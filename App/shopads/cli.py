from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .config import application_dir, load_config
from .errors import ShopAdsError
from .manifest import relative_record, taipei_timestamp, write_json_atomic
from .validation import JobSpec, inspect_job, resolve_job_dir


LOGGER = logging.getLogger("shopads")


def _close_logging() -> None:
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
        handler.close()


def _setup_logging(job_dir: Path | None = None) -> Path | None:
    _close_logging()
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    LOGGER.addHandler(console)
    if not job_dir:
        return None
    log_dir = job_dir / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = __import__("datetime").datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    log_path = log_dir / f"shopads-{stamp}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    return log_path


def _print_error(error: ShopAdsError) -> None:
    LOGGER.error("%s", error)


def _load_for_job(config_argument: str | None, job_argument: str | None) -> tuple[Path, dict[str, Any]]:
    config_path = Path(config_argument).resolve() if config_argument else None
    base_config = load_config(config_path)
    job_dir = resolve_job_dir(job_argument, Path(base_config["paths"]["work_root"]))
    return job_dir, load_config(config_path, job_dir)


def _safe_cleanup_group(generated_dir: Path, group_name: str) -> list[str]:
    generated_dir.mkdir(parents=True, exist_ok=True)
    resolved = generated_dir.resolve()
    expected_parent = generated_dir.parent.resolve()
    if resolved.parent != expected_parent or resolved.name != "Generated":
        raise ShopAdsError(
            "E302", "WRITE_OUTPUT", "拒絕清理非 Generated 目錄。", str(resolved)
        )
    pattern = re.compile(rf"^{re.escape(group_name)}(?:-\d+)?\.(?:png|gif)$", re.IGNORECASE)
    removed: list[str] = []
    for path in generated_dir.iterdir():
        if path.is_file() and pattern.fullmatch(path.name):
            path.unlink()
            removed.append(path.name)
    return removed


def _source_records(job: JobSpec) -> list[dict[str, Any]]:
    paths = [job.directory / "Prod_Description.md"]
    for group in job.groups:
        paths.extend(group.images)
        description = group.directory / "Img_Description.md"
        if description.is_file() and not group.passthrough_gif:
            paths.append(description)
    return [relative_record(path, job.directory) for path in paths]


def command_validate(args: argparse.Namespace) -> int:
    job_dir, _config = _load_for_job(args.config, args.job)
    _setup_logging(job_dir)
    LOGGER.info("[VALIDATE_INPUT] 作業目錄：%s", job_dir)
    job = inspect_job(job_dir)
    for group in job.groups:
        mode = "GIF 複製" if group.passthrough_gif else f"靜態圖片 {len(group.images)} 張"
        LOGGER.info("[VALIDATE_INPUT] 群組 %s：%s", group.name, mode)
    for error in job.errors:
        _print_error(error)
    if job.errors:
        LOGGER.error("驗證失敗：%d 個群組錯誤。", len(job.errors))
        return 1
    LOGGER.info("驗證成功：%d 個群組。", len(job.groups))
    return 0


def command_generate(args: argparse.Namespace) -> int:
    try:
        from .compositor import compose_clean, verify_image
    except RuntimeError as exc:
        raise ShopAdsError("E003", "ENVIRONMENT", str(exc)) from exc

    job_dir, config = _load_for_job(args.config, args.job)
    log_path = _setup_logging(job_dir)
    LOGGER.info("[VALIDATE_INPUT] 開始生成：%s", job_dir)
    job = inspect_job(job_dir)
    errors = list(job.errors)
    generated_dir = job_dir / "Result" / "Generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "Result" / "Final").mkdir(parents=True, exist_ok=True)
    group_results: list[dict[str, Any]] = []
    max_per_page = int(config["image"]["max_images_per_page"])
    expected_size = (int(config["image"]["width"]), int(config["image"]["height"]))

    for group in job.groups:
        LOGGER.info("[PROCESS_IMAGES] 處理群組 %s。", group.name)
        try:
            with tempfile.TemporaryDirectory(prefix=f"shopads-{group.name}-", dir=job_dir / "Result") as temp_name:
                staging_dir = Path(temp_name)
                staged: list[Path] = []
                if group.passthrough_gif:
                    output = staging_dir / f"{group.name}.gif"
                    shutil.copyfile(group.images[0], output)
                    verify_image(output)
                    staged.append(output)
                else:
                    pages = [
                        group.images[index : index + max_per_page]
                        for index in range(0, len(group.images), max_per_page)
                    ]
                    for page_index, page in enumerate(pages, start=1):
                        filename = (
                            f"{group.name}.png"
                            if len(pages) == 1
                            else f"{group.name}-{page_index}.png"
                        )
                        output = staging_dir / filename
                        compose_clean(
                            page,
                            group.description or {},
                            group.name,
                            page_index,
                            config,
                            output,
                        )
                        verify_image(output, expected_size)
                        staged.append(output)

                removed = _safe_cleanup_group(generated_dir, group.name)
                if removed:
                    LOGGER.info("[WRITE_OUTPUT] 清除舊成品：%s", ", ".join(removed))
                final_outputs: list[Path] = []
                for staged_path in staged:
                    destination = generated_dir / staged_path.name
                    os.replace(staged_path, destination)
                    final_outputs.append(destination)
                    LOGGER.info("[WRITE_OUTPUT] 已產生：%s", destination)
                group_results.append(
                    {
                        "name": group.name,
                        "mode": "gif_passthrough" if group.passthrough_gif else "clean",
                        "inputs": [relative_record(path, job_dir) for path in group.images],
                        "outputs": [relative_record(path, job_dir) for path in final_outputs],
                    }
                )
        except ShopAdsError as exc:
            errors.append(exc)
            _print_error(exc)
        except OSError as exc:
            error = ShopAdsError(
                "E303", "WRITE_OUTPUT", f"群組處理失敗：{exc}", str(group.directory)
            )
            errors.append(error)
            _print_error(error)

    status = "success" if not errors and group_results else "partial" if group_results else "failed"
    manifest = {
        "schema_version": 1,
        "program_version": __version__,
        "job": job_dir.name,
        "status": status,
        "created_at": taipei_timestamp(),
        "config": {
            "path": config["_config_path"],
            "width": config["image"]["width"],
            "height": config["image"]["height"],
            "style": config["image"]["default_style"],
        },
        "product": job.product,
        "sources": _source_records(job),
        "groups": group_results,
        "errors": [error.as_dict() for error in errors],
        "log": str(log_path.relative_to(job_dir)) if log_path else None,
    }
    write_json_atomic(job_dir / "run-manifest.json", manifest)
    if errors:
        LOGGER.error("生成完成但有 %d 個錯誤；狀態：%s。", len(errors), status)
        return 1
    LOGGER.info("生成成功：%d 個群組。", len(group_results))
    return 0


