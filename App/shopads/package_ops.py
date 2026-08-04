from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .compositor import verify_image
from .errors import ShopAdsError
from .manifest import sha256_file, taipei_timestamp


def load_generation_manifest(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "run-manifest.json"
    if not path.is_file():
        raise ShopAdsError(
            "E410",
            "VERIFY_OUTPUT",
            "找不到生成 Manifest。",
            str(path),
            "請先執行 generate。",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShopAdsError(
            "E411", "VERIFY_OUTPUT", f"生成 Manifest 無法讀取：{exc}", str(path)
        ) from exc


def expected_output_names(manifest: dict[str, Any]) -> list[str]:
    if manifest.get("status") != "success":
        raise ShopAdsError(
            "E412",
            "VERIFY_OUTPUT",
            "最近一次生成未完全成功，不能確認 Final。",
            suggestion="修正 run-manifest.json 內列出的錯誤後重新生成。",
        )
    names: list[str] = []
    for group in manifest.get("groups", []):
        for output in group.get("outputs", []):
            names.append(Path(output["path"]).name)
    if not names:
        raise ShopAdsError("E413", "VERIFY_OUTPUT", "Manifest 沒有任何生成成品。")
    return names


def check_final(job_dir: Path, config: dict[str, Any]) -> list[Path]:
    manifest = load_generation_manifest(job_dir)
    final_dir = job_dir / "Result" / "Final"
    expected = expected_output_names(manifest)
    missing = [name for name in expected if not (final_dir / name).is_file()]
    if missing:
        raise ShopAdsError(
            "E414",
            "VERIFY_OUTPUT",
            f"Final 缺少成品：{', '.join(missing)}。",
            str(final_dir),
            "檢視或加工 Generated 後，將確認版本放入 Final。",
        )
    files = [final_dir / name for name in expected]
    expected_size = (int(config["image"]["width"]), int(config["image"]["height"]))
    for path in files:
        verify_image(path, None if path.suffix.casefold() == ".gif" else expected_size)
    return files


def create_package(job_dir: Path, config: dict[str, Any], version: str) -> Path:
    final_files = check_final(job_dir, config)
    markdown_files = sorted(job_dir.glob("*.md"))
    records: list[dict[str, Any]] = []
    sources: list[tuple[Path, str]] = []
    for path in final_files:
        archive_name = f"Final/{path.name}"
        sources.append((path, archive_name))
        records.append({"path": archive_name, "size": path.stat().st_size, "sha256": sha256_file(path)})
    for path in markdown_files:
        archive_name = path.relative_to(job_dir).as_posix()
        sources.append((path, archive_name))
        records.append({"path": archive_name, "size": path.stat().st_size, "sha256": sha256_file(path)})

    publish_manifest = {
        "schema_version": 1,
        "program_version": version,
        "job": job_dir.name,
        "created_at": taipei_timestamp(),
        "files": records,
    }
    package_dir = job_dir / "PublishPackages"
    package_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    package_path = package_dir / f"PublishPackage-{job_dir.name}-{stamp}.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_name in sources:
            archive.write(source, archive_name)
        archive.writestr(
            "publish-manifest.json",
            json.dumps(publish_manifest, ensure_ascii=False, indent=2) + "\n",
        )
    return package_path


def verify_package(package_path: Path) -> int:
    if not package_path.is_file():
        raise ShopAdsError("E501", "PACKAGE", "找不到封裝檔。", str(package_path))
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            manifest = json.loads(archive.read("publish-manifest.json").decode("utf-8"))
            checked = 0
            for record in manifest.get("files", []):
                data = archive.read(record["path"])
                import hashlib

                digest = hashlib.sha256(data).hexdigest()
                if digest != record["sha256"] or len(data) != record["size"]:
                    raise ShopAdsError(
                        "E502",
                        "PACKAGE",
                        f"封裝內容驗證失敗：{record['path']}。",
                        str(package_path),
                    )
                checked += 1
            return checked
    except ShopAdsError:
        raise
    except (OSError, KeyError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ShopAdsError(
            "E503", "PACKAGE", f"封裝檔無法驗證：{exc}", str(package_path)
        ) from exc
