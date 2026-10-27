from __future__ import annotations

import json


RISK_LEVEL_ALIASES = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "critical": "high",
    "低": "low",
    "中": "medium",
    "高": "high",
    "低风险": "low",
    "中风险": "medium",
    "高风险": "high",
    "低危": "low",
    "中危": "medium",
    "高危": "high",
}


RISK_LEVEL_LABELS = {
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
    "critical": "高风险",
}


def parse_json_response(text: str, *, error_cls=RuntimeError) -> dict:
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        lines = [line for line in candidate.splitlines() if not line.strip().startswith("```")]
        candidate = "\n".join(lines).strip()

    if not candidate:
        raise error_cls("模型返回内容为空")

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError as error:
                raise error_cls("模型返回的 JSON 无法解析") from error
        raise error_cls("模型未返回有效 JSON")


def normalize_risk_level(value) -> str | None:
    if not value:
        return None

    text = str(value).strip().lower()
    if text in RISK_LEVEL_ALIASES:
        return RISK_LEVEL_ALIASES[text]

    for alias, normalized in RISK_LEVEL_ALIASES.items():
        if alias in text:
            return normalized
    return None


def clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return " ".join(text.split())
