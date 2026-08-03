from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ShopAdsError(Exception):
    code: str
    stage: str
    message: str
    path: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.code}][{self.stage}]", self.message]
        if self.path:
            parts.append(f"路徑：{self.path}")
        if self.suggestion:
            parts.append(f"建議：{self.suggestion}")
        return "\n".join(parts)

    def as_dict(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
        }
        if self.path:
            result["path"] = self.path
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result
