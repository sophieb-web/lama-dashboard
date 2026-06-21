"""
Pure HTTP + HTML scraper — no AI, no Anthropic API.
Checks CTech, TechCrunch, Geektime, SecurityWeek for Israeli cyber funding news.
"""

import hashlib
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

import staging

LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 10
DELAY = 2.5  # seconds between requests

CYBER_KEYWORDS = [
    "cybersecurity", "cyber security", "cyber", "security",
    "raises", "raised", "funding", "round", "series", "seed",
    "million", "$", "invest",
]

ROUND_PATTERNS = {
    "Seed": r"\bseed\b",
    "Series A": r"\bseries\s*a\b",
    "Series B": r"\bseries\s*b\b",
    "Series C": r"\bseries\s*c\b",
    "Series D": r"\bseries\s*d\b",
    "Series E": r"\bseries\s*e\b",
    "Growth": r"\bgrowth\b|\blate.stage\b",
}

AMOUNT_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*(m|million|b|billion)", re.IGNORECASE)

log_lines = []


def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    log_lines.append(line)
    print(line)


def _get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r
    except Exception as e:
        _log(f"  ⚠ Request failed for {url}: {e}")
        return None


def _extract_amount(text):
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ("b", "billion"):
        n *= 1000
    return round(n, 1)


def _extract_round_type(text):
    text_lower = text.lower()
    for rtype, pattern in ROUND_PATTERNS.items():
        if re.search(pattern, text_lower):
            return rtype
    return None


def _make_id(source, company, date_str):
    raw = f"{source}|{company.lower().strip()}|{date_str}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _is_relevant(text):
    text_lower = text.lower()
    has_israel = "israel" in text_lower or "tel aviv" in text_lower or "israeli" in text_lower
    has_cyber = any(k in text_lower for k in CYBER_KEYWORDS[:6])
    has_money = "$" in text or "million" in text_lower or "funding" in text_lower
    return has_israel and (has_cyber or has_money)


def _days_ago(n):
    return datetime.now(timezone.utc) - timedelta(days=n)


# ── Load existing DB company names for cross-reference ───────────────────────

def _load_db_companies():
    try:
        import pandas as pd
        csv_path = os.path.join(os.path.dirname(__file__), "data", "deals.csv")
        df = pd.read_csv(csv_path, skiprows=2, dtype=str, usecols=[0])
        df.columns = ["name"]
        return [n.strip() for n in df["name"].dropna().tolist() if n.strip()]
    except Exception as e:
        _log(f"  ⚠ Could not load DB companies: {e}")
        return []


def _fuzzy_match(name, db_names):
    try:
        from rapidfuzz import fuzz
        name_lower = name.lower().strip()
        best_score = 0
        best_match = None
        for db_name in db_names:
            score = fuzz.ratio(name_lower, db_name.lower().strip())
            if score > best_score:
                best_score = score
                best_match = db_name
        if best_score >= 85:
            return best_match
        return None
    except ImportError:
        # Fallback: exact match
        for db_name in db_names:
            if name.lower().strip() == db_name.lower().strip():
                return db_name
        return None


def _already_in_db(company, round_type, round_date, db_companies):
    """Check staging.json to avoid re-staging known duplicates."""
    data = staging.load_staging()
    all_staged = data["pending"] + data["approved"] + data["rejected"] + data["pushed"]
    for f in all_staged:
        if (f.get("company_name", "").lower() == company.lower() and
                f["data"].get("round_type") == round_type and
                f["data"].get("round_date") == round_date):
            return True
    return False


def _build_finding(source_name, company_name, headline, url, round_type,
                   round_date, round_size, lead_investor, co_investors,
                   ftype, db_match):
    fid = _make_id(source_name, company_name, round_date or headline[:20])
    is_portfolio = company_name in LAMA_PORTFOLIO or (db_match and db_match in LAMA_PORTFOLIO)
    return {
        "id": fid,
        "type": ftype,
        "status": "pending",
        "company_name": company_name,
        "company_in_db": db_match is not None,
        "db_match": db_match,
        "is_portfolio": is_portfolio,
        "source_url": url,
        "source_name": source_name,
        "headline": headline,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "round_type": round_type or "",
            "round_date": round_date or "",
            "round_size": round_size,
            "lead_investor": lead_investor or "",
            "co_investors": co_investors or "",
        },
    }


# ── Source scrapers ───────────────────────────────────────────────────────────

