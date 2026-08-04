from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import ShopAdsError
from .markdown import parse_sections


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
JOB_RE = re.compile(r"^(\d{8})-(0[1-9]|10)$")


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def gif_is_animated(path: Path) -> bool:
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(path) as gif:
            return int(getattr(gif, "n_frames", 1)) > 1
    except (OSError, UnidentifiedImageError) as exc:
        raise ShopAdsError("E117", "VALIDATE_INPUT", f"GIF 無法讀取：{exc}", str(path)) from exc


@dataclass(slots=True)
class JobSpec:
    directory: Path
    product: dict[str, str]
    images: list[Path]
    static_images: list[Path]
    single_frame_gifs: list[Path]
    animated_gifs: list[Path]
    duplicate_images: list[tuple[Path, Path, str]]
    errors: list[ShopAdsError]


def filter_duplicate_images(images: list[Path]) -> tuple[list[Path], list[tuple[Path, Path, str]]]:
    """Keep the first naturally sorted file for each exact SHA-256 payload."""
    unique: list[Path] = []
    duplicates: list[tuple[Path, Path, str]] = []
    first_by_digest: dict[str, Path] = {}
    for path in images:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise ShopAdsError("E118", "VALIDATE_INPUT", f"圖片無法讀取：{exc}", str(path)) from exc
        value = digest.hexdigest()
        original = first_by_digest.get(value)
        if original is None:
            first_by_digest[value] = path
            unique.append(path)
        else:
            duplicates.append((path, original, value))
    return unique, duplicates


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
                "找不到 yyyyMMdd-NN 格式的商品作業目錄。",
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
            "作業目錄名稱必須是有效的 yyyyMMdd-NN，流水號為 01～10。",
            str(job_dir),
        )
    return job_dir


def _valid_date_name(value: str) -> bool:
    match = JOB_RE.fullmatch(value)
    if not match:
        return False
    try:
        datetime.strptime(match.group(1), "%Y%m%d")
        return True
    except ValueError:
        return False


def inspect_job(job_dir: Path) -> JobSpec:
    product = parse_sections(
        job_dir / "Product_Description.md", ("商品名稱", "商品說明")
    )
    input_dir = job_dir / "Input"
    if not input_dir.is_dir():
        raise ShopAdsError(
            "E114",
            "VALIDATE_INPUT",
            "找不到 Input 圖片目錄。",
            str(input_dir),
            "建立 Input 目錄並放入商品圖片。",
        )
    discovered = sorted(
        (item for item in input_dir.iterdir() if item.is_file() and item.suffix.casefold() in SUPPORTED_EXTENSIONS),
        key=natural_key,
    )
    if not discovered:
        raise ShopAdsError("E115", "VALIDATE_INPUT", "Input 內沒有支援的圖片。", str(input_dir))
    images, duplicate_images = filter_duplicate_images(discovered)
    single_frame_gifs: list[Path] = []
    animated_gifs: list[Path] = []
    for path in (item for item in images if item.suffix.casefold() == ".gif"):
        animated = gif_is_animated(path)
        (animated_gifs if animated else single_frame_gifs).append(path)
    static_images = [item for item in images if item.suffix.casefold() != ".gif" or item in single_frame_gifs]
    return JobSpec(job_dir, product, images, static_images, single_frame_gifs, animated_gifs, duplicate_images, [])
