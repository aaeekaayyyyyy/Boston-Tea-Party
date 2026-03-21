#!/usr/bin/env python3
"""
Download one representative sample of each source type into sources/.
Run from repo root: python scripts/download_samples.py
"""
import os
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = REPO_ROOT / "sources"


def download_irc_sample():
    """Fetch IRC § 1 (Tax imposed) from Cornell LII as sample."""
    url = "https://www.law.cornell.edu/uscode/text/26/1"
    out_dir = SOURCES / "irc"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "26_usc_1.html"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BostonTeaParty2.0/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode(errors="replace")
        out_path.write_text(html, encoding="utf-8")
        print(f"Saved IRC sample: {out_path}")
        return True
    except Exception as e:
        print(f"IRC sample download failed: {e}")
        return False


def download_irs_pub_sample():
    """Fetch one IRS Publication PDF (e.g. Pub. 501 excerpt or full) as sample."""
    # Pub. 501 — Dependents, Standard Deduction, Filing Info (smaller than Pub. 17)
    url = "https://www.irs.gov/pub/irs-pdf/p501.pdf"
    out_dir = SOURCES / "irs_pubs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "p501_sample.pdf"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BostonTeaParty2.0/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        print(f"Saved IRS Pub sample: {out_path}")
        return True
    except Exception as e:
        print(f"IRS Pub sample download failed: {e}")
        return False


def download_tax_court_sample():
    """Fetch one U.S. Tax Court opinion as sample (HTML if available)."""
    # Sample: Tax Court opinion list or a single opinion; URL may need updating.
    url = "https://www.ustaxcourt.gov/ustc/opinions.htm"
    out_dir = SOURCES / "tax_court"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "opinions_index_sample.html"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BostonTeaParty2.0/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode(errors="replace")
        out_path.write_text(html, encoding="utf-8")
        print(f"Saved Tax Court sample (index): {out_path}")
        return True
    except Exception as e:
        print(f"Tax Court sample download failed: {e}")
        return False


def main():
    os.chdir(REPO_ROOT)
    print("Downloading one sample per source type into sources/ ...")
    download_irc_sample()
    download_irs_pub_sample()
    download_tax_court_sample()
    print("Done. See sources/README.md and docs/structure_analysis.md.")


if __name__ == "__main__":
    main()
