from __future__ import annotations

import re
from pathlib import Path

from .errors import ShopAdsError


HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


def parse_sections(path: Path, required: tuple[str, ...]) -> dict[str, str]:
    if not path.is_file():
        raise ShopAdsError(
            "E101",
            "READ_DESCRIPTION",
            "找不到必要的 Markdown 說明檔。",
            str(path),
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ShopAdsError(
            "E102", "READ_DESCRIPTION", f"Markdown 無法以 UTF-8 讀取：{exc}", str(path)
        ) from exc

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    result = {key: "\n".join(value).strip() for key, value in sections.items()}
    missing = [name for name in required if not result.get(name)]
    if missing:
        raise ShopAdsError(
            "E103",
            "READ_DESCRIPTION",
            f"Markdown 缺少內容：{', '.join(missing)}。",
            str(path),
            "使用 Markdown 標題建立欄位，並在標題下填入文字。",
        )
    return {name: result[name] for name in required}
