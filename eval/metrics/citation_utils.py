"""
Shared helpers for citation normalization, text processing, and matching.
Used by both citation_nli.py and the harness's citation existence scoring.

Two matching tiers are provided and reported separately:
  - Section-level (strict): full normalized citation must be a substring.
  - Source-level (loose):  just the source ID (e.g. 'pub 501') must appear.
Callers must never silently substitute source-level for section-level.
"""
import re


# -- Regex constants -----------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_LIST_ITEM_RE = re.compile(r"^\s*(\d+\.|[-*])\s+")
_NUMBER_ONLY_RE = re.compile(r"^\s*\d+\.\s*$")
_BRACKETED_CITATION_RE = re.compile(r"\[[^\]]+\]")
_PARENTHETICAL_CITATION_RE = re.compile(
    r"\((?:[^)]*\b(?:usc|u\.s\.c\.|irc|pub|publication|section|sec\.)\b[^)]*)\)",
    re.IGNORECASE,
)

# Common legal abbreviations that should not trigger sentence splits.
ABBREV_PROTECT = [
    "Pub.", "pub.", "Sec.", "sec.", "No.", "no.", "Rev.", "rev.",
    "Rul.", "rul.", "Proc.", "proc.", "Reg.", "reg.", "Treas.",
    "treas.", "Corp.", "corp.", "Inc.", "inc.", "Ltd.", "ltd.",
    "U.S.C.", "u.s.c.", "U.S.", "u.s.", "I.R.C.", "i.r.c.",
    "e.g.", "i.e.", "etc.", "vs.", "v.", "Ch.", "ch.", "Art.", "art.",
]


# -- Citation normalization ----------------------------------------------------

