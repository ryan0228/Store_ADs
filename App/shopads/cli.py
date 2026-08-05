from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
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


def _restore_inherited_permissions(path: Path) -> None:
    """Windows 搬移暫存成品後，恢復目的目錄的 ACL 繼承。"""
    if os.name != "nt":
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:e"],
            capture_output=True,
            check=False,
            creationflags=flags,
        )
    except OSError as exc:
        raise ShopAdsError("E304", "WRITE_OUTPUT", f"無法恢復成品權限繼承：{exc}", str(path)) from exc
    if result.returncode != 0:
        raise ShopAdsError("E304", "WRITE_OUTPUT", "無法恢復成品權限繼承。", str(path), "請確認目前帳號可修改 Generated 檔案權限。")


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


def _safe_cleanup_generated(generated_dir: Path) -> list[str]:
    generated_dir.mkdir(parents=True, exist_ok=True)
    resolved = generated_dir.resolve()
    expected_parent = generated_dir.parent.resolve()
    if resolved.parent != expected_parent or resolved.name != "Generated":
        raise ShopAdsError(
            "E302", "WRITE_OUTPUT", "拒絕清理非 Generated 目錄。", str(resolved)
        )
    pattern = re.compile(r"^\d{2}\.(?:png|gif)$", re.IGNORECASE)
    removed: list[str] = []
    for path in generated_dir.iterdir():
        if path.is_file() and pattern.fullmatch(path.name):
            _restore_inherited_permissions(path)
            path.unlink()
            removed.append(path.name)
    return removed


def _source_records(job: JobSpec) -> list[dict[str, Any]]:
    duplicate_paths = [item[0] for item in job.duplicate_images]
    paths = [job.directory / "Product_Description.md", *job.images, *duplicate_paths]
    return [relative_record(path, job.directory) for path in paths]


def command_validate(args: argparse.Namespace) -> int:
    job_dir, _config = _load_for_job(args.config, args.job)
    _setup_logging(job_dir)
    LOGGER.info("[VALIDATE_INPUT] 作業目錄：%s", job_dir)
    job = inspect_job(job_dir)
    for duplicate, original, _digest in job.duplicate_images:
        LOGGER.warning("[VALIDATE_INPUT] 略過重複圖片：%s（與 %s 內容相同）。", duplicate.name, original.name)
    LOGGER.info("[VALIDATE_INPUT] 靜態圖片：%d 張（含單影格 GIF %d 個）；動畫 GIF：%d 個。", len(job.static_images), len(job.single_frame_gifs), len(job.animated_gifs))
    for error in job.errors:
        _print_error(error)
    if job.errors:
        LOGGER.error("驗證失敗：%d 個輸入錯誤。", len(job.errors))
        return 1
    LOGGER.info("驗證成功：共 %d 個有效來源檔案，略過 %d 個重複檔案。", len(job.images), len(job.duplicate_images))
    return 0


def command_new_job(args: argparse.Namespace) -> int:
    from .job_ops import create_job, open_job

    config_path = Path(args.config).resolve() if args.config else None
    config = load_config(config_path)
    _setup_logging()
    job_dir = create_job(Path(config["paths"]["work_root"]), args.date)
    LOGGER.info("[CREATE_JOB] 已建立商品作業：%s", job_dir)
    LOGGER.info("下一步：填寫 Product_Description.md，並將商品圖片放入 Input。")
    if not args.no_open:
        for failure in open_job(job_dir):
            LOGGER.warning("[CREATE_JOB] 無法自動開啟 %s", failure)
    return 0


def command_analyze(args: argparse.Namespace) -> int:
    from .ai_plan import save_plan
    from .ai_provider import analyze

    job_dir, config = _load_for_job(args.config, args.job)
    _setup_logging(job_dir)
    job = inspect_job(job_dir)
    for duplicate, original, digest in job.duplicate_images:
        LOGGER.warning("[AI_ANALYZE] 不送出重複圖片：%s（保留 %s，SHA-256 %s…）。", duplicate.name, original.name, digest[:12])
    maximum = int(config["ai"].get("max_input_images", 15))
    if len(job.images) > maximum:
        raise ShopAdsError("E628", "AI_ANALYZE", f"來源檔案共 {len(job.images)} 個，超過上限 {maximum} 個。", str(job_dir / "Input"))
    LOGGER.info("[AI_ANALYZE] 使用 %s 分析 %d 張靜態圖片與 %d 個動畫 GIF 代表影格；不傳送完整 GIF。", config["ai"].get("provider"), len(job.static_images), len(job.animated_gifs))
    payload, metadata = analyze(job, config)
    rejected = payload.setdefault("rejected", [])
    for duplicate, original, _digest in job.duplicate_images:
        rejected.append({"image": duplicate.name, "reason": f"與 {original.name} 檔案內容完全相同，已在上傳 AI 前略過。"})
    payload["product"] = job.product
    payload["ai"] = metadata
    plan_path = save_plan(job_dir, payload)
    LOGGER.info("[AI_PLAN] 已建立：%s", plan_path)
    LOGGER.info("[AI_PLAN] 預覽：%s", job_dir / "Work" / "preview.html")
    return 0


