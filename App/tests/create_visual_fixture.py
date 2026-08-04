from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_product_image(path: Path, color: str, label: str) -> None:
    image = Image.new("RGB", (600, 760), "#F4F4F4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((90, 75, 510, 685), radius=45, fill=color)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 60)
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text(((600 - (bbox[2] - bbox[0])) / 2, 335), label, font=font, fill="white")
    image.save(path)


def main(target: Path) -> None:
    if target.exists():
        raise SystemExit(f"Target already exists: {target}")
    input_dir = target / "Input"
    work_dir = target / "Work"
    input_dir.mkdir(parents=True)
    work_dir.mkdir()
    (target / "Product_Description.md").write_text("# 商品名稱\n測試商品\n# 商品說明\n用於品牌版面驗證。\n# 商品用途\n日常質感生活\n# 廠商文字說明\n日本語の商品説明を繁体字中国語で紹介します。\n", encoding="utf-8")
    create_product_image(input_dir / "01.png", "#355C7D", "商品 A")
    create_product_image(input_dir / "02.png", "#C06C84", "商品 B")
    create_product_image(input_dir / "03.png", "#6C5B7B", "商品 C")
    plan = {
        "schema_version": 1,
        "outputs": [
            {"output": "01.png", "type": "static", "layout": "three_cards", "images": ["01.png", "02.png", "03.png"], "top_title": "簡約生活，從今天開始", "description": "保留商品完整外觀與清楚資訊", "bottom_title": "探索理想選擇"},
            {"output": "02.png", "type": "text", "layout": "vendor_text", "images": [], "top_title": "廠商商品資訊", "description": "• 廠商日文說明已翻譯為繁體中文\n• 文字經過整理，方便快速閱讀\n• 實際內容請以商品標示為準", "bottom_title": "購買前請詳閱"},
        ],
        "rejected": [],
    }
    (work_dir / "ai-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