def _scrape_techcrunch(db_names):
    findings = []
    urls = [
        "https://techcrunch.com/search/?q=israel+cybersecurity",
        "https://techcrunch.com/search/?q=israel+cyber+funding",
    ]
    for url in urls:
        _log(f"  Fetching TechCrunch: {url}")
        r = _get(url)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")

        # TechCrunch search results
        articles = soup.select("article, .post-block, [class*='article']")
        if not articles:
            articles = soup.select("h2 a, h3 a")

        for article in articles[:15]:
            try:
                if hasattr(article, "select_one"):
                    link_el = article.select_one("a[href]")
                    title_el = article.select_one("h2, h3, .post-block__title")
                    title = title_el.get_text(strip=True) if title_el else ""
                    href = link_el["href"] if link_el else ""
                else:
                    title = article.get_text(strip=True)
                    href = article.get("href", "")

                if not title or not _is_relevant(title):
                    continue

                amount = _extract_amount(title)
                rtype = _extract_round_type(title)
                company = _extract_company_from_headline(title)
                if not company:
                    continue

                db_match = _fuzzy_match(company, db_names)
                if _already_in_db(company, rtype, "", db_names):
                    continue

                findings.append(_build_finding(
                    "TechCrunch", company, title, href,
                    rtype, "", amount, "", "", "new_round", db_match
                ))
            except Exception:
                continue
        time.sleep(DELAY)
    _log(f"  TechCrunch: found {len(findings)} candidate(s)")
    return findings


def _scrape_geektime(db_names):
    findings = []
    url = "https://www.geektime.com/?s=cybersecurity+funding+israel"
    _log(f"  Fetching Geektime: {url}")
    r = _get(url)
    if not r:
        _log("  Geektime: no response")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.select("article h2 a, .post h2 a, .entry-title a")

    for a in articles[:15]:
        try:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or not _is_relevant(title):
                continue
            amount = _extract_amount(title)
            rtype = _extract_round_type(title)
            company = _extract_company_from_headline(title)
            if not company:
                continue
            db_match = _fuzzy_match(company, db_names)
            findings.append(_build_finding(
                "Geektime", company, title, href,
                rtype, "", amount, "", "", "new_round", db_match
            ))
        except Exception:
            continue

    time.sleep(DELAY)
    _log(f"  Geektime: found {len(findings)} candidate(s)")
    return findings


def _scrape_securityweek(db_names):
    findings = []
    url = "https://www.securityweek.com/?s=israel+funding"
    _log(f"  Fetching SecurityWeek: {url}")
    r = _get(url)
    if not r:
        _log("  SecurityWeek: no response")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.select("h2 a, h3 a, .article-title a")

    for a in articles[:15]:
        try:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not title or not _is_relevant(title):
                continue
            amount = _extract_amount(title)
            rtype = _extract_round_type(title)
            company = _extract_company_from_headline(title)
            if not company:
                continue
            db_match = _fuzzy_match(company, db_names)
            findings.append(_build_finding(
                "SecurityWeek", company, title, href,
                rtype, "", amount, "", "", "new_round", db_match
            ))
        except Exception:
            continue

    time.sleep(DELAY)
    _log(f"  SecurityWeek: found {len(findings)} candidate(s)")
    return findings


def _scrape_ctech(db_names):
    findings = []
    urls = [
        "https://ctech.calcalist.co.il/search?q=cybersecurity+funding",
        "https://ctech.calcalist.co.il/search?q=israel+cyber+raise",
    ]
    for url in urls:
        _log(f"  Fetching CTech: {url}")
        r = _get(url)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.select("a[href]")

        for a in articles[:30]:
            try:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if len(title) < 20 or not _is_relevant(title):
                    continue
                amount = _extract_amount(title)
                rtype = _extract_round_type(title)
                company = _extract_company_from_headline(title)
                if not company:
                    continue
                db_match = _fuzzy_match(company, db_names)
                findings.append(_build_finding(
                    "CTech", company, title, href,
                    rtype, "", amount, "", "", "new_round", db_match
                ))
            except Exception:
                continue
        time.sleep(DELAY)

    # Deduplicate within this source
    seen = set()
    unique = []
    for f in findings:
        key = f["id"]
        if key not in seen:
            seen.add(key)
            unique.append(f)

    _log(f"  CTech: found {len(unique)} candidate(s)")
    return unique


