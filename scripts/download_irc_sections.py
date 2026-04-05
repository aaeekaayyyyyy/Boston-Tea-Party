#!/usr/bin/env python3
"""
Download Cornell LII HTML for Title 26 sections into sources/irc/26_usc_<n>.html.

Default sections match constraint-engine citations (filing status, std deduction, dependents, charitable): 1, 2, 63, 68, 151, 152, 170, 6012, 6013, 7703 (override with argv).

Run from repo root: python scripts/download_irc_sections.py 1 2 63
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "sources" / "irc"


def download_section(num: str) -> bool:
    url = f"https://www.law.cornell.edu/uscode/text/26/{num}"
    path = OUT_DIR / f"26_usc_{num}.html"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BostonTeaParty2.0/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            html = resp.read().decode(errors="replace")
        path.write_text(html, encoding="utf-8")
        print("Saved", path)
        return True
    except Exception as e:
        print("Failed", num, e)
        return False


def main() -> int:
    default = ["1", "2", "63", "68", "151", "152", "170", "6012", "6013", "7703"]
    secs = sys.argv[1:] if len(sys.argv) > 1 else default
    ok = 0
    for s in secs:
        if download_section(s.strip()):
            ok += 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
