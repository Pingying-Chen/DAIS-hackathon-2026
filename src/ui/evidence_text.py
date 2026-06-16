from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


CLAIM_LABELS = {
    "specialties": "Specialties",
    "procedure": "Procedures",
    "equipment": "Equipment",
    "capability": "Capability",
    "description": "Description",
    "nfhs_need": "District need",
    "facility_density": "Local supply",
}

KNOWN_ACRONYMS = {"icu", "nicu", "opd", "ent", "ct", "mri", "usg", "ivf", "ot"}


def claim_label(value: Any) -> str:
    text = _clean_text(value, "Source note")
    return CLAIM_LABELS.get(text.casefold(), text.replace("_", " ").replace("-", " ").title())


def evidence_sentence(claim_type: Any, evidence: Any) -> str:
    claim = _clean_text(claim_type, "description").casefold()
    values = _evidence_values(evidence)
    if not values:
        return "No readable source detail is available yet."

    joined = _join_values(values)
    if claim == "specialties":
        return f"Listed specialties include {joined}."
    if claim == "procedure":
        return f"Listed procedures include {joined}."
    if claim == "equipment":
        return f"Listed equipment includes {joined}."
    if claim == "capability":
        return f"Capability note: {joined}."
    if claim == "description":
        return f"Facility description: {joined}."
    if claim == "nfhs_need":
        return f"District need context: {joined}."
    if claim == "facility_density":
        return f"Local supply context: {joined}."
    return joined if joined.endswith(".") else f"{joined}."


def source_note(value: Any) -> str:
    text = _clean_text(value, "")
    if not text:
        return "Source: provided facility data"
    if text.startswith("unity-catalog://"):
        return "Source: provided district dataset"
    parsed = urlparse(text)
    if parsed.netloc:
        return f"Source: {parsed.netloc}"
    return "Source: provided facility data"


def _evidence_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return _dedupe(_humanize_token(item) for item in value)

    text = _clean_text(value, "")
    if not text:
        return []

    parsed = _json_values(text)
    if parsed:
        return parsed

    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    if quoted:
        return _dedupe(_humanize_token(first or second) for first, second in quoted)

    separators = [";", "\n"]
    for separator in separators:
        if separator in text:
            return _dedupe(_humanize_token(part) for part in text.split(separator))
    return [_humanize_token(text)]


def _json_values(text: str) -> list[str]:
    if not text.startswith(("[", "{")):
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        parsed = list(parsed.values())
    if not isinstance(parsed, list):
        return []
    flattened: list[Any] = []
    for item in parsed:
        if isinstance(item, list):
            flattened.extend(item)
        else:
            flattened.append(item)
    return _dedupe(_humanize_token(item) for item in flattened)


def _humanize_token(value: Any) -> str:
    text = _clean_text(value, "")
    text = text.strip("[]{}")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,.;")
    if not text:
        return ""

    words = []
    for word in text.split(" "):
        stripped = word.strip()
        if not stripped:
            continue
        if stripped.casefold() in KNOWN_ACRONYMS or stripped.isupper():
            words.append(stripped.upper())
        elif any(character.isdigit() for character in stripped):
            words.append(stripped)
        else:
            words.append(stripped.casefold())
    if not words:
        return ""
    result = " ".join(words)
    return result[0].upper() + result[1:]


def _join_values(values: list[str]) -> str:
    clean_values = [value for value in values if value]
    if not clean_values:
        return "no readable details"
    if len(clean_values) == 1:
        return clean_values[0]
    if len(clean_values) == 2:
        return f"{clean_values[0]} and {clean_values[1]}"
    return f"{', '.join(clean_values[:-1])}, and {clean_values[-1]}"


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _clean_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null", "n/a", "na", "unknown"}:
        return fallback
    return text