def _extract_company_from_headline(headline):
    """
    Heuristic: many headlines follow patterns like:
      "CompanyName Raises $XM in Series A"
      "CompanyName Secures $XM"
      "Israeli CompanyName Gets $XM"
    Extract the company name from the start of the headline.
    """
    # Strip common prefixes
    headline = re.sub(r"^(Israeli|Israel-based|Tel Aviv)\s+", "", headline, flags=re.IGNORECASE)

    # Match "Name Raises/Secures/Gets/Closes/Announces"
    m = re.match(
        r"^([A-Z][A-Za-z0-9\.\-\s]{1,35}?)\s+"
        r"(raises?|secures?|gets?|closes?|announces?|lands?|nets?|bags?|receives?|completes?)\b",
        headline,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Match "Name, a ... startup, raises"
    m2 = re.match(r"^([A-Z][A-Za-z0-9\.\-\s]{1,35}?),\s+a\b", headline)
    if m2:
        return m2.group(1).strip()

    return None


# ── Main entry point ──────────────────────────────────────────────────────────

def run_scrape():
    """
    Run all scrapers, cross-reference findings, deduplicate, and stage results.
    Updates staging.json throughout. Returns list of new findings added.
    """
    global log_lines
    log_lines = []

    # Mark as running
    data = staging.load_staging()
    data["scrape_status"] = "running"
    data["scrape_log"] = []
    staging.save_staging(data)

    try:
        _log("Starting scrape — checking last 7 days of Israeli cyber news")
        db_names = _load_db_companies()
        _log(f"Loaded {len(db_names)} companies from database for cross-reference")

        all_findings = []

        _log("Scraping CTech...")
        try:
            all_findings += _scrape_ctech(db_names)
        except Exception as e:
            _log(f"  CTech error: {e}")

        _log("Scraping TechCrunch...")
        try:
            all_findings += _scrape_techcrunch(db_names)
        except Exception as e:
            _log(f"  TechCrunch error: {e}")

        _log("Scraping Geektime...")
        try:
            all_findings += _scrape_geektime(db_names)
        except Exception as e:
            _log(f"  Geektime error: {e}")

        _log("Scraping SecurityWeek...")
        try:
            all_findings += _scrape_securityweek(db_names)
        except Exception as e:
            _log(f"  SecurityWeek error: {e}")

        # Deduplicate across sources by id
        seen_ids = set()
        unique_findings = []
        for f in all_findings:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                unique_findings.append(f)

        in_db = sum(1 for f in unique_findings if f["company_in_db"])
        new_cos = sum(1 for f in unique_findings if not f["company_in_db"])
        portfolio_hits = [f for f in unique_findings if f.get("is_portfolio")]

        _log(f"Cross-reference complete: {in_db} matched existing companies, {new_cos} potential new companies")
        if portfolio_hits:
            _log(f"⚠ {len(portfolio_hits)} finding(s) match Lama portfolio companies — review carefully")

        added = staging.add_findings(unique_findings)
        _log(f"Staged {added} new finding(s) (duplicates skipped). Done.")

        # Save final status
        data = staging.load_staging()
        data["scrape_status"] = "complete"
        data["last_scraped"] = datetime.now(timezone.utc).isoformat()
        data["scrape_log"] = log_lines
        # Next Monday 9am Israel time
        data["next_scheduled"] = _next_monday_israel()
        staging.save_staging(data)

        return unique_findings

    except Exception as e:
        _log(f"Fatal scrape error: {e}")
        data = staging.load_staging()
        data["scrape_status"] = "error"
        data["scrape_log"] = log_lines
        staging.save_staging(data)
        raise


def _next_monday_israel():
    from datetime import timezone as tz
    try:
        from zoneinfo import ZoneInfo
        israel = ZoneInfo("Asia/Jerusalem")
    except ImportError:
        israel = timezone(timedelta(hours=3))

    now = datetime.now(israel)
    days_until_monday = (7 - now.weekday()) % 7 or 7
    next_mon = now + timedelta(days=days_until_monday)
    next_mon = next_mon.replace(hour=9, minute=0, second=0, microsecond=0)
    return next_mon.isoformat()


if __name__ == "__main__":
    results = run_scrape()
    print(f"\nTotal findings: {len(results)}")
    for f in results:
        print(f"  [{f['source_name']}] {f['company_name']} — {f['headline'][:60]}")
