from __future__ import annotations

import hashlib
import os
import random
import re
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
except ImportError as exc:  # pragma: no cover - environment guard
    raise RuntimeError("缺少 Pillow；請先執行 python -m pip install Pillow。") from exc

from .errors import ShopAdsError


def _split_long_token(draw: ImageDraw.ImageDraw, token: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    all_lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            all_lines.append("")
            continue
        tokens = re.findall(r"\S+\s*", paragraph)
        line = ""
        for token in tokens:
            if draw.textlength(line + token, font=font) <= width:
                line += token
                continue
            if line.strip():
                all_lines.append(line.rstrip())
                line = ""
            if draw.textlength(token, font=font) <= width:
                line = token.lstrip()
            else:
                pieces = _split_long_token(draw, token.strip(), font, width)
                all_lines.extend(pieces[:-1])
                line = pieces[-1] if pieces else ""
        if line.strip():
            all_lines.append(line.rstrip())
    return "\n".join(all_lines)


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    start_size: int,
    minimum_size: int,
    box: tuple[int, int, int, int],
    fill: str,
    spacing: int = 8,
) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    for size in range(start_size, minimum_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        wrapped = wrap_text(draw, text, font, width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing, align="center")
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if text_width <= width and text_height <= height:
            x = left + (width - text_width) / 2
            y = top + (height - text_height) / 2 - bbox[1]
            draw.multiline_text(
                (x, y), wrapped, font=font, fill=fill, spacing=spacing, align="center"
            )
            return
    raise ShopAdsError(
        "E204",
        "PROCESS_IMAGES",
        "文字超出版面安全區，縮小到最小字級後仍無法放入。",
        suggestion="縮短 Img_Description.md 文字，或在 job.toml 調整允許的字級。",
    )


def _open_static(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            if getattr(image, "is_animated", False):
                raise ShopAdsError(
                    "E205", "PROCESS_IMAGES", "動畫圖片不可當成靜態圖片合成。", str(path)
                )
            return image.convert("RGBA")
    except ShopAdsError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise ShopAdsError(
            "E203",
            "PROCESS_IMAGES",
            f"圖片無法讀取，檔案可能損壞：{exc}",
            str(path),
        ) from exc


def _fixed_rotation(group: str, page: int, filename: str, maximum: float) -> float:
    seed_text = f"{group}|{page}|{filename}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_text).digest()[:8], "big")
    return random.Random(seed).uniform(-maximum, maximum)


def _make_card(image_path: Path, width: int, height: int, style: dict[str, Any]) -> Image.Image:
    radius = int(style["corner_radius"])
    inner = 18
    body = Image.new("RGBA", (width, height), style["card_color"])
    image = _open_static(image_path)
    fitted = ImageOps.contain(image, (width - inner * 2, height - inner * 2), Image.Resampling.LANCZOS)
    pos = ((width - fitted.width) // 2, (height - fitted.height) // 2)
    body.alpha_composite(fitted, pos)

    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    body.putalpha(mask)

    border = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.rounded_rectangle(
        (1, 1, width - 2, height - 2), radius=radius, outline=style["border_color"], width=5
    )
    body.alpha_composite(border)
    return body


def _paste_rotated_card(
    canvas: Image.Image,
    card: Image.Image,
    center: tuple[int, int],
    angle: float,
    shadow_blur: int,
) -> None:
    rotated = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    x = int(center[0] - rotated.width / 2)
    y = int(center[1] - rotated.height / 2)
    shadow = Image.new("RGBA", rotated.size, (25, 25, 25, 0))
    shadow.putalpha(rotated.getchannel("A").filter(ImageFilter.GaussianBlur(shadow_blur)))
    canvas.alpha_composite(shadow, (x + 8, y + 12))
    canvas.alpha_composite(rotated, (x, y))


def _create_background(width: int, height: int, style: dict[str, Any]) -> Image.Image:
    start = ImageColor.getrgb(str(style["background_color"]))
    end = ImageColor.getrgb(str(style.get("background_tint", style["background_color"])))
    canvas = Image.new("RGBA", (width, height))
    pixels = canvas.load()
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(start[index] * (1 - ratio) + end[index] * ratio) for index in range(3)) + (255,)
        for x in range(width):
            pixels[x, y] = color
    decoration = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(decoration)
    accent = ImageColor.getrgb(str(style["accent_color"]))
    primary = ImageColor.getrgb(str(style["primary_color"]))
    draw.ellipse((-180, 170, 360, 710), fill=(*accent, 20))
    draw.ellipse((760, 80, 1240, 560), fill=(*primary, 12))
    draw.ellipse((690, 700, 1180, 1190), fill=(*accent, 12))
    canvas.alpha_composite(decoration)
    return canvas


def _banner_lines(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ShopAdsError("E208", "PROCESS_IMAGES", f"店鋪特色文字無法讀取：{exc}", str(path)) from exc
    values = [line.lstrip()[2:].strip() for line in lines if line.lstrip().startswith("- ") and line.lstrip()[2:].strip()]
    if not values:
        raise ShopAdsError("E208", "PROCESS_IMAGES", "店鋪特色文字檔沒有可用項目。", str(path))
    return values


def _apply_branding(canvas: Image.Image, config: dict[str, Any], group: str, page_number: int) -> None:
    branding = config["branding"]
    path = Path(branding["_footer_image_path"])
    try:
        with Image.open(path) as source:
            logo = source.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise ShopAdsError("E207", "PROCESS_IMAGES", f"品牌頁尾圖片無法讀取：{exc}", str(path)) from exc
    target_width = int(branding["footer_width"])
    target_height = max(1, round(logo.height * target_width / logo.width))
    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
    margin = int(branding["footer_margin"])
    y = canvas.height - target_height - margin
    canvas.alpha_composite(logo, (margin, y))

    banner_path = Path(branding["_banner_text_path"])
    lines = _banner_lines(banner_path)
    seed = int.from_bytes(hashlib.sha256(f"{group}|{page_number}|store-banner".encode("utf-8")).digest()[:8], "big")
    banner = lines[seed % len(lines)]
    draw = ImageDraw.Draw(canvas)
    fit_text(
        draw,
        banner,
        config["font"]["bold"],
        int(branding.get("banner_font_size", 28)),
        18,
        (margin + target_width + 20, y - 8, canvas.width - margin, y + target_height + 8),
        config["styles"][config["image"]["default_style"]]["primary_color"],
        spacing=2,
    )


def _save_canvas(canvas: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    try:
        canvas.convert("RGB").save(temporary, format="PNG", optimize=True)
        os.replace(temporary, output_path)
    except OSError as exc:
        if temporary.exists():
            temporary.unlink()
        raise ShopAdsError("E301", "WRITE_OUTPUT", f"成品無法寫入：{exc}", str(output_path)) from exc


def compose_clean(
    image_paths: list[Path],
    description: dict[str, str],
    group: str,
    page_number: int,
    config: dict[str, Any],
    output_path: Path,
) -> None:
    image_cfg = config["image"]
    font_cfg = config["font"]
    style = config["styles"][image_cfg["default_style"]]
    width, height = int(image_cfg["width"]), int(image_cfg["height"])
    canvas = _create_background(width, height, style)
    draw = ImageDraw.Draw(canvas)

    margin = int(style["safe_margin"])
    draw.rounded_rectangle(
        (margin, 38, width - margin, 46), radius=4, fill=style["accent_color"]
    )
    fit_text(
        draw,
        description["上標題"],
        font_cfg["bold"],
        int(font_cfg["title_size"]),
        int(font_cfg["minimum_size"]),
        (margin, 58, width - margin, 190),
        style["title_color"],
    )

    count = len(image_paths)
    if count == 1:
        card_width, card_height = 760, 520
        centers = [(540, 493)]
    elif count == 2:
        card_width, card_height = 465, 510
        centers = [(285, 500), (795, 500)]
    else:
        raise ShopAdsError("E206", "PROCESS_IMAGES", "單張成品來源圖片必須為一至二張。")

    maximum_rotation = float(style["rotation_degrees"])
    for path, center in zip(image_paths, centers, strict=True):
        card = _make_card(path, card_width, card_height, style)
        angle = _fixed_rotation(group, page_number, path.name, maximum_rotation)
        _paste_rotated_card(canvas, card, center, angle, int(style["shadow_blur"]))

    fit_text(
        draw,
        description["說明"],
        font_cfg["regular"],
        int(font_cfg["body_size"]),
        int(font_cfg["minimum_size"]),
        (margin, 775, width - margin, 895),
        style["body_color"],
        spacing=6,
    )
    fit_text(
        draw,
        description["下標題"],
        font_cfg["bold"],
        int(font_cfg["footer_size"]),
        int(font_cfg["minimum_size"]),
        (margin, 895, width - margin, 950),
        style["primary_color"],
        spacing=5,
    )

    _apply_branding(canvas, config, group, page_number)
    _save_canvas(canvas, output_path)


def compose_vendor_text(description: dict[str, str], group: str, page_number: int, config: dict[str, Any], output_path: Path) -> None:
    image_cfg = config["image"]
    font_cfg = config["font"]
    style = config["styles"][image_cfg["default_style"]]
    width, height = int(image_cfg["width"]), int(image_cfg["height"])
    margin = int(style["safe_margin"])
    canvas = _create_background(width, height, style)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((margin, 38, width - margin, 46), radius=4, fill=style["accent_color"])
    fit_text(draw, description["上標題"], font_cfg["bold"], int(font_cfg["title_size"]), int(font_cfg["minimum_size"]), (margin, 65, width - margin, 190), style["title_color"])
    panel = (margin, 220, width - margin, 850)
    draw.rounded_rectangle(panel, radius=int(style["corner_radius"]), fill=style["card_color"], outline=style["accent_color"], width=4)
    fit_text(draw, description["說明"], font_cfg["regular"], int(font_cfg["body_size"]), int(font_cfg["minimum_size"]), (panel[0] + 45, panel[1] + 40, panel[2] - 45, panel[3] - 40), style["body_color"], spacing=12)
    fit_text(draw, description["下標題"], font_cfg["bold"], int(font_cfg["footer_size"]), int(font_cfg["minimum_size"]), (margin, 865, width - margin, 945), style["primary_color"], spacing=5)
    _apply_branding(canvas, config, group, page_number)
    _save_canvas(canvas, output_path)


def verify_image(path: Path, expected_size: tuple[int, int] | None = None) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
        if expected_size:
            with Image.open(path) as image:
                if image.size != expected_size:
                    raise ShopAdsError(
                        "E401",
                        "VERIFY_OUTPUT",
                        f"圖片尺寸是 {image.width}×{image.height}，預期為 {expected_size[0]}×{expected_size[1]}。",
                        str(path),
                    )
    except ShopAdsError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise ShopAdsError(
            "E402", "VERIFY_OUTPUT", f"輸出圖片無法驗證：{exc}", str(path)
        ) from exc
