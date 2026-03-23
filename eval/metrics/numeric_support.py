"""
Deterministic numeric-support heuristic for citation verification.
Checks whether simple threshold/rate claims in a response are numerically
consistent with conditions stated in the source passage.

This avoids relying on NLI for claims like "$30,000 is not over $36,900"
where DeBERTa cannot do arithmetic.

Entry point: numeric_support_check(passage_text, claim_text) -> dict
"""
import re

from eval.metrics.citation_utils import normalize_space


# -- Regex patterns for extracting numeric conditions --------------------------

_MONEY_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

_SUBJECT_THRESHOLD_PATTERNS = [
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:is|are|was|were|be|must be)\s+"
        r"(?P<comparator>not over|over|under|at least|at most|more than|less than)"
        r"\s+\$?(?P<value>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:is|are|was|were|be|must be)\s+"
        r"(?P<comparator>not over|over|under|at least|at most|more than|less than)"
        r"\s+(?P<value>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:must be\s+)?"
        r"(?P<comparator>under age|over age|at least age)\s+(?P<value>\d+)",
        re.IGNORECASE,
    ),
]

_GENERIC_THRESHOLD_PATTERNS = [
    re.compile(r"(?P<comparator>under age|over age|at least age)\s+(?P<value>\d+)", re.IGNORECASE),
    re.compile(
        r"(?P<comparator>not over|over|under|at least|at most|more than|less than)"
        r"\s+(?P<value>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
]

_HALF_PATTERNS = [
    (re.compile(r"\bmore than half\b", re.IGNORECASE), ">", 0.5),
    (re.compile(r"\bless than half\b", re.IGNORECASE), "<", 0.5),
    (re.compile(r"\bat least half\b", re.IGNORECASE), ">=", 0.5),
    (re.compile(r"\bnot over half\b", re.IGNORECASE), "<=", 0.5),
]

_SUBJECT_VALUE_PATTERNS = [
    re.compile(
        r"(?:with\s+)?(?P<subject>[a-z][a-z\s]{0,80}?)\s+of\s+\$?(?P<value>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:is|are|was|were)\s+\$?(?P<value>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:is|are|was|were|must be)\s+(?P<value>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<subject>[a-z][a-z\s]{0,80}?)\s+(?:must be\s+)?"
        r"(?:under age|over age|at least age)\s+(?P<value>\d+)",
        re.IGNORECASE,
    ),
]

_NOISE_SUBJECT_WORDS = {
    "the", "a", "an", "of", "for", "to", "and", "or", "is", "are", "was", "were",
    "be", "being", "been", "if", "with", "that", "this", "these", "those", "your",
    "their", "his", "her", "its", "my", "our", "in", "on", "at", "by", "from", "as",
    "who", "whom", "someone", "individual", "person", "taxpayer",
}


# -- Internal helpers ----------------------------------------------------------

def _parse_number(raw_value: str) -> float:
    """Parse a money/percent/age literal into a float."""
    return float(raw_value.replace(",", ""))


def _normalize_subject(subject: str) -> str:
    """Canonicalize a subject string for lightweight matching."""
    lowered = re.sub(r"[^a-z0-9\s]", " ", subject.lower())
    words = [w for w in lowered.split() if w and w not in _NOISE_SUBJECT_WORDS]
    return " ".join(words) if words else ""


def _comparator_symbol(raw_comparator: str) -> str:
    """Map language comparators to symbolic operators."""
    mapping = {
        "not over": "<=", "over": ">", "under": "<",
        "at least": ">=", "at most": "<=",
        "more than": ">", "less than": "<",
        "under age": "<", "over age": ">", "at least age": ">=",
    }
    return mapping[raw_comparator.lower().strip()]


def _compare_numeric(candidate: float, comparator: str, threshold: float) -> bool:
    """Evaluate a simple numeric comparator."""
    ops = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b,
           ">=": lambda a, b: a >= b, ">": lambda a, b: a > b}
    return ops[comparator](candidate, threshold)


