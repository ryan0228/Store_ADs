from __future__ import annotations

import copy
import sys
import tomllib
from pathlib import Path
from typing import Any

from .errors import ShopAdsError


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {"work_root": r"D:\CASE\Shop_ADs"},
    "image": {
        "width": 1080,
        "height": 1080,
        "default_style": "clean",
        "max_images_per_page": 4,
        "output_format": "png",
    },
    "ai": {
        "provider": "openai",
        "model": "",
        "analysis_max_dimension": 768,
        "max_input_images": 15,
        "gif_frame_analysis": True,
    },
    "branding": {
        "store_name": "情趣時光",
        "footer_image": "assets/branding/shop-footer.png",
        "footer_width": 250,
        "footer_margin": 28,
    },
    "font": {
        "regular": r"C:\Windows\Fonts\msjh.ttc",
        "bold": r"C:\Windows\Fonts\msjhbd.ttc",
        "title_size": 68,
        "body_size": 36,
        "footer_size": 42,
        "minimum_size": 22,
    },
    "styles": {
        "clean": {
            "background_color": "#F7F5F2",
            "primary_color": "#234E70",
            "accent_color": "#F2B134",
            "title_color": "#222222",
            "body_color": "#444444",
            "card_color": "#FFFFFF",
            "border_color": "#FFFFFF",
            "safe_margin": 72,
            "corner_radius": 26,
            "shadow_blur": 18,
            "rotation_degrees": 2.0,
        }
    },
}

JOB_OVERRIDE_KEYS = {"image", "font", "styles"}


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _read_toml(path: Path, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ShopAdsError(
                "E001",
                "LOAD_CONFIG",
                "找不到設定檔。",
                str(path),
                "確認 config.toml 與程式放在同一目錄，或使用 --config 指定。",
            )
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ShopAdsError(
            "E002", "LOAD_CONFIG", f"設定檔無法讀取：{exc}", str(path)
        ) from exc


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(config_path: Path | None, job_dir: Path | None = None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    selected = config_path or application_dir() / "config.toml"
    _deep_merge(config, _read_toml(selected, required=True))
    local_path = selected.with_name("config.local.toml")
    _deep_merge(config, _read_toml(local_path))

    if job_dir:
        job_settings = _read_toml(job_dir / "job.toml")
        forbidden = sorted(set(job_settings) - JOB_OVERRIDE_KEYS)
        if forbidden:
            raise ShopAdsError(
                "E004",
                "LOAD_CONFIG",
                f"job.toml 包含不允許覆寫的區段：{', '.join(forbidden)}",
                str(job_dir / "job.toml"),
            )
        _deep_merge(config, job_settings)

    validate_config(config)
    config["_config_path"] = str(selected.resolve())
    config["_local_config_path"] = str(local_path.resolve())
    return config


def validate_config(config: dict[str, Any]) -> None:
    image = config.get("image", {})
    if image.get("width") != 1080 or image.get("height") != 1080:
        raise ShopAdsError(
            "E005", "LOAD_CONFIG", "第一階段輸出尺寸必須為 1080×1080。"
        )
    if image.get("max_images_per_page") != 4:
        raise ShopAdsError(
            "E006", "LOAD_CONFIG", "AI 版型每頁圖片上限必須為 4。"
        )
    style_name = image.get("default_style", "clean")
    if style_name not in config.get("styles", {}):
        raise ShopAdsError(
            "E007", "LOAD_CONFIG", f"找不到版型設定：{style_name}。"
        )
    for font_key in ("regular", "bold"):
        font_path = Path(config.get("font", {}).get(font_key, ""))
        if not font_path.is_file():
            raise ShopAdsError(
                "E008",
                "LOAD_CONFIG",
                f"找不到 {font_key} 字型。",
                str(font_path),
                "請在 config.toml 指定可顯示繁體中文的字型。",
            )
    branding = config.get("branding", {})
    footer_path = Path(str(branding.get("footer_image", "")))
    if not footer_path.is_absolute():
        footer_path = application_dir() / footer_path
    if not footer_path.is_file():
        raise ShopAdsError("E009", "LOAD_CONFIG", "找不到店鋪品牌頁尾圖片。", str(footer_path))
    config["branding"]["_footer_image_path"] = str(footer_path.resolve())
