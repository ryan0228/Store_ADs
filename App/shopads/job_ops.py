from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .config import application_dir
from .errors import ShopAdsError


def _job_date(value: str | None) -> str:
    if value is None:
        return datetime.now().astimezone().strftime("%Y%m%d")
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise ShopAdsError("E130", "CREATE_JOB", "日期必須是有效的 YYYY-MM-DD。", value) from exc


def create_job(work_root: Path, date_value: str | None = None) -> Path:
    work_root = work_root.expanduser().resolve()
    if not work_root.is_dir():
        raise ShopAdsError("E131", "CREATE_JOB", "作業根目錄不存在。", str(work_root))
    template = application_dir() / "templates" / "Product_Description.md"
    if not template.is_file():
        raise ShopAdsError("E132", "CREATE_JOB", "找不到商品說明範本。", str(template))
    day = _job_date(date_value)
    target: Path | None = None
    for sequence in range(1, 11):
        candidate = work_root / f"{day}-{sequence:02d}"
        if not candidate.exists():
            target = candidate
            break
    if target is None:
        raise ShopAdsError("E133", "CREATE_JOB", f"{day} 已建立 10 個商品作業。", str(work_root), "請確認日期，或整理當天既有作業後再試。")

    try:
        with tempfile.TemporaryDirectory(prefix=".shopads-newjob-", dir=work_root) as temp_name:
            staging = Path(temp_name)
            (staging / "Input").mkdir()
            (staging / "Result" / "Generated").mkdir(parents=True)
            (staging / "Result" / "Final").mkdir()
            shutil.copyfile(template, staging / "Product_Description.md")
            if target.exists():
                raise ShopAdsError("E134", "CREATE_JOB", "商品作業編號已被其他程序建立。", str(target), "請重新執行以取得下一個編號。")
            staging.rename(target)
    except ShopAdsError:
        raise
    except OSError as exc:
        raise ShopAdsError("E135", "CREATE_JOB", f"商品作業建立失敗：{exc}", str(target)) from exc
    return target


def open_job(job_dir: Path) -> list[str]:
    failures: list[str] = []
    for path in (job_dir / "Product_Description.md", job_dir / "Input"):
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            failures.append(f"{path}：{exc}")
    return failures