def _extract_threshold_conditions(text: str) -> list[dict]:
    """Extract conservative threshold conditions from a passage."""
    lowered = normalize_space(text.lower())
    conditions = []

    for pattern in _SUBJECT_THRESHOLD_PATTERNS:
        for match in pattern.finditer(lowered):
            raw_subject = match.groupdict().get("subject", "") or ""
            raw_comparator = match.group("comparator")
            raw_value = match.group("value")
            unit = "money"
            if "%" in match.group(0):
                unit = "percent"
            elif "age" in raw_comparator:
                unit = "age"
                if not raw_subject:
                    raw_subject = "age"
            subject = _normalize_subject(raw_subject)
            if not subject:
                continue
            conditions.append({
                "unit": unit, "subject": subject,
                "comparator": _comparator_symbol(raw_comparator),
                "value": _parse_number(raw_value),
            })

    for pattern in _GENERIC_THRESHOLD_PATTERNS:
        for match in pattern.finditer(lowered):
            raw_comparator = match.group("comparator")
            raw_value = match.group("value")
            unit = "age" if "age" in raw_comparator else "percent"
            subject = "age" if unit == "age" else "rate"
            conditions.append({
                "unit": unit, "subject": subject,
                "comparator": _comparator_symbol(raw_comparator),
                "value": _parse_number(raw_value),
            })

    for pattern, comparator, threshold in _HALF_PATTERNS:
        if pattern.search(lowered):
            conditions.append({
                "unit": "fraction", "subject": "share",
                "comparator": comparator, "value": threshold,
            })

    # Deduplicate
    seen = set()
    deduped = []
    for c in conditions:
        key = (c["unit"], c["subject"], c["comparator"], c["value"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped


def _extract_rate_values(text: str) -> list[float]:
    """Extract percentage values from text."""
    return [_parse_number(m.group(1)) for m in _PERCENT_RE.finditer(text)]


def _extract_subject_values(text: str, unit: str, subject: str) -> list[float]:
    """Extract candidate numeric values associated with a subject in the claim."""
    lowered = normalize_space(text.lower())
    subject_words = subject.split()
    values = []

    for pattern in _SUBJECT_VALUE_PATTERNS:
        for match in pattern.finditer(lowered):
            raw_subject = match.groupdict().get("subject", "") or ""
            normalized_subject = _normalize_subject(raw_subject)
            if subject_words and not all(w in normalized_subject for w in subject_words):
                continue
            snippet = match.group(0)
            if unit == "money" and "$" not in snippet:
                continue
            if unit == "percent" and "%" not in snippet:
                continue
            if unit == "age" and "age" not in snippet:
                continue
            values.append(_parse_number(match.group("value")))

    if values:
        return values

    # Fallback: scan for money values near subject words
    for money_match in _MONEY_RE.finditer(lowered):
        if unit != "money":
            break
        window_start = max(0, money_match.start() - 60)
        window_end = min(len(lowered), money_match.end() + 25)
        window = lowered[window_start:window_end]
        if all(w in window for w in subject_words):
            values.append(_parse_number(money_match.group(1)))

    return values


def _supports_half_claim(claim_text: str, comparator: str) -> bool:
    """Check direct phrase support for half-threshold claims."""
    lowered = normalize_space(claim_text.lower())
    phrase_map = {
        ">": "more than half", "<": "less than half",
        ">=": "at least half", "<=": "not over half",
    }
    expected = phrase_map.get(comparator)
    return bool(expected and expected in lowered)


# -- Public entry point --------------------------------------------------------

def numeric_support_check(passage_text: str, claim_text: str) -> dict:
    """
    Try to prove support for simple numeric threshold/rate claims.

    Returns:
        {"applied": bool, "supported": bool}
    """
    conditions = _extract_threshold_conditions(passage_text)
    if not conditions:
        return {"applied": False, "supported": False}

    passage_rates = _extract_rate_values(passage_text)
    claim_rates = _extract_rate_values(claim_text)
    applied = False

    for condition in conditions:
        if condition["unit"] == "fraction":
            if _supports_half_claim(claim_text, condition["comparator"]):
                return {"applied": True, "supported": True}
            applied = True
            continue

        candidate_values = _extract_subject_values(
            claim_text, condition["unit"], condition["subject"]
        )
        if not candidate_values:
            continue

        applied = True
        threshold_satisfied = any(
            _compare_numeric(v, condition["comparator"], condition["value"])
            for v in candidate_values
        )
        if not threshold_satisfied:
            continue

        if condition["unit"] == "money" and passage_rates and claim_rates:
            if not any(cr in passage_rates for cr in claim_rates):
                continue

        return {"applied": True, "supported": True}

    return {"applied": applied, "supported": False}
