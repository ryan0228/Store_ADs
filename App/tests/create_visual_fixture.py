from __future__ import annotations

import shutil
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
        shutil.rmtree(target)
    group = target / "01"
    group.mkdir(parents=True)
    (target / "Prod_Description.md").write_text(
        "# 商品名稱\n測試商品\n# 使用情境\n日常質感生活\n# 商品說明\n用於版面驗證的測試商品。\n",
        encoding="utf-8",
    )
    (group / "Img_Description.md").write_text(
        "# 上標題\n簡約生活，從今天開始\n# 說明\n三款設計依序呈現，保留商品完整外觀與清楚資訊。\n# 下標題\n探索你的理想選擇\n",
        encoding="utf-8",
    )
    create_product_image(group / "01.png", "#355C7D", "商品 A")
    create_product_image(group / "02.png", "#C06C84", "商品 B")
    create_product_image(group / "03.png", "#6C5B7B", "商品 C")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