def command_check_final(args: argparse.Namespace) -> int:
    try:
        from .package_ops import check_final
    except RuntimeError as exc:
        raise ShopAdsError("E003", "ENVIRONMENT", str(exc)) from exc
    job_dir, config = _load_for_job(args.config, args.job)
    _setup_logging(job_dir)
    files = check_final(job_dir, config)
    for path in files:
        LOGGER.info("[VERIFY_OUTPUT] Final 通過：%s", path)
    LOGGER.info("Final 驗證成功：%d 個檔案。", len(files))
    return 0


def command_package(args: argparse.Namespace) -> int:
    try:
        from .package_ops import create_package, verify_package
    except RuntimeError as exc:
        raise ShopAdsError("E003", "ENVIRONMENT", str(exc)) from exc
    job_dir, config = _load_for_job(args.config, args.job)
    _setup_logging(job_dir)
    package_path = create_package(job_dir, config, __version__)
    count = verify_package(package_path)
    LOGGER.info("[PACKAGE] 已建立並驗證封裝：%s", package_path)
    LOGGER.info("封裝成功：%d 個檔案。", count)
    return 0


def command_verify_package(args: argparse.Namespace) -> int:
    try:
        from .package_ops import verify_package
    except RuntimeError as exc:
        raise ShopAdsError("E003", "ENVIRONMENT", str(exc)) from exc
    _setup_logging()
    package_path = Path(args.package_file).expanduser().resolve()
    count = verify_package(package_path)
    LOGGER.info("[PACKAGE] 封裝驗證成功：%s（%d 個檔案）", package_path, count)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shop Ads 1080×1080 圖片產生工具")
    parser.add_argument("--version", action="version", version=f"ShopAds {__version__}")
    parser.add_argument(
        "--config", help="config.toml 路徑；預設讀取程式同目錄的 config.toml。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="檢查作業目錄與說明檔。")
    validate.add_argument("job", nargs="?", help="yyyyMMdd 作業目錄；省略時使用最新日期。")
    validate.set_defaults(handler=command_validate)

    generate = subparsers.add_parser("generate", help="產生 Generated 圖片。")
    generate.add_argument("job", nargs="?", help="yyyyMMdd 作業目錄；省略時使用最新日期。")
    generate.set_defaults(handler=command_generate)

    check = subparsers.add_parser("check-final", help="檢查 Final 是否可供封裝。")
    check.add_argument("job", nargs="?", help="yyyyMMdd 作業目錄；省略時使用最新日期。")
    check.set_defaults(handler=command_check_final)

    package = subparsers.add_parser("package", help="建立跨電腦發布封裝。")
    package.add_argument("job", nargs="?", help="yyyyMMdd 作業目錄；省略時使用最新日期。")
    package.set_defaults(handler=command_package)

    verify = subparsers.add_parser("verify-package", help="在另一台電腦驗證發布封裝。")
    verify.add_argument("package_file", help="PublishPackage ZIP 路徑。")
    verify.set_defaults(handler=command_verify_package)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ShopAdsError as exc:
        if not LOGGER.handlers:
            _setup_logging()
        _print_error(exc)
        return 2
    except KeyboardInterrupt:
        LOGGER.error("使用者中止執行。")
        return 130
    finally:
        _close_logging()