def command_generate(args: argparse.Namespace) -> int:
    try:
        from .compositor import compose_clean, compose_vendor_text, verify_image
    except RuntimeError as exc:
        raise ShopAdsError("E003", "ENVIRONMENT", str(exc)) from exc

    job_dir, config = _load_for_job(args.config, args.job)
    log_path = _setup_logging(job_dir)
    LOGGER.info("[VALIDATE_INPUT] 開始生成：%s", job_dir)
    job = inspect_job(job_dir)
    from .ai_plan import load_plan
    plan = load_plan(job_dir)
    errors = list(job.errors)
    generated_dir = job_dir / "Result" / "Generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "Result" / "Final").mkdir(parents=True, exist_ok=True)
    group_results: list[dict[str, Any]] = []
    expected_size = (int(config["image"]["width"]), int(config["image"]["height"]))

    input_by_name = {path.name: path for path in job.images}
    staged_all: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="shopads-plan-", dir=job_dir / "Result") as temp_name:
            staging_dir = Path(temp_name)
            for output_plan in plan["outputs"]:
                name = output_plan["output"]
                LOGGER.info("[PROCESS_IMAGES] 處理成品 %s。", name)
                sources = [input_by_name[item] for item in output_plan["images"]]
                output = staging_dir / name
                if output_plan["type"] == "gif":
                    shutil.copyfile(sources[0], output)
                    verify_image(output)
                    mode = "gif_passthrough"
                elif output_plan["type"] == "text":
                    compose_vendor_text({"上標題": output_plan["top_title"], "說明": output_plan["description"], "下標題": output_plan["bottom_title"]}, job_dir.name, int(Path(name).stem), config, output)
                    verify_image(output, expected_size)
                    mode = "vendor_text"
                else:
                    compose_clean(sources, {"上標題": output_plan["top_title"], "說明": output_plan["description"], "下標題": output_plan["bottom_title"]}, job_dir.name, int(Path(name).stem), config, output)
                    verify_image(output, expected_size)
                    mode = output_plan["layout"]
                staged_all.append(output)
                group_results.append({"name": Path(name).stem, "mode": mode, "inputs": [relative_record(path, job_dir) for path in sources], "outputs": []})

            removed = _safe_cleanup_generated(generated_dir)
            if removed:
                LOGGER.info("[WRITE_OUTPUT] 清除舊成品：%s", ", ".join(removed))
            for staged_path, result in zip(staged_all, group_results, strict=True):
                destination = generated_dir / staged_path.name
                os.replace(staged_path, destination)
                _restore_inherited_permissions(destination)
                result["outputs"] = [relative_record(destination, job_dir)]
                LOGGER.info("[WRITE_OUTPUT] 已產生：%s", destination)
    except ShopAdsError as exc:
        errors.append(exc)
        _print_error(exc)
    except OSError as exc:
        error = ShopAdsError("E303", "WRITE_OUTPUT", f"計畫處理失敗：{exc}", str(job_dir))
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

    new_job = subparsers.add_parser("new-job", help="建立今天的下一個商品作業。")
    new_job.add_argument("--date", help="指定 YYYY-MM-DD；省略時使用本機今天日期。")
    new_job.add_argument("--no-open", action="store_true", help="建立後不要開啟描述檔與 Input。")
    new_job.set_defaults(handler=command_new_job)

    validate = subparsers.add_parser("validate", help="檢查作業目錄與說明檔。")
    validate.add_argument("job", nargs="?", help="yyyyMMdd-NN 作業目錄；省略時使用最新作業。")
    validate.set_defaults(handler=command_validate)

    analyze_parser = subparsers.add_parser("analyze", help="以 AI 分析 Input 並建立預覽計畫。")
    analyze_parser.add_argument("job", nargs="?", help="yyyyMMdd-NN 作業目錄；省略時使用最新作業。")
    analyze_parser.set_defaults(handler=command_analyze)

    generate = subparsers.add_parser("generate", help="產生 Generated 圖片。")
    generate.add_argument("job", nargs="?", help="yyyyMMdd-NN 作業目錄；省略時使用最新作業。")
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
