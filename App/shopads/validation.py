from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import ShopAdsError
from .markdown import parse_sections


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
GROUP_RE = re.compile(r"^\d+$")


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


@dataclass(slots=True)
class GroupSpec:
    name: str
    directory: Path
    images: list[Path]
    description: dict[str, str] | None
    passthrough_gif: bool


@dataclass(slots=True)
class JobSpec:
    directory: Path
    product: dict[str, str]
    groups: list[GroupSpec]
    errors: list[ShopAdsError]


def resolve_job_dir(argument: str | None, work_root: Path) -> Path:
    if argument:
        job_dir = Path(argument).expanduser().resolve()
    else:
        if not work_root.is_dir():
            raise ShopAdsError(
                "E110", "VALIDATE_INPUT", "作業根目錄不存在。", str(work_root)
            )
        candidates = [
            item for item in work_root.iterdir() if item.is_dir() and _valid_date_name(item.name)
        ]
        if not candidates:
            raise ShopAdsError(
                "E111",
                "VALIDATE_INPUT",
                "找不到 yyyyMMdd 格式的作業目錄。",
                str(work_root),
            )
        job_dir = max(candidates, key=lambda item: item.name).resolve()

    if not job_dir.is_dir():
        raise ShopAdsError(
            "E112", "VALIDATE_INPUT", "指定的作業目錄不存在。", str(job_dir)
        )
    if not _valid_date_name(job_dir.name):
        raise ShopAdsError(
            "E113",
            "VALIDATE_INPUT",
            "作業目錄名稱必須是有效的 yyyyMMdd 日期。",
            str(job_dir),
        )
    return job_dir


def _valid_date_name(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def inspect_job(job_dir: Path) -> JobSpec:
    product = parse_sections(
        job_dir / "Prod_Description.md", ("商品名稱", "使用情境", "商品說明")
    )
    group_dirs = sorted(
        (item for item in job_dir.iterdir() if item.is_dir() and GROUP_RE.fullmatch(item.name)),
        key=lambda item: natural_key(item),
    )
    if not group_dirs:
        raise ShopAdsError(
            "E114",
            "VALIDATE_INPUT",
            "找不到數字圖片群組目錄。",
            str(job_dir),
            "建立 01、02、03 等子目錄並放入圖片。",
        )

    groups: list[GroupSpec] = []
    errors: list[ShopAdsError] = []
    for directory in group_dirs:
        images = sorted(
            (
                item
                for item in directory.iterdir()
                if item.is_file() and item.suffix.casefold() in SUPPORTED_EXTENSIONS
            ),
            key=natural_key,
        )
        if not images:
            errors.append(
                ShopAdsError(
                    "E115", "VALIDATE_INPUT", "群組內沒有支援的圖片。", str(directory)
                )
            )
            continue
        gifs = [item for item in images if item.suffix.casefold() == ".gif"]
        if gifs and not (len(images) == 1 and len(gifs) == 1):
            errors.append(
                ShopAdsError(
                    "E116",
                    "VALIDATE_INPUT",
                    "GIF 不可與其他圖片混用。",
                    str(directory),
                    "單一 GIF 請獨立放在一個數字群組。",
                )
            )
            continue
        if len(gifs) == 1:
            groups.append(GroupSpec(directory.name, directory, images, None, True))
            continue
        try:
            description = parse_sections(
                directory / "Img_Description.md", ("上標題", "說明", "下標題")
            )
        except ShopAdsError as exc:
            errors.append(exc)
            continue
        groups.append(GroupSpec(directory.name, directory, images, description, False))
    return JobSpec(job_dir, product, groups, errors)
