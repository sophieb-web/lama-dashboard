"""
RSS-based scraper — no browser automation, no bot-blocking issues.
Reads TechCrunch Security and SecurityWeek RSS feeds; filters for
Israeli cybersecurity funding articles.
"""

import hashlib
import os
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

import staging

LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

TIMEOUT = 15
DELAY = 1.5  # seconds between feed fetches

# RSS feeds — plain XML, no bot-blocking
# require_israel=False for Israeli outlets where all articles are implicitly Israeli
RSS_FEEDS = [
    {
        "name": "TechCrunch Security",
        "url": "https://techcrunch.com/category/security/feed/",
        "require_israel": True,
    },
    {
        "name": "SecurityWeek",
        "url": "https://www.securityweek.com/feed/",
        "require_israel": True,
    },
    {
        "name": "Globes",
        "url": "https://en.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=1725",
        "require_israel": False,  # Israeli outlet — all articles are Israeli
        "encoding": "utf-8-sig",  # has BOM
    },
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


def _get_rss(url, encoding=None):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        if encoding:
            return r.content.decode(encoding, errors="replace")
        return r.content.decode("utf-8", errors="replace")
    except Exception as e:
        _log(f"  ⚠ RSS fetch failed for {url}: {e}")
        return None


def _parse_rss_items(xml_text):
    """Return list of dicts with title, description, link, pub_date."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        _log(f"  ⚠ XML parse error: {e}")
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()

        # Parse RFC 822 date → ISO string
        pub_date = ""
        if pub_raw:
            try:
                pub_date = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d")
            except Exception:
                pass

        items.append({
            "title": title,
            "description": desc,
            "link": link,
            "pub_date": pub_date,
        })
    return items


def _is_relevant(title, description="", require_israel=True):
    """Filter for funding + cyber articles. Israel check optional for Israeli outlets."""
    combined = (title + " " + description).lower()
    has_israel = any(w in combined for w in ["israel", "israeli", "tel aviv", "haifa"])
    has_money = any(w in combined for w in [
        "raises", "raised", "funding", "round", "series", "seed",
        "million", "$", "invest", "secures", "closes",
    ])
    has_cyber = any(w in combined for w in [
        "cyber", "security", "infosec", "ransomware", "threat", "cloud security",
        "nso", "defense tech", "defensetech",
    ])
    if require_israel:
        return has_israel and has_money and has_cyber
    return has_money and has_cyber


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


def _extract_company_from_headline(headline):
    """
    Heuristics for patterns like:
      "CompanyName Raises $XM in Series A"
      "Israeli CompanyName Secures $XM"
      "CompanyName, a cybersecurity startup, raises..."
    """
    # Strip leading nationality/descriptor prefixes (loop until stable)
    PREFIX_RE = re.compile(
        r"^(Israeli|Israel.based|Tel Aviv.based|Israeli.founded"
        r"|startup|cyber|cybersecurity"
        r"|offensive security co|security co"
        r"|tech company|firm)\s+",
        re.IGNORECASE,
    )
    for _ in range(5):
        stripped = PREFIX_RE.sub("", headline)
        if stripped == headline:
            break
        headline = stripped

    m = re.match(
        r"^([A-Z][A-Za-z0-9\.\-\s]{1,35}?)\s+"
        r"(raises?|secures?|gets?|closes?|announces?|lands?|nets?|bags?|"
        r"receives?|completes?|clinches?|wins?)\b",
        headline, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    m2 = re.match(r"^([A-Z][A-Za-z0-9\.\-\s]{1,35}?),\s+a\b", headline)
    if m2:
        return m2.group(1).strip()

    return None


def _make_id(source, company, date_str):
    raw = f"{source}|{company.lower().strip()}|{date_str}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


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
        best_score, best_match = 0, None
        for db_name in db_names:
            score = fuzz.ratio(name_lower, db_name.lower().strip())
            if score > best_score:
                best_score, best_match = score, db_name
        return best_match if best_score >= 85 else None
    except ImportError:
        for db_name in db_names:
            if name.lower().strip() == db_name.lower().strip():
                return db_name
        return None


def _already_staged(company, round_type, round_date):
    """Check staging.json to avoid re-staging duplicates."""
    data = staging.load_staging()
    all_staged = data["pending"] + data["approved"] + data["rejected"] + data["pushed"]
    for f in all_staged:
        if (f.get("company_name", "").lower() == company.lower()
                and f["data"].get("round_type") == round_type
                and f["data"].get("round_date") == round_date):
            return True
    return False


def _build_finding(source_name, company_name, headline, url, round_type,
                   round_date, round_size, lead_investor, co_investors,
                   ftype, db_match):
    fid = _make_id(source_name, company_name, round_date or headline[:20])
    is_portfolio = (company_name in LAMA_PORTFOLIO
                    or (db_match and db_match in LAMA_PORTFOLIO))
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


def _scrape_feed(feed, db_names):
    """Fetch one RSS feed and return list of findings."""
    name = feed["name"]
    url = feed["url"]
    require_israel = feed.get("require_israel", True)
    encoding = feed.get("encoding", None)
    _log(f"  Fetching {name}: {url}")

    xml_text = _get_rss(url, encoding=encoding)
    if not xml_text:
        return []

    items = _parse_rss_items(xml_text)
    _log(f"  {name}: parsed {len(items)} RSS items")

    findings = []
    seen_ids = set()

    for item in items:
        title = item["title"]
        desc = item["description"]
        link = item["link"]
        pub_date = item["pub_date"]

        if not _is_relevant(title, desc, require_israel=require_israel):
            continue

        combined_text = title + " " + desc
        amount = _extract_amount(combined_text)
        rtype = _extract_round_type(combined_text)
        company = _extract_company_from_headline(title)

        if not company:
            # Try description lead
            company = _extract_company_from_headline(desc[:200])
        if not company:
            _log(f"    Skip (no company name): {title[:70]}")
            continue

        db_match = _fuzzy_match(company, db_names)
        ftype = "new_company" if not db_match else "new_round"

        if _already_staged(company, rtype, pub_date):
            _log(f"    Skip (already staged): {company}")
            continue

        finding = _build_finding(
            name, company, title, link,
            rtype, pub_date, amount, "", "", ftype, db_match
        )

        if finding["id"] not in seen_ids:
            seen_ids.add(finding["id"])
            findings.append(finding)
            _log(f"    + Found: {company} ({rtype or '?'} {amount or '?'}M) — {title[:55]}")

    _log(f"  {name}: {len(findings)} qualifying finding(s)")
    return findings


# ── Main entry point ──────────────────────────────────────────────────────────

def run_scrape():
    """
    Fetch all RSS feeds, filter for Israeli cyber funding news,
    cross-reference against DB, and stage new findings.
    """
    global log_lines
    log_lines = []

    data = staging.load_staging()
    data["scrape_status"] = "running"
    data["scrape_log"] = []
    staging.save_staging(data)

    try:
        _log(f"Starting RSS scrape — {len(RSS_FEEDS)} feed(s)")
        db_names = _load_db_companies()
        _log(f"Loaded {len(db_names)} companies from database")

        all_findings = []

        for feed in RSS_FEEDS:
            try:
                all_findings += _scrape_feed(feed, db_names)
            except Exception as e:
                _log(f"  {feed['name']} error: {e}")
            time.sleep(DELAY)

        # Deduplicate across feeds by id
        seen_ids = set()
        unique = []
        for f in all_findings:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                unique.append(f)

        in_db     = sum(1 for f in unique if f["company_in_db"])
        new_cos   = sum(1 for f in unique if not f["company_in_db"])
        portfolio = [f for f in unique if f.get("is_portfolio")]

        _log(f"Total: {len(unique)} unique finding(s) — "
             f"{in_db} matched existing, {new_cos} potentially new")
        if portfolio:
            _log(f"⚠ {len(portfolio)} match Lama portfolio — review carefully")

        added = staging.add_findings(unique)
        _log(f"Staged {added} new finding(s) (duplicates skipped). Done.")

        data = staging.load_staging()
        data["scrape_status"] = "complete"
        data["last_scraped"] = datetime.now(timezone.utc).isoformat()
        data["scrape_log"] = log_lines
        data["next_scheduled"] = _next_monday_israel()
        staging.save_staging(data)

        return unique

    except Exception as e:
        _log(f"Fatal scrape error: {e}")
        data = staging.load_staging()
        data["scrape_status"] = "error"
        data["scrape_log"] = log_lines
        staging.save_staging(data)
        raise


def _next_monday_israel():
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
        print(f"  [{f['source_name']}] {f['company_name']} — {f['headline'][:70]}")
