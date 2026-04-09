from __future__ import annotations

from typing import Any, Dict


YES_VALUES = {"yes", "y", "true", "t", "1"}
NO_VALUES = {"no", "n", "false", "f", "0"}

ALIASES = {
    "marital_status": "marital_status_on_1231",
    "spouse_joint": "spouse_willing_to_file_jointly",
    "joint_filing": "spouse_willing_to_file_jointly",
    "charity_cash": "charitable_cash_contributions",
    "charity_noncash": "charitable_noncash_contributions",
    "charity_documented": "charitable_contributions_documented",
}


def _normalize_bool(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in YES_VALUES:
            return True
        if lowered in NO_VALUES:
            return False
    return value


def normalize_user_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a small set of user-facing aliases into repo-style field names."""
    normalized: Dict[str, Any] = {}
    for key, value in facts.items():
        canonical_key = ALIASES.get(key, key)
        normalized[canonical_key] = _normalize_bool(value)

    marital_status = normalized.get("marital_status_on_1231")
    if isinstance(marital_status, str):
        normalized["marital_status_on_1231"] = marital_status.strip().lower()

    fed = normalized.get("federal_tax_residency")
    if isinstance(fed, str):
        normalized["federal_tax_residency"] = fed.strip().lower().replace(" ", "_")

    return normalized


def merge_fact_updates(current_facts: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current_facts)
    merged.update(updates)
    return normalize_user_facts(merged)


def has_any_charitable_contribution(facts: Dict[str, Any]) -> bool:
    cash = facts.get("charitable_cash_contributions", 0) or 0
    noncash = facts.get("charitable_noncash_contributions", 0) or 0
    return cash > 0 or noncash > 0
