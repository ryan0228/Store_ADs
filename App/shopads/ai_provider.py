from __future__ import annotations

import base64
import io
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .errors import ShopAdsError


LOGGER = logging.getLogger("shopads")


PLAN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "integer"},
        "outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "output": {"type": "string"},
                    "type": {"type": "string", "enum": ["static", "gif", "text"]},
                    "layout": {"type": "string", "enum": ["hero", "two_cards", "original_gif", "vendor_text"]},
                    "images": {"type": "array", "items": {"type": "string"}},
                    "top_title": {"type": "string"},
                    "description": {"type": "string"},
                    "bottom_title": {"type": "string"},
                },
                "required": ["output", "type", "layout", "images", "top_title", "description", "bottom_title"],
            },
        },
        "rejected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"image": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["image", "reason"],
            },
        },
    },
    "required": ["schema_version", "outputs", "rejected"],
}


def _analysis_image(path: Path, maximum: int) -> tuple[str, str]:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=82, optimize=True)
    except OSError as exc:
        raise ShopAdsError("E620", "AI_ANALYZE", f"無法建立分析副本：{exc}", str(path)) from exc
    return path.name, base64.b64encode(stream.getvalue()).decode("ascii")


def _analysis_gif_preview(path: Path, maximum: int) -> tuple[str, str]:
    try:
        with Image.open(path) as source:
            frame_count = int(getattr(source, "n_frames", 1))
            indices = (0, frame_count // 2, frame_count - 1)
            tile_size = max(128, maximum // 3)
            preview = Image.new("RGB", (tile_size * 3, tile_size), "white")
            for column, index in enumerate(indices):
                source.seek(index)
                frame = source.convert("RGBA")
                frame.thumbnail((tile_size, tile_size), Image.Resampling.LANCZOS)
                background = Image.new("RGBA", frame.size, "white")
                background.alpha_composite(frame)
                x = column * tile_size + (tile_size - frame.width) // 2
                y = (tile_size - frame.height) // 2
                preview.paste(background.convert("RGB"), (x, y))
            stream = io.BytesIO()
            preview.save(stream, format="JPEG", quality=82, optimize=True)
    except (OSError, EOFError) as exc:
        raise ShopAdsError("E629", "AI_ANALYZE", f"無法建立動畫 GIF 代表影格：{exc}", str(path)) from exc
    return f"{path.name}（動畫首／中／末影格）", base64.b64encode(stream.getvalue()).decode("ascii")


def _prompt(product: dict[str, str], static_names: list[str], gif_names: list[str], summary_min_facts: int = 3) -> str:
    return f"""你是商品廣告圖片規劃器。只根據提供的繁體中文商品資料與圖片規劃，不可發明尺寸、材質、價格、產地、結構、功能、功效或保證。圖片只能支持顏色、形狀、畫面配置等直接可見的外觀描述；材質、結構、功能與效果性文字必須能在商品資料原文或圖片清楚文字中直接找到依據，不可從外觀猜測或擴寫，例如原文寫「360度按摩頭」時不可自行加上「可彎曲」。你可以根據已確認的商品特性生成簡短、有吸引力但不誇大的繁體中文文案，並與 Product_Description.md 既有文字及圖片文字合併去重；即使描述檔只有基本資料，也要為一般圖片頁產生自然短文案。不可生成、修改或換背景；只選擇、排序、分組原圖並撰寫短文案。靜態圖（包含單影格 GIF）每張成品最多使用 2 張，版型與數量必須對應 hero=1、two_cards=2；需要更多圖片時拆成更多成品，不可使用三圖或四宮格。多影格動畫 GIF 已提供首／中／末代表影格預覽；每個動畫必須恰好安排一次、不可排除、不與其他圖合併，使用 original_gif。輸出依展示順序連續命名 01.png/01.gif。可排除重複、模糊或低價值的靜態圖片，但列出原因。全部文字使用繁體中文。

商品資料：{json.dumps(product, ensure_ascii=False)}
若「商品用途」留白，請只根據商品名稱、商品說明與可見圖片推導中性的使用情境，不得加入無依據功效。
靜態檔名（單影格 GIF 也在此）：{json.dumps(static_names, ensure_ascii=False)}
動畫 GIF 檔名：{json.dumps(gif_names, ensure_ascii=False)}
最後摘要頁規則：同時讀取商品資料與圖片中清楚可辨識的文字，整理功能、材質、操作、規格、尺寸、配件等具體資訊；相同資訊只保留一次，不可猜測看不清楚的文字，也不可新增來源沒有的宣稱。先根據確認資訊生成一段簡短自然的「商品亮點」文案，再接續分類規格；商品亮點要與 Product_Description.md 既有文案合併去重，不論原檔是否已提供完整宣傳句都要重新整理，不可只是逐字複製。若「廠商文字說明」有內容，必須辨識語言並翻譯／整理為繁體中文，且一定產生摘要頁。若沒有廠商文字，只有在去除重複後至少有 {summary_min_facts} 項具體且可驗證的資訊時才產生；資訊不足就不要勉強產生。摘要頁在 outputs 最後加入且最多一筆，使用 type=text、layout=vendor_text、images=[]；上標題使用「商品資訊總覽」或貼近內容的名稱，description 以「商品亮點」開頭，再以清楚分行的精簡重點呈現。

只回傳 JSON 物件，格式為 schema_version=1、outputs 陣列、rejected 陣列。每個 output 都包含 output、type、layout、images、top_title、description、bottom_title；gif 的三個文字欄位填空字串。"""


def _request_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="POST")
    transient_codes = {429, 500, 502, 503, 504}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                error = error_payload.get("error", {})
                status = str(error.get("status", "")).strip()
                message = str(error.get("message", "")).strip()
                detail = ": ".join(item for item in (status, message) if item)[:500]
                for secret in headers.values():
                    if len(secret) >= 8:
                        detail = detail.replace(secret, "***")
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                detail = ""
            if exc.code in transient_codes and attempt < 2:
                LOGGER.warning("[AI_ANALYZE] AI API 暫時回應 HTTP %d；%d 秒後進行第 %d/3 次嘗試。", exc.code, 2 ** attempt, attempt + 2)
                time.sleep(2 ** attempt)
                continue
            suffix = f"（{detail}）" if detail else ""
            raise ShopAdsError("E621", "AI_ANALYZE", f"AI API 回應 HTTP {exc.code}{suffix}。", suggestion="確認 API key、模型、額度與網路後重試。") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ShopAdsError("E622", "AI_ANALYZE", f"AI API 無法完成：{type(exc).__name__}。", suggestion="確認網路與 Provider 設定後重試。") from exc
    raise AssertionError("unreachable")


def analyze(job: Any, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ai = config.get("ai", {})
    provider = str(ai.get("provider", "")).casefold()
    model = str(ai.get("model", "")).strip()
    providers = ai.get("providers", {})
    api_key = str(providers.get(provider, {}).get("api_key", "")).strip()
    if not model:
        raise ShopAdsError("E623", "AI_ANALYZE", "尚未設定 AI model。", config.get("_config_path"))
    if not api_key:
        raise ShopAdsError("E624", "AI_ANALYZE", f"找不到 {provider} API key。", config.get("_local_config_path"), "複製 config.local.example.toml 為 config.local.toml 後填入金鑰。")
    maximum = int(ai.get("analysis_max_dimension", 768))
    images = [_analysis_image(path, maximum) for path in job.static_images]
    if bool(ai.get("gif_frame_analysis", True)):
        images.extend(_analysis_gif_preview(path, maximum) for path in job.animated_gifs)
    prompt = _prompt(job.product, [path.name for path in job.static_images], [path.name for path in job.animated_gifs], int(ai.get("summary_min_facts", 3)))
    if provider == "openai":
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for label, data in images:
            content.append({"type": "input_text", "text": f"分析資產：{label}"})
            content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{data}", "detail": "low"})
        response = _request_json("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {api_key}"}, {"model": model, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_object"}}})
        text = response.get("output_text")
        if not text:
            parts = [part.get("text", "") for item in response.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text"]
            text = "".join(parts)
        usage = response.get("usage", {})
    elif provider == "google":
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for label, data in images:
            parts.append({"text": f"分析資產：{label}"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": data}})
        response = _request_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": api_key}, {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": PLAN_RESPONSE_SCHEMA}})
        try:
            text = response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ShopAdsError("E625", "AI_ANALYZE", "Google AI 回應沒有可用內容。") from exc
        usage = response.get("usageMetadata", {})
    else:
        raise ShopAdsError("E626", "AI_ANALYZE", f"不支援的 AI Provider：{provider}。")
    cleaned = str(text).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    try:
        return json.loads(cleaned.strip()), {"provider": provider, "model": model, "usage": usage}
    except json.JSONDecodeError as exc:
        raise ShopAdsError("E627", "AI_ANALYZE", "AI 未回傳合法 JSON。") from exc
