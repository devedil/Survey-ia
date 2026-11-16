import re
import unicodedata


def normalize_fact_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def find_fact_contradictions(facts: list[dict]) -> list[str]:
    grouped: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for fact in facts:
        key = normalize_fact_value(fact["field_name"])
        grouped.setdefault(key, set()).add(normalize_fact_value(fact["value"]))
        labels[key] = fact["field_name"]
    return [labels[key] for key, values in grouped.items() if len(values) > 1]