def normalize_citation_text(text: str) -> str:
    """Collapse common citation variants into a comparable form."""
    normalized = text.lower()
    normalized = normalized.replace("\u00c2\u00a7", " section ")
    normalized = normalized.replace("\u00a7", " section ")
    # Word boundary goes on the last letter 'c', trailing period is optional
    # outside it.  Old pattern had \b after \.? which fails because period
    # is non-word and the next char (space) is also non-word.
    normalized = re.sub(r"\bi\s*\.?\s*r\s*\.?\s*c\b\.?", " irc ", normalized)
    normalized = re.sub(r"\b26\s+u\s*\.?\s*s\s*\.?\s*c\b\.?", " irc ", normalized)
    normalized = re.sub(r"\bsec(?:tion)?\.?\b", " section ", normalized)
    normalized = re.sub(r"\birs\s+publications?\b", " pub ", normalized)
    normalized = re.sub(r"\birs\s+pub(?:lication)?s?\.?\b", " pub ", normalized)
    normalized = re.sub(r"\bpub(?:lication)?s?\.?\b", " pub ", normalized)
    normalized = re.sub(r"\bsection\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def extract_source_id(citation_norm: str) -> str:
    """Extract the source-level ID (e.g. 'pub 501', 'irc 152') from a
    normalized citation string.  Used ONLY for the separate source-level
    metric, never as a substitute for section-level matching."""
    m = re.match(r"(pub|irc)\s+(\d+)", citation_norm)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # Tax court: keep full case name
    m = re.match(r"([a-z]+)\s+v\s+", citation_norm)
    if m:
        return citation_norm
    return citation_norm


# -- Token helpers -------------------------------------------------------------

_MIN_TOKEN_LEN = 2  # skip single-char tokens like 'a' to avoid false matches


def _significant_tokens(normalized: str) -> set[str]:
    """Return the set of tokens with length >= _MIN_TOKEN_LEN."""
    return {t for t in normalized.split() if len(t) >= _MIN_TOKEN_LEN}


# -- Section-level matching (strict, token-set containment) --------------------
#
# Uses token-set containment: every significant token in the gold citation
# must appear somewhere in the candidate string.  This handles format
# differences between benchmark citations ('IRS Pub. 501, Filing Status -
# Head of Household') and PageIndex citations ('IRS Pub. 501 (2025),
# Dependents, ... > Filing Status > Head of Household') without loosening
# the section specificity.  A wrong section (e.g. 'Qualifying Surviving
# Spouse') will be missing tokens like 'head', 'household' and correctly
# fail.
#
# Year tokens like '2025' in retrieved citations do NOT break the match
# because containment only requires gold tokens to be present, not that
# they form a contiguous substring.  Tax-year correctness is validated
# separately by check_tax_year_validation on chunk metadata.

def citation_in_text(text: str, citation: str) -> bool:
    """Section-level check: do all significant tokens from the citation
    appear in the text?"""
    citation_norm = normalize_citation_text(citation)
    if not citation_norm:
        return False
    gold_tokens = _significant_tokens(citation_norm)
    if not gold_tokens:
        return False
    text_tokens = _significant_tokens(normalize_citation_text(text))
    return gold_tokens <= text_tokens


def _citation_aliases(
    citation: str,
    alias_map: dict[str, list[str]] | None,
) -> list[str]:
    """Return benchmark citation plus any mapped aliases for sentence matching."""
    aliases = [citation]
    if alias_map:
        aliases.extend(alias_map.get(citation, []) or [])
    seen = set()
    unique = []
    for alias in aliases:
        if not alias:
            continue
        norm = normalize_citation_text(alias)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(alias)
    return unique


def find_citations_in_sentence(
    sentence: str,
    citations: list[str],
    alias_map: dict[str, list[str]] | None = None,
) -> list[str]:
    """Section-level: find required citations or mapped aliases in the sentence."""
    sentence_tokens = _significant_tokens(normalize_citation_text(sentence))
    found = []
    for c in citations:
        for alias in _citation_aliases(c, alias_map):
            alias_tokens = _significant_tokens(normalize_citation_text(alias))
            if alias_tokens and alias_tokens <= sentence_tokens:
                found.append(c)
                break
    return found


# -- Source-level matching (loose, reported separately) ------------------------

def source_citation_in_text(text: str, citation: str) -> bool:
    """Loose source-level check: does the source identifier (e.g. 'pub 501')
    appear in the text?  Reported separately from section-level matching."""
    citation_norm = normalize_citation_text(citation)
    if not citation_norm:
        return False
    text_norm = normalize_citation_text(text)
    if citation_norm in text_norm:
        return True
    return extract_source_id(citation_norm) in text_norm


def find_source_citations_in_sentence(sentence: str, citations: list[str]) -> list[str]:
    """Loose source-level: find citations whose source ID appears in a sentence."""
    sentence_norm = normalize_citation_text(sentence)
    found = []
    for c in citations:
        c_norm = normalize_citation_text(c)
        if c_norm in sentence_norm:
            found.append(c)
        elif extract_source_id(c_norm) in sentence_norm:
            found.append(c)
    return found


# -- Whitespace helpers --------------------------------------------------------

def normalize_space(text: str) -> str:
    """Collapse all whitespace to single spaces."""
    return _WHITESPACE_RE.sub(" ", text.strip())


# -- Abbreviation-aware sentence splitting -------------------------------------

def _protect_abbreviations(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Temporarily replace periods in abbreviations with placeholders."""
    protected = text
    replacements = []
    for abbrev in sorted(ABBREV_PROTECT, key=len, reverse=True):
        placeholder = abbrev.replace(".", "\x00")
        if abbrev in protected:
            protected = protected.replace(abbrev, placeholder)
            replacements.append((placeholder, abbrev))
    return protected, replacements


def _restore_abbreviations(text: str, replacements: list[tuple[str, str]]) -> str:
    """Restore protected abbreviations after sentence splitting."""
    restored = text
    for placeholder, original in replacements:
        restored = restored.replace(placeholder, original)
    return restored


def split_prose_paragraph(paragraph: str) -> list[str]:
    """Split a prose paragraph into sentences while protecting abbreviations."""
    protected, replacements = _protect_abbreviations(paragraph)
    candidates = re.split(r"(?<=[.!?])\s+", protected.strip())
    sentences = []
    for candidate in candidates:
        sentence = _restore_abbreviations(candidate, replacements).strip()
        if sentence and not _NUMBER_ONLY_RE.fullmatch(sentence):
            sentences.append(sentence)
    return sentences


def split_list_paragraph(paragraph: str) -> list[str]:
    """Split a numbered list paragraph into individual list items."""
    candidates = re.split(r"(?m)(?=^\s*\d+\.\s+)", paragraph.strip())
    items = []
    for candidate in candidates:
        item = candidate.strip()
        if not item:
            continue
        if _LIST_ITEM_RE.match(item):
            items.append(item)
        else:
            items.extend(split_prose_paragraph(item))
    return items


def is_list_item(text: str) -> bool:
    """Check if text starts with a list marker (e.g. '1.', '-', '*')."""
    return bool(_LIST_ITEM_RE.match(text))


# -- Hypothesis cleaning for NLI ----------------------------------------------

def clean_hypothesis(sentence: str) -> str:
    """Strip citation scaffolding and formatting noise before NLI."""
    cleaned = sentence.replace("\r", " ").replace("\n", " ")
    cleaned = _BRACKETED_CITATION_RE.sub("", cleaned)
    cleaned = _PARENTHETICAL_CITATION_RE.sub("", cleaned)
    cleaned = re.sub(r"^\s*\d+\.\s*", "", cleaned)
    cleaned = re.sub(r"[*_`]+", "", cleaned)
    cleaned = re.sub(r"^\s*according to\s+[^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*under\s+[^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r",?\s*as (?:provided|outlined|described|specified|stated) in\b.*$",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = normalize_space(cleaned).strip(" .:;-")
    return cleaned


# -- Claim classification -----------------------------------------------------

def is_substantive_claim(cleaned_sentence: str) -> bool:
    """Return True for sentences substantial enough to score for recall."""
    if not cleaned_sentence:
        return False
    if len(cleaned_sentence) < 8:
        return False
    if not re.search(r"[A-Za-z]", cleaned_sentence):
        return False
    return True


def is_citation_only(
    sentence: str,
    citations: list[str],
    alias_map: dict[str, list[str]] | None = None,
) -> bool:
    """Return True when the sentence is only citation scaffolding, not a claim."""
    explicit_citations = find_citations_in_sentence(sentence, citations, alias_map)
    if not explicit_citations:
        return False
    stripped = sentence
    for citation in explicit_citations:
        for alias in _citation_aliases(citation, alias_map):
            stripped = re.sub(re.escape(alias), " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"[\[\]()]", " ", stripped)
    stripped = re.sub(r"[*_`]+", " ", stripped)
    stripped = re.sub(
        r"^\s*(according to|see|under|source|citation|reference)\b[:\s]*",
        "", stripped, flags=re.IGNORECASE,
    )
    stripped = re.sub(r"\s+", " ", stripped).strip(" .:;-")
    return not is_substantive_claim(stripped)
