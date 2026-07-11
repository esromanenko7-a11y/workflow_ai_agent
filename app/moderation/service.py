import hashlib
import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.moderation.schemas import ModerationResult


logger = structlog.get_logger(__name__)


DEFAULT_KEYWORDS_PATH = Path("moderation_keywords.yaml")


def _normalize_text(content: str) -> str:
    return content.lower().strip()


def _text_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _mask_for_log(content: str) -> str:
    """
    Минимальная маскировка для логов.

    Сырой текст в moderation incident не пишем.
    Здесь закрываем частые PII-паттерны: email, телефоны, карты.
    """
    masked = re.sub(
        r"[\w\.-]+@[\w\.-]+\.\w+",
        "[EMAIL]",
        content,
    )
    masked = re.sub(
        r"\+?\d[\d\s\-\(\)]{8,}\d",
        "[PHONE]",
        masked,
    )
    masked = re.sub(
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "[CARD]",
        masked,
    )

    if len(masked) > 200:
        return masked[:200] + "..."

    return masked


class ModerationService:
    def __init__(
        self,
        keywords_path: Path | str = DEFAULT_KEYWORDS_PATH,
        use_openai: bool = False,
    ) -> None:
        self.keywords_path = Path(keywords_path)
        self.use_openai = use_openai
        self.rules = self._load_rules()

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self.keywords_path.exists():
            return []

        data = yaml.safe_load(
            self.keywords_path.read_text(encoding="utf-8"),
        ) or {}

        rules = data.get("rules", [])

        if not isinstance(rules, list):
            return []

        return rules

    def check_input(self, content: str) -> ModerationResult:
        return self._check_keywords(
            content=content,
            direction="input",
        )

    def check_output(self, content: str) -> ModerationResult:
        return self._check_keywords(
            content=content,
            direction="output",
        )

    def _check_keywords(
        self,
        content: str,
        direction: str,
    ) -> ModerationResult:
        normalized = _normalize_text(content)

        categories: list[str] = []
        reasons: list[str] = []

        for rule in self.rules:
            category = str(rule.get("category", "unknown"))
            reason = str(rule.get("reason", "Blocked by moderation rule"))
            patterns = rule.get("patterns", [])

            if not isinstance(patterns, list):
                continue

            for pattern in patterns:
                pattern_text = str(pattern).lower()

                if not pattern_text:
                    continue

                if re.search(pattern_text, normalized):
                    categories.append(category)
                    reasons.append(reason)
                    break

        if not categories:
            return ModerationResult(
                allowed=True,
            )

        unique_categories = list(dict.fromkeys(categories))
        unique_reasons = list(dict.fromkeys(reasons))

        logger.warning(
            "moderation_blocked",
            direction=direction,
            text_hash=_text_hash(content),
            masked_text=_mask_for_log(content),
            categories=unique_categories,
            blocked_by="keyword",
        )

        return ModerationResult(
            allowed=False,
            categories=unique_categories,
            reasons=unique_reasons,
            blocked_by="keyword",
        )
