from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .errors import ShopAdsError
from .manifest import write_json_atomic
from .markdown import parse_sections
from .validation import inspect_job


LAYOUT_COUNTS = {"hero": 1, "two_cards": 2, "three_cards": 3, "four_grid": 4}


def normalize_output_names(payload: dict[str, Any]) -> dict[str, Any]:
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for index, item in enumerate(outputs, start=1):
            if isinstance(item, dict):
                item["output"] = f"{index:02d}.{'gif' if item.get('type') == 'gif' else 'png'}"
    return payload


def validate_plan(payload: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ShopAdsError("E601", "AI_PLAN", "AI Plan schema_version 必須為 1。")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ShopAdsError("E602", "AI_PLAN", "AI Plan 沒有成品計畫。")
    job = inspect_job(job_dir)
    available = {item.name: item for item in job.images}
    animated_names = {item.name for item in job.animated_gifs}
    planned_animated: list[str] = []
    seen_outputs: set[str] = set()
    for index, item in enumerate(outputs, start=1):
        if not isinstance(item, dict):
            raise ShopAdsError("E603", "AI_PLAN", f"第 {index} 筆成品格式錯誤。")
        kind = item.get("type")
        expected = f"{index:02d}.{'gif' if kind == 'gif' else 'png'}"
        if item.get("output") != expected or expected in seen_outputs:
            raise ShopAdsError("E604", "AI_PLAN", f"成品必須連續命名，預期 {expected}。")
        seen_outputs.add(expected)
        names = item.get("images")
        if not isinstance(names, list) or (kind != "text" and not names):
            raise ShopAdsError("E605", "AI_PLAN", f"{expected} 沒有來源圖片。")
        missing = [name for name in names if name not in available]
        if missing:
            raise ShopAdsError("E606", "AI_PLAN", f"{expected} 引用不存在的圖片：{', '.join(missing)}。")
        if kind == "gif":
            if len(names) != 1 or names[0] not in animated_names or item.get("layout") != "original_gif":
                raise ShopAdsError("E607", "AI_PLAN", f"{expected} 的 GIF 計畫不合法。")
            planned_animated.append(names[0])
        elif kind == "static":
            layout = item.get("layout")
            if layout not in LAYOUT_COUNTS or len(names) != LAYOUT_COUNTS[layout]:
                raise ShopAdsError("E608", "AI_PLAN", f"{expected} 的版型與圖片數量不符。")
            if any(name in animated_names for name in names):
                raise ShopAdsError("E609", "AI_PLAN", f"{expected} 不可將動畫 GIF 當靜態圖合成。")
            for field in ("top_title", "description", "bottom_title"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ShopAdsError("E610", "AI_PLAN", f"{expected} 缺少 {field}。")
        elif kind == "text":
            if item.get("layout") != "vendor_text" or names:
                raise ShopAdsError("E611", "AI_PLAN", f"{expected} 的商品資訊摘要頁不可引用圖片。")
            if index != len(outputs):
                raise ShopAdsError("E614", "AI_PLAN", "商品資訊摘要頁必須是最後一張成品。")
            for field in ("top_title", "description", "bottom_title"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ShopAdsError("E610", "AI_PLAN", f"{expected} 缺少 {field}。")
        else:
            raise ShopAdsError("E611", "AI_PLAN", f"{expected} 的 type 必須為 static、gif 或 text。")
    product = parse_sections(job_dir / "Product_Description.md", ("商品名稱", "商品說明"))
    vendor_text = product.get("廠商文字說明", "")
    planned_text = [item for item in outputs if item.get("type") == "text"]
    if vendor_text.strip() and len(planned_text) != 1:
        raise ShopAdsError("E615", "AI_PLAN", "有廠商文字說明時，必須產生一張最後資訊圖。")
    if len(planned_text) > 1:
        raise ShopAdsError("E616", "AI_PLAN", "商品資訊摘要頁最多只能產生一張。")
    if sorted(planned_animated) != sorted(animated_names):
        raise ShopAdsError("E617", "AI_PLAN", "每個動畫 GIF 必須在計畫中恰好出現一次。", suggestion="不可排除、遺漏或重複使用動畫 GIF。")
    payload["product"] = product
    return payload


def save_plan(job_dir: Path, payload: dict[str, Any]) -> Path:
    normalize_output_names(payload)
    validate_plan(payload, job_dir)
    path = job_dir / "Work" / "ai-plan.json"
    write_json_atomic(path, payload)
    write_preview(job_dir, payload)
    return path


def load_plan(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "Work" / "ai-plan.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ShopAdsError("E612", "AI_PLAN", "找不到 AI Plan。", str(path), "請先執行 analyze。") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ShopAdsError("E613", "AI_PLAN", f"AI Plan 無法讀取：{exc}", str(path)) from exc
    return validate_plan(payload, job_dir)


def write_preview(job_dir: Path, payload: dict[str, Any]) -> Path:
    cards: list[str] = []
    for item in payload["outputs"]:
        text = "GIF 原樣複製" if item["type"] == "gif" else (
            f"<b>上標題：</b>{html.escape(item['top_title'])}<br>"
            f"<b>說明：</b>{html.escape(item['description'])}<br>"
            f"<b>下標題：</b>{html.escape(item['bottom_title'])}"
        )
        cards.append(f"<section><h2>{html.escape(item['output'])}</h2><p><b>版型：</b>{html.escape(item['layout'])}</p><p><b>來源：</b>{html.escape(', '.join(item['images']))}</p><p>{text}</p></section>")
    rejected = payload.get("rejected", [])
    rejected_html = "".join(f"<li>{html.escape(str(x.get('image','')))}：{html.escape(str(x.get('reason','')))}</li>" for x in rejected if isinstance(x, dict))
    document = "<!doctype html><meta charset='utf-8'><title>ShopAds AI Plan</title><style>body{font-family:'Microsoft JhengHei',sans-serif;max-width:900px;margin:40px auto;background:#f7f5f2;color:#222}section{background:white;padding:18px 24px;margin:18px 0;border-radius:16px}code{background:#eee;padding:2px 6px}</style>" + f"<h1>{html.escape(job_dir.name)} AI 生成計畫</h1>" + "".join(cards) + f"<h2>未採用圖片</h2><ul>{rejected_html or '<li>無</li>'}</ul><p>確認內容後執行 <code>generate</code>。</p>"
    path = job_dir / "Work" / "preview.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path
