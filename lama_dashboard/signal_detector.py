"""
signal_detector.py — Lama Partners daily signal detection.
No AI, no Anthropic API. Pure keyword matching, RSS, and database logic.
"""
import hashlib
import os
import re
import time
from datetime import datetime, timezone, timedelta

import signals_store

LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}
_log_lines = []

PROXYCURL_API_KEY = os.environ.get("PROXYCURL_API_KEY", "")

# Titles that indicate the founder is actively founding something new
_FOUNDING_TITLES = {"founder", "co-founder", "ceo", "chief executive officer", "co-ceo"}
# Titles that indicate between-roles / advisor mode
_ADVISOR_TITLES = {"advisor", "independent", "angel", "angel investor", "consultant",
                   "independent advisor", "board member", "board advisor"}


def _proxycurl_check(linkedin_url, acquirer_name):
    """
    Call Proxycurl API and return a dict:
      {
        "status": "suppressed" | "founding" | "advisor" | "employed_elsewhere" | "failed" | "no_key",
        "priority_override": "Critical" | "High" | "Medium" | None,
        "linkedin_note": str,       # short human-readable result
        "current_company": str,
        "current_title": str,
        "linkedin_url": str,
        "verified": bool,
      }
    """
    base = {
        "status": "failed",
        "priority_override": "Medium",
        "linkedin_note": "",
        "current_company": "",
        "current_title": "",
        "linkedin_url": linkedin_url or "",
        "verified": False,
    }

    if not PROXYCURL_API_KEY:
        base["status"] = "no_key"
        base["linkedin_note"] = "⚠️ LinkedIn verification skipped — PROXYCURL_API_KEY not set"
        return base

    if not linkedin_url:
        base["status"] = "failed"
        base["linkedin_note"] = "⚠️ No LinkedIn URL in database — verify manually before acting"
        return base

    try:
        import requests as _req
        resp = _req.get(
            "https://nubela.co/proxycurl/api/v2/linkedin",
            headers={"Authorization": f"Bearer {PROXYCURL_API_KEY}"},
            params={"url": linkedin_url},
            timeout=15,
        )
        if resp.status_code == 402:
            base["status"] = "failed"
            base["linkedin_note"] = "⚠️ LinkedIn verification failed — Proxycurl out of credits"
            return base
        if resp.status_code != 200:
            base["status"] = "failed"
            base["linkedin_note"] = f"⚠️ LinkedIn verification failed — API returned {resp.status_code}"
            return base

        data = resp.json()
        experiences = data.get("experiences") or []

        if not experiences:
            base["status"] = "failed"
            base["linkedin_note"] = "⚠️ LinkedIn verification failed — no experience data returned"
            return base

        # Find the most recent current role (ends_at is None)
        current = next((e for e in experiences if e.get("ends_at") is None), experiences[0])
        title = (current.get("title") or "").strip()
        company = (current.get("company") or "").strip()
        title_lower = title.lower()

        base["current_title"] = title
        base["current_company"] = company
        base["verified"] = True

        # Check if still at acquirer
        acquirer_lower = acquirer_name.lower().strip()
        company_lower = company.lower()
        if acquirer_lower and (acquirer_lower in company_lower or company_lower in acquirer_lower):
            base["status"] = "suppressed"
            base["priority_override"] = None  # suppress entirely
            base["linkedin_note"] = f"LinkedIn confirms: still at {company} ({title}) — suppressing signal"
            return base

        # Check founding new company
        if any(t in title_lower for t in _FOUNDING_TITLES):
            base["status"] = "founding"
            base["priority_override"] = "Critical"
            base["linkedin_note"] = f"✓ LinkedIn confirms: actively founding {company} ({title})"
            return base

        # Check advisor/between roles
        if any(t in title_lower for t in _ADVISOR_TITLES) or not company:
            base["status"] = "advisor"
            base["priority_override"] = "High"
            base["linkedin_note"] = f"LinkedIn: between roles / advisor ({title or 'no current title'})"
            return base

        # Employed elsewhere — still useful signal, lower priority
        base["status"] = "employed_elsewhere"
        base["priority_override"] = "Medium"
        base["linkedin_note"] = f"LinkedIn: employed elsewhere at {company} ({title}) — lower priority"
        return base

    except Exception as e:
        base["status"] = "failed"
        base["linkedin_note"] = f"⚠️ LinkedIn verification failed — {e}"
        return base


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _log_lines.append(line)
    print(line)


def _make_id(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _month_key():
    d = datetime.now()
    return f"{d.year}-{d.month:02d}"


# ─── Detector 1: RSS News Monitor ────────────────────────────────────────────

RSS_FEEDS = [
    ("TechCrunch Security", "https://techcrunch.com/category/security/feed/"),
    ("SecurityWeek", "https://www.securityweek.com/feed/"),
    ("Globes English", "https://en.globes.co.il/en/rss"),
    ("CTech", "https://www.calcalist.co.il/rss/AID-1522221960.xml"),
    ("Dark Reading", "https://www.darkreading.com/rss.xml"),
    ("Hacker News", "https://news.ycombinator.com/rss"),
]

CISO_APPT_TRIGGERS = ["appoints", "names", "hires", "welcomes", "joins as"]
CISO_ROLE_KW = ["ciso", "chief information security officer", "chief security officer"]

AI_TRANSFORM_KW = [
    "ai transformation", "agentic ai", "ai agents", "deploy ai",
    "mcp", "model context protocol", "ai copilot", "generative ai rollout",
    "llm in production", "ai-powered", "chief ai officer", "caito",
]

BREACH_KW = [
    "data breach", "ransomware attack", "cyberattack", "hacked",
    "security incident", "breach confirmed", "exposed records",
]

FUNDING_KW = ["raises", "raised", "funding", "series", "seed round",
              "million", "venture capital", "investment"]
ISRAEL_KW = ["israeli", "israel", "tel aviv"]
CYBER_KW = ["cybersecurity", "cyber security", "cyber"]

REGULATION_KW = ["sec", "gdpr", "eu ai act", "nis2", "cyber regulation",
                 "compliance mandate", "regulatory requirement", "fine", "penalty"]

ACQUISITION_KW = ["acquires", "acquired", "acquisition", "buys", "merger",
                  "deal closes", "takeover"]

NEW_STARTUP_KW = ["raises seed", "emerges from stealth", "founded", "new startup", "stealth mode"]


def _within_48h(entry):
    try:
        import feedparser
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not published:
            return True
        import calendar
        pub_ts = calendar.timegm(published)
        cutoff = time.time() - 48 * 3600
        return pub_ts >= cutoff
    except Exception:
        return True


def _text(entry):
    title = entry.get("title", "") or ""
    summary = entry.get("summary", "") or ""
    return (title + " " + summary).lower()


def _contains_any(text, keywords):
    return any(kw in text for kw in keywords)


def _extract_company_name(text, trigger_kw):
    """Best-effort: extract the subject before the trigger keyword."""
    for kw in trigger_kw:
        idx = text.lower().find(kw)
        if idx > 0:
            before = text[:idx].strip()
            words = before.split()
            if words:
                candidate = " ".join(words[-4:]).strip(" ,.")
                return candidate
    return ""


def _fuzzy_match_company(name, known_names, threshold=85):
    """Return (matched_name, score) if name fuzzy-matches any known company, else (None, 0)."""
    try:
        from rapidfuzz import process, fuzz
        result = process.extractOne(name, known_names, scorer=fuzz.token_sort_ratio)
        if result and result[1] >= threshold:
            return result[0], result[1]
    except ImportError:
        # Fall back to exact substring match
        name_lower = name.lower()
        for kn in known_names:
            if name_lower in kn.lower() or kn.lower() in name_lower:
                return kn, 90
    return None, 0


def _round_already_known(company_name, article_date_str, db_companies):
    """Check if a round for this company is already in deals.csv (within ~6 months of article date)."""
    try:
        from data_loader import get_raw_df
        df = get_raw_df()
        rows = df[df["Company Name"].str.lower() == company_name.lower()]
        if rows.empty:
            return False
        article_date = _parse_date(article_date_str)
        if not article_date:
            return False
        for _, row in rows.iterrows():
            d = _parse_date(str(row.get("Round Date", "") or ""))
            if d and abs((d - article_date).days) <= 180:
                return True
        return False
    except Exception:
        return False


def detect_rss_signals(known_companies=None, db_companies_list=None):
    try:
        import feedparser
    except ImportError:
        log("feedparser not installed — skipping RSS detector")
        return []

    if known_companies is None:
        known_companies = set()
    known_names_list = list(known_companies)

    signals = []

    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            entries = feed.entries or []
            recent = [e for e in entries if _within_48h(e)]
            scanned = len(recent)
            found = 0

            for entry in recent:
                text = _text(entry)
                title = entry.get("title", "")
                url = entry.get("link", "")
                pub = entry.get("published", entry.get("updated", ""))

                # GROUP A: CISO appointment
                if _contains_any(text, CISO_APPT_TRIGGERS) and _contains_any(text, CISO_ROLE_KW):
                    company = _extract_company_name(title, CISO_APPT_TRIGGERS)
                    sig = {
                        "id": _make_id("ciso_appt", feed_name, title[:60]),
                        "category": "Market",
                        "signal_type": "New CISO appointed",
                        "priority": "Critical",
                        "status": "active",
                        "title": f"New CISO appointment: {title[:120]}",
                        "entity": company or feed_name,
                        "why_it_matters": "90-day buying window — biggest tool purchasing decisions happen in first 90 days of new CISO",
                        "action": "Introduce portfolio companies immediately — window closes fast",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)
                    found += 1
                    continue

                # GROUP B: AI transformation
                if _contains_any(text, AI_TRANSFORM_KW):
                    company = _extract_company_name(title, AI_TRANSFORM_KW) or title[:60]
                    sig = {
                        "id": _make_id("ai_transform", feed_name, title[:60]),
                        "category": "AI Transformation",
                        "signal_type": "Company announces AI transformation initiative",
                        "priority": "Critical",
                        "status": "active",
                        "title": title[:160],
                        "entity": company,
                        "why_it_matters": "Immediate need for AI security tools — Capsule and Orion direct opportunity",
                        "action": "Reach out within days — budget is being allocated in real time",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": True,
                        "portfolio_companies": ["Capsule", "Orion Security"],
                    }
                    signals.append(sig)
                    found += 1
                    continue

                # GROUP C: Major cyber incident
                if _contains_any(text, BREACH_KW):
                    company = title.split(" ")[0] if title else "Unknown"
                    sig = {
                        "id": _make_id("breach", feed_name, title[:60]),
                        "category": "Market",
                        "signal_type": "Company announces data breach",
                        "priority": "Critical",
                        "status": "active",
                        "title": title[:160],
                        "entity": company,
                        "why_it_matters": "Acute pain — accelerated buying with board pressure",
                        "action": "Portfolio company outreach — fastest buying cycle in security",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)
                    found += 1
                    continue

                # GROUP D: Funding round — DB-aware (only surface new information)
                if _contains_any(text, FUNDING_KW) and (
                        _contains_any(text, ISRAEL_KW) or _contains_any(text, CYBER_KW)):
                    co_name = _extract_company_name(title, FUNDING_KW) or " ".join(title.split()[:4])
                    matched_name, score = _fuzzy_match_company(co_name, known_names_list)

                    if matched_name:
                        # Company is in our DB — check if this round is also already known
                        if _round_already_known(matched_name, pub, known_companies):
                            log(f"  Found {co_name} in article — already in DB, round already known — skipping")
                            continue
                        else:
                            # New round for a company we already track — surface it
                            log(f"  Found {co_name} in article — in DB but round is new — surfacing signal")
                            sig = {
                                "id": _make_id("funding_new_round", matched_name, title[:40]),
                                "category": "Market",
                                "signal_type": "New round for existing company",
                                "priority": "High",
                                "status": "active",
                                "title": title[:160],
                                "entity": matched_name,
                                "why_it_matters": f"{matched_name} is in our database — this round is not yet recorded",
                                "action": "Update deals.csv with this round via Update Center",
                                "source_url": url,
                                "source_name": feed_name,
                                "detected_at": _now_iso(),
                                "date_of_event": pub,
                                "notes": f"Fuzzy match: '{co_name}' → '{matched_name}' (score {score})",
                                "portfolio_relevant": matched_name in LAMA_PORTFOLIO,
                                "portfolio_companies": [matched_name] if matched_name in LAMA_PORTFOLIO else [],
                            }
                            signals.append(sig)
                            found += 1
                            continue
                    else:
                        # Company NOT in our DB — this is new intelligence
                        log(f"  Found {co_name} in article — NOT in DB — new company signal")
                        sig = {
                            "id": _make_id("new_company_found", co_name, title[:40]),
                            "category": "Market",
                            "signal_type": "New Israeli cyber company found",
                            "priority": "High",
                            "status": "active",
                            "title": f"New company not in DB: {title[:120]}",
                            "entity": co_name,
                            "why_it_matters": "Company not in our database — potential new deal or blind spot",
                            "action": "Research and add to deals.csv via Update Center if relevant",
                            "source_url": url,
                            "source_name": feed_name,
                            "detected_at": _now_iso(),
                            "date_of_event": pub,
                            "notes": f"Extracted company name: '{co_name}' — no fuzzy match found in deals.csv",
                            "portfolio_relevant": False,
                            "portfolio_companies": [],
                        }
                        signals.append(sig)
                        found += 1
                        continue

                # GROUP E: Regulation
                if _contains_any(text, REGULATION_KW):
                    sig = {
                        "id": _make_id("regulation", feed_name, title[:60]),
                        "category": "Market",
                        "signal_type": "New regulation announced",
                        "priority": "High",
                        "status": "active",
                        "title": title[:160],
                        "entity": "Regulatory",
                        "why_it_matters": "Creates immediate compliance buying urgency",
                        "action": "Identify which portfolio companies address this requirement",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)
                    found += 1
                    continue

                # GROUP F: Acquisition in cyber
                if _contains_any(text, ACQUISITION_KW) and _contains_any(text, CYBER_KW):
                    company = " ".join(title.split()[:4])
                    sig = {
                        "id": _make_id("acquisition", feed_name, title[:60]),
                        "category": "Competitive",
                        "signal_type": "Competitor gets acquired",
                        "priority": "High",
                        "status": "active",
                        "title": title[:160],
                        "entity": company,
                        "why_it_matters": "Market consolidating — assess impact on portfolio",
                        "action": "Assess impact on portfolio — does this help or hurt?",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)
                    found += 1
                    continue

                # GROUP G: New Israeli cyber company
                if _contains_any(text, ISRAEL_KW) and _contains_any(text, CYBER_KW) and _contains_any(text, NEW_STARTUP_KW):
                    company = " ".join(title.split()[:4])
                    sig = {
                        "id": _make_id("new_israeli_co", feed_name, title[:60]),
                        "category": "Competitive",
                        "signal_type": "New entrant in portfolio company's category",
                        "priority": "High",
                        "status": "active",
                        "title": title[:160],
                        "entity": company,
                        "why_it_matters": "New Israeli cyber company — potential new deal or competitive threat",
                        "action": "Research company and add to database if not already tracked",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)
                    found += 1

            log(f"{feed_name}: {scanned} articles scanned, {found} signals found")

        except Exception as e:
            log(f"{feed_name}: error — {e}")

    return signals


# ─── Detector 2: Database Calculations ───────────────────────────────────────

def detect_database_signals():
    signals = []
    try:
        from data_loader import get_companies, get_raw_df
        companies = get_companies()
        df = get_raw_df()
    except Exception as e:
        log(f"Database detector: failed to load data — {e}")
        return []

    today = datetime.now()
    month = _month_key()

    acquired_companies = [c for c in companies if c.get("acquired")]
    log(f"Founder vesting: checking {len(acquired_companies)} acquired companies")

    vesting_found = 0
    suppressed_count = 0
    for c in acquired_companies:
        name = c.get("name", "")
        founders = c.get("founders", "")
        acq_date_str = _find_acquisition_date(c, df)
        if not acq_date_str:
            continue

        acq_date = _parse_date(acq_date_str)
        if not acq_date:
            continue

        acquirer = c.get('acquirer', 'unknown acquirer')

        # Pull LinkedIn URL from database (first founder's URL if multiple founders)
        linkedin_raw = c.get("founder_linkedin", "")
        linkedin_url = _first_linkedin_url(linkedin_raw)

        vesting_db_note = (
            f"Calculated from acquisition date in database. "
            f"Always verify on LinkedIn first."
        )

        # CALCULATION A: Vesting window (3-4 years post-acquisition)
        vesting_start = acq_date + timedelta(days=3 * 365)
        vesting_end = acq_date + timedelta(days=4 * 365)
        pre_window = vesting_start - timedelta(days=90)

        if vesting_start <= today <= vesting_end:
            li = _proxycurl_check(linkedin_url, acquirer)
            if li["status"] == "suppressed":
                log(f"  Suppressed: {founders} ({name}) — {li['linkedin_note']}")
                suppressed_count += 1
            else:
                priority = li["priority_override"] or "Medium"
                disclaimer = li["linkedin_note"] if li["verified"] else (
                    li["linkedin_note"] or
                    "⚠️ Verify on LinkedIn before acting — founder may be actively employed or not planning a new venture."
                )
                source_detail = (
                    f"Source: {name} acquired by {acquirer} — Round Date: {acq_date_str} in deals.csv"
                    + (" + LinkedIn verification via Proxycurl" if li["verified"] else "")
                )
                sig = {
                    "id": _make_id("vesting", name, month),
                    "category": "Founder",
                    "signal_type": "Founder vesting complete",
                    "priority": priority,
                    "status": "active",
                    "title": f"{founders} ({name}) — vesting window open",
                    "entity": name,
                    "why_it_matters": "Founder likely free from vesting and considering next company — prime time to build relationship",
                    "action": "Reach out to founder before they start taking meetings",
                    "source_url": "",
                    "source_name": "Database + LinkedIn" if li["verified"] else "Database",
                    "source_detail": source_detail,
                    "disclaimer": disclaimer,
                    "linkedin_url": li["linkedin_url"],
                    "linkedin_verified": li["verified"],
                    "linkedin_current_title": li["current_title"],
                    "linkedin_current_company": li["current_company"],
                    "detected_at": _now_iso(),
                    "date_of_event": acq_date_str,
                    "notes": (
                        f"{vesting_db_note} "
                        f"Vesting window: {vesting_start.strftime('%Y-%m')} to {vesting_end.strftime('%Y-%m')}."
                    ),
                    "portfolio_relevant": False,
                    "portfolio_companies": [],
                }
                signals.append(sig)
                vesting_found += 1

        elif pre_window <= today < vesting_start:
            li = _proxycurl_check(linkedin_url, acquirer)
            if li["status"] == "suppressed":
                log(f"  Suppressed: {founders} ({name}) — {li['linkedin_note']}")
                suppressed_count += 1
            else:
                priority = li["priority_override"] or "Medium"
                # Approaching window: cap at High even if LinkedIn says Critical
                if priority == "Critical":
                    priority = "High"
                disclaimer = li["linkedin_note"] if li["verified"] else (
                    li["linkedin_note"] or
                    "⚠️ Verify on LinkedIn before acting — founder may be actively employed or not planning a new venture."
                )
                source_detail = (
                    f"Source: {name} acquired by {acquirer} — Round Date: {acq_date_str} in deals.csv"
                    + (" + LinkedIn verification via Proxycurl" if li["verified"] else "")
                )
                sig = {
                    "id": _make_id("vesting_approaching", name, month),
                    "category": "Founder",
                    "signal_type": "Founder vesting complete",
                    "priority": priority,
                    "status": "active",
                    "title": f"{founders} ({name}) — vesting window approaching in <3 months",
                    "entity": name,
                    "why_it_matters": "Vesting window opens soon — get ahead of the curve",
                    "action": "Start building relationship now — before vesting hits",
                    "source_url": "",
                    "source_name": "Database + LinkedIn" if li["verified"] else "Database",
                    "source_detail": source_detail,
                    "disclaimer": disclaimer,
                    "linkedin_url": li["linkedin_url"],
                    "linkedin_verified": li["verified"],
                    "linkedin_current_title": li["current_title"],
                    "linkedin_current_company": li["current_company"],
                    "detected_at": _now_iso(),
                    "date_of_event": acq_date_str,
                    "notes": (
                        f"{vesting_db_note} "
                        f"Vesting window opens {vesting_start.strftime('%Y-%m')}."
                    ),
                    "portfolio_relevant": False,
                    "portfolio_companies": [],
                }
                signals.append(sig)
                vesting_found += 1

        # CALCULATION C: Serial founder 4-year mark (3.5-4.5 years post-acq)
        four_yr_start = acq_date + timedelta(days=int(3.5 * 365))
        four_yr_end = acq_date + timedelta(days=int(4.5 * 365))
        if four_yr_start <= today <= four_yr_end:
            li = _proxycurl_check(linkedin_url, acquirer)
            if li["status"] == "suppressed":
                suppressed_count += 1
            else:
                priority = li["priority_override"] or "Medium"
                source_detail = (
                    f"Source: {name} acquired by {acquirer} — Round Date: {acq_date_str} in deals.csv"
                    + (" + LinkedIn verification via Proxycurl" if li["verified"] else "")
                )
                sig = {
                    "id": _make_id("serial_founder_4yr", name, month),
                    "category": "Founder",
                    "signal_type": "Serial founder's last company crosses 4-year mark",
                    "priority": priority,
                    "status": "active",
                    "title": f"{founders} — 4 years post-{acquirer} acquisition",
                    "entity": name,
                    "why_it_matters": "Serial founders typically start next company after 4 years at acquirer — pattern signal",
                    "action": "Proactive outreach — be first call when they're ready",
                    "source_url": "",
                    "source_name": "Database + LinkedIn" if li["verified"] else "Database",
                    "source_detail": source_detail,
                    "disclaimer": li["linkedin_note"] or "⚠️ Verify on LinkedIn before acting.",
                    "linkedin_url": li["linkedin_url"],
                    "linkedin_verified": li["verified"],
                    "linkedin_current_title": li["current_title"],
                    "linkedin_current_company": li["current_company"],
                    "detected_at": _now_iso(),
                    "date_of_event": acq_date_str,
                    "notes": vesting_db_note,
                    "portfolio_relevant": False,
                    "portfolio_companies": [],
                }
                signals.append(sig)

        # CALCULATION D: Non-compete expiry (~18 months post-acq)
        nc_start = acq_date + timedelta(days=12 * 30)
        nc_end = acq_date + timedelta(days=24 * 30)
        if nc_start <= today <= nc_end:
            li = _proxycurl_check(linkedin_url, acquirer)
            if li["status"] == "suppressed":
                suppressed_count += 1
            else:
                priority = li["priority_override"] or "Medium"
                source_detail = (
                    f"Source: {name} acquired by {acquirer} — Round Date: {acq_date_str} in deals.csv"
                    + (" + LinkedIn verification via Proxycurl" if li["verified"] else "")
                )
                sig = {
                    "id": _make_id("non_compete", name, month),
                    "category": "Founder",
                    "signal_type": "Founder's non-compete expires",
                    "priority": priority,
                    "status": "active",
                    "title": f"{founders} — non-compete window closing at {name}",
                    "entity": name,
                    "why_it_matters": "Post-acquisition non-competes typically 12-24 months — expiry means founder is legally free to compete",
                    "action": "Reach out as non-compete window closes",
                    "source_url": "",
                    "source_name": "Database + LinkedIn" if li["verified"] else "Database",
                    "source_detail": source_detail,
                    "disclaimer": li["linkedin_note"] or "⚠️ Verify on LinkedIn before acting.",
                    "linkedin_url": li["linkedin_url"],
                    "linkedin_verified": li["verified"],
                    "linkedin_current_title": li["current_title"],
                    "linkedin_current_company": li["current_company"],
                    "detected_at": _now_iso(),
                    "date_of_event": acq_date_str,
                    "notes": vesting_db_note,
                    "portfolio_relevant": False,
                "portfolio_companies": [],
            }
            signals.append(sig)

    log(f"Founder vesting: {vesting_found} signals surfaced, {suppressed_count} suppressed by LinkedIn verification")

    # CALCULATION E: Competitor recently funded
    try:
        comp_signals = _detect_competitor_funded(companies, df, today)
        signals.extend(comp_signals)
    except Exception as e:
        log(f"Competitor funded detector error: {e}")

    return signals


def _first_linkedin_url(raw):
    """Extract first LinkedIn URL from a raw string (may contain Name: URL | Name: URL format)."""
    if not raw or str(raw).lower() in ("nan", "none", ""):
        return ""
    # Try to find any linkedin.com URL
    m = re.search(r"https?://(?:www\.)?linkedin\.com/in/[^\s|,\"']+", str(raw))
    return m.group(0).rstrip("/.") if m else ""


def _find_acquisition_date(company, df):
    name = company.get("name", "")
    rows = df[df["Company Name"] == name]
    for _, row in rows.iterrows():
        rt = str(row.get("Round Type", "") or "").strip().lower()
        if "acqui" in rt or "exit" in rt or "acquisition" in rt:
            d = str(row.get("Round Date", "") or "").strip()
            if d and d.lower() not in ("nan", ""):
                return d
    # Fall back to any date in the company's deal rows
    for _, row in rows.iterrows():
        d = str(row.get("Round Date", "") or "").strip()
        if d and d.lower() not in ("nan", ""):
            return d
    return None


def _parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %Y", "%B %Y",
                "%Y-%m", "%m-%Y", "%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    m = re.search(r"(20\d\d)", date_str)
    if m:
        try:
            return datetime(int(m.group(1)), 6, 1)
        except Exception:
            pass
    return None


GLOBAL_TIER1_FUNDS = {
    "sequoia capital", "bessemer venture partners", "lightspeed venture partners",
    "accel", "general catalyst", "insight partners", "index ventures",
    "greylock partners", "greylock", "andreessen horowitz", "a16z",
    "tiger global", "coatue", "softbank", "google ventures", "gv",
    "salesforce ventures", "microsoft m12", "m12", "battery ventures",
    "crv", "kleiner perkins", "mayfield fund", "warburg pincus",
    "goldman sachs", "jp morgan", "jpmorgan",
}

ISRAEL_FOCUSED_FUNDS = {
    "cyberstarts", "yl ventures", "glilot capital", "glilot capital partners",
    "team8", "team 8", "jerusalem venture partners", "jvp",
    "tlv partners", "viola ventures", "viola", "merlin ventures",
    "cerca partners", "awz ventures", "f2 venture capital",
    "s capital", "blumberg capital",
}


def _detect_fund_quiet_periods(df, today, month):
    signals = []
    fund_last_deal = {}

    for _, row in df.iterrows():
        lead = str(row.get("Lead Investor", "") or "").strip()
        if not lead or lead.lower() in ("nan", ""):
            continue
        # Skip global tier-1 funds — active globally, quiet in Israeli DB means nothing
        if lead.lower() in GLOBAL_TIER1_FUNDS:
            continue
        # Only flag Israel-focused funds where quiet period in our DB is meaningful
        if lead.lower() not in ISRAEL_FOCUSED_FUNDS:
            continue
        date_str = str(row.get("Round Date", "") or "").strip()
        d = _parse_date(date_str)
        if not d:
            continue
        if lead not in fund_last_deal or d > fund_last_deal[lead]:
            fund_last_deal[lead] = d

    found = 0
    for fund, last_date in fund_last_deal.items():
        months_silent = (today.year - last_date.year) * 12 + (today.month - last_date.month)
        fund_source_detail = (
            f"Source: {fund} — most recent lead deal in deals.csv: {last_date.strftime('%B %Y')} "
            f"({months_silent} months ago)"
        )
        if months_silent >= 9:
            sig = {
                "id": _make_id("fund_quiet", fund, month),
                "category": "Investor",
                "signal_type": "Fund goes quiet 6+ months",
                "priority": "Critical",
                "status": "active",
                "title": f"{fund} — no new deals in {months_silent} months",
                "entity": fund,
                "why_it_matters": "Likely raising new fund — will re-emerge with fresh capital in 3-6 months",
                "action": "Build relationship with fund before they re-emerge active",
                "source_url": "",
                "source_name": "Database",
                "source_detail": fund_source_detail,
                "detected_at": _now_iso(),
                "date_of_event": last_date.strftime("%Y-%m"),
                "notes": f"Last deal as lead investor: {last_date.strftime('%B %Y')}",
                "portfolio_relevant": False,
                "portfolio_companies": [],
            }
            signals.append(sig)
            found += 1
        elif months_silent >= 6:
            sig = {
                "id": _make_id("fund_quiet", fund, month),
                "category": "Investor",
                "signal_type": "Fund goes quiet 6+ months",
                "priority": "High",
                "status": "active",
                "title": f"{fund} — no new deals in {months_silent} months",
                "entity": fund,
                "why_it_matters": "Likely raising new fund — will re-emerge with fresh capital in 3-6 months",
                "action": "Build relationship with fund before they re-emerge active",
                "source_url": "",
                "source_name": "Database",
                "source_detail": fund_source_detail,
                "detected_at": _now_iso(),
                "date_of_event": last_date.strftime("%Y-%m"),
                "notes": f"Last deal as lead investor: {last_date.strftime('%B %Y')}",
                "portfolio_relevant": False,
                "portfolio_companies": [],
            }
            signals.append(sig)
            found += 1

    log(f"Fund quiet periods: checked {len(fund_last_deal)} funds, {found} signals found")
    return signals


def _detect_competitor_funded(companies, df, today):
    signals = []
    cutoff = today - timedelta(days=30)

    portfolio_cos = {c["name"]: c["sector"] for c in companies if c.get("is_portfolio")}

    found = 0
    for _, row in df.iterrows():
        date_str = str(row.get("Round Date", "") or "").strip()
        d = _parse_date(date_str)
        if not d or d < cutoff:
            continue
        co_name = str(row.get("Company Name", "") or "").strip()
        if co_name in LAMA_PORTFOLIO:
            continue
        sector = str(row.get("Sector Tag", "") or "").strip()
        round_size = row.get("Round Size ($M)")
        try:
            size = float(round_size) if round_size else 0
        except (TypeError, ValueError):
            size = 0

        for portfolio_co, portfolio_sector in portfolio_cos.items():
            if sector == portfolio_sector and sector:
                size_str = f"${size:.0f}M" if size else "undisclosed amount"
                sig = {
                    "id": _make_id("competitor_funded", co_name, date_str[:7]),
                    "category": "Portfolio",
                    "signal_type": "Competitor to portfolio company raises big round",
                    "priority": "Critical",
                    "status": "active",
                    "title": f"{co_name} raises {size_str} in {portfolio_co}'s sector ({sector})",
                    "entity": co_name,
                    "why_it_matters": f"Direct competitive threat to {portfolio_co} — competitor now has runway",
                    "action": f"Alert {portfolio_co} founder immediately — may accelerate hiring or product",
                    "source_url": "",
                    "source_name": "Database",
                    "source_detail": f"Source: {co_name} — Round Date: {date_str}, Size: {size_str}, Sector: {sector} in deals.csv",
                    "detected_at": _now_iso(),
                    "date_of_event": date_str,
                    "notes": "",
                    "portfolio_relevant": True,
                    "portfolio_companies": [portfolio_co],
                }
                signals.append(sig)
                found += 1
                break

    log(f"Competitor funded: checked recent deals, {found} signals found")
    return signals


# ─── Detector 2b: News-based Investor Activity ───────────────────────────────

NEW_FUND_KW = ["closes fund", "new fund", "raises fund", "fund ii", "fund iii", "fund iv",
               "fund v", "first close", "final close", "venture fund", "new vehicle",
               "raised a new", "announced a"]
PARTNER_MOVE_KW = ["joins", "named partner", "promoted to partner", "leaves", "appointed partner",
                   "new partner at", "general partner"]

# Days without news coverage before we flag a fund as going quiet
_FUND_QUIET_NEWS_DAYS = 90


def detect_investor_signals():
    """News-based investor signals — no deals.csv involved."""
    try:
        import feedparser
    except ImportError:
        log("feedparser not installed — skipping investor detector")
        return []

    signals = []
    fund_last_seen = {fund: None for fund in ISRAEL_FOCUSED_FUNDS}
    cutoff_90 = datetime.now() - timedelta(days=90)
    cutoff_30 = datetime.now() - timedelta(days=30)

    log("Running news-based investor activity monitor...")

    for feed_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            entries = feed.entries or []
            # Look back 90 days for fund activity tracking
            for entry in entries:
                text = _text(entry)
                title = entry.get("title", "")
                url = entry.get("link", "")
                pub_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_str = entry.get("published", entry.get("updated", ""))

                import calendar
                if pub_parsed:
                    pub_ts = calendar.timegm(pub_parsed)
                    entry_date = datetime.fromtimestamp(pub_ts)
                else:
                    entry_date = datetime.now()

                if entry_date < cutoff_90:
                    continue

                # Track Israeli fund mentions (for quiet period detection)
                for fund in ISRAEL_FOCUSED_FUNDS:
                    if fund in text and entry_date > (fund_last_seen[fund] or datetime.min):
                        fund_last_seen[fund] = entry_date

                # Only process recent (30-day) entries for new signals
                if entry_date < cutoff_30:
                    continue

                # GROUP H: New fund announcement
                if _contains_any(text, NEW_FUND_KW) and _contains_any(text, CYBER_KW):
                    fund_name = _extract_company_name(title, NEW_FUND_KW) or " ".join(title.split()[:4])
                    sig = {
                        "id": _make_id("new_fund", feed_name, title[:60]),
                        "category": "Investor",
                        "signal_type": "Fund closes new vehicle",
                        "priority": "High",
                        "status": "active",
                        "title": title[:160],
                        "entity": fund_name,
                        "why_it_matters": "Fresh fund = active deployment ahead — reach out for co-investment or LP intro",
                        "action": "Identify overlap with portfolio sectors and schedule partner meeting",
                        "source_url": url,
                        "source_name": feed_name,
                        "detected_at": _now_iso(),
                        "date_of_event": pub_str,
                        "notes": "",
                        "portfolio_relevant": False,
                        "portfolio_companies": [],
                    }
                    signals.append(sig)

                # GROUP I: Partner movement between funds
                if _contains_any(text, PARTNER_MOVE_KW):
                    any_fund = any(f in text for f in ISRAEL_FOCUSED_FUNDS)
                    any_cyber = _contains_any(text, CYBER_KW)
                    if any_fund or any_cyber:
                        person = _extract_company_name(title, PARTNER_MOVE_KW) or title[:60]
                        sig = {
                            "id": _make_id("partner_move", feed_name, title[:60]),
                            "category": "Investor",
                            "signal_type": "Partner moves between funds",
                            "priority": "Medium",
                            "status": "active",
                            "title": title[:160],
                            "entity": person,
                            "why_it_matters": "Partner transitions signal fund strategy shifts — new relationships possible",
                            "action": "Reach out to new partner early before their deal pipeline is full",
                            "source_url": url,
                            "source_name": feed_name,
                            "detected_at": _now_iso(),
                            "date_of_event": pub_str,
                            "notes": "",
                            "portfolio_relevant": False,
                            "portfolio_companies": [],
                        }
                        signals.append(sig)

        except Exception as e:
            log(f"Investor detector — {feed_name} error: {e}")

    # Fund quiet period: based on RSS coverage, not deals.csv
    today = datetime.now()
    quiet_found = 0
    for fund, last_seen in fund_last_seen.items():
        if last_seen is None:
            # Never seen in news at all — flag as quiet
            days_silent = 999
        else:
            days_silent = (today - last_seen).days

        if days_silent >= _FUND_QUIET_NEWS_DAYS:
            sig = {
                "id": _make_id("fund_quiet_news", fund, _month_key()),
                "category": "Investor",
                "signal_type": "Fund goes quiet 6+ months",
                "priority": "High",
                "status": "active",
                "title": f"{fund} — no news coverage in {days_silent if days_silent < 900 else '90+'} days",
                "entity": fund,
                "why_it_matters": "Likely raising new fund — will re-emerge with fresh capital in 3-6 months",
                "action": "Build relationship with fund before they re-emerge active",
                "source_url": "",
                "source_name": "RSS Monitor",
                "source_detail": f"Scanned {len(RSS_FEEDS)} RSS feeds over the last 90 days — no mention of {fund} found",
                "detected_at": _now_iso(),
                "date_of_event": last_seen.strftime("%Y-%m") if last_seen else "unknown",
                "notes": f"Last seen in news: {last_seen.strftime('%B %d, %Y') if last_seen else 'never in scanned feeds'}",
                "portfolio_relevant": False,
                "portfolio_companies": [],
            }
            signals.append(sig)
            quiet_found += 1

    log(f"Investor monitor: {quiet_found} fund-quiet signals, {len(signals) - quiet_found} other investor signals")
    return signals


# ─── Detector 3: LinkedIn Jobs Monitor ───────────────────────────────────────

def detect_linkedin_signals():
    log("Running LinkedIn Jobs monitor...")
    signals = []
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        ciso_search_urls = [
            "https://www.linkedin.com/jobs/search/?keywords=CISO&f_TPR=r604800",
            "https://www.linkedin.com/jobs/search/?keywords=chief+information+security+officer&f_TPR=r604800",
        ]
        for url in ciso_search_urls:
            try:
                time.sleep(3)
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 429 or "authwall" in resp.url.lower():
                    log("LinkedIn Jobs: blocked (429/authwall) — skipping")
                    return []
                if resp.status_code != 200:
                    log(f"LinkedIn Jobs: HTTP {resp.status_code} — skipping")
                    return []

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                job_cards = soup.find_all("div", class_=re.compile(r"job-search-card|base-card"))

                for card in job_cards[:20]:
                    title_el = card.find(["h3", "h4"])
                    company_el = card.find("h4") or card.find(class_=re.compile(r"company"))
                    title_text = title_el.get_text(strip=True) if title_el else ""
                    company_text = company_el.get_text(strip=True) if company_el else ""

                    if any(kw in title_text.lower() for kw in ["ciso", "chief information security", "chief security officer"]):
                        sig = {
                            "id": _make_id("linkedin_ciso", company_text, title_text[:40]),
                            "category": "Customer",
                            "signal_type": "New CISO appointed",
                            "priority": "High",
                            "status": "active",
                            "title": f"CISO role open at {company_text}: {title_text}",
                            "entity": company_text,
                            "why_it_matters": "Open CISO role signals security leadership transition — buying window approaching",
                            "action": "Monitor for new hire announcement — be ready to move fast",
                            "source_url": url,
                            "source_name": "LinkedIn Jobs",
                            "detected_at": _now_iso(),
                            "date_of_event": _now_iso()[:10],
                            "notes": "",
                            "portfolio_relevant": False,
                            "portfolio_companies": [],
                        }
                        signals.append(sig)

            except requests.exceptions.RequestException as e:
                log(f"LinkedIn Jobs: request error — {e}")
                return []

        log(f"LinkedIn Jobs: {len(signals)} CISO postings found, {len(signals)} new signal(s)")
    except ImportError:
        log("LinkedIn Jobs: requests or beautifulsoup4 not installed — skipping")
    except Exception as e:
        log(f"LinkedIn Jobs: unexpected error — {e}")

    return signals


# ─── Detector 4: X Monitoring Placeholder ────────────────────────────────────

def detect_x_signals():
    """
    X monitoring not yet active.
    Future implementation will monitor:
    - CISO/CTO posts about AI security pain
    - Agentic AI deployment announcements
    - MCP adoption conversations
    - Israeli cyber founder activity

    Options being evaluated:
    - X API Basic ($100/month) — fully automated
    - Apify X scraper (~$50/month) — managed scraping
    - RSS Bridge — self-hosted, free but unreliable

    Returns empty list until implementation is added.
    """
    log("X monitoring not yet active — skipping")
    return []


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_all_detectors():
    global _log_lines
    _log_lines = []

    log("Starting signal detection — Lama Partners Daily Brief")

    signals_store.set_run_status("running", log_lines=_log_lines)

    all_signals = []

    # Detector 1: RSS (DB-aware — only surfaces new information)
    log("Running RSS news monitor...")
    try:
        from data_loader import get_companies
        companies = get_companies()
        known_cos = {c["name"] for c in companies}
    except Exception:
        known_cos = set()
        companies = []
    try:
        rss_signals = detect_rss_signals(known_cos, companies)
        all_signals.extend(rss_signals)
    except Exception as e:
        log(f"RSS detector failed: {e}")

    # Detector 2: Database calculations (vesting, competitor analysis — insights FROM existing data)
    log("Running database calculations...")
    try:
        db_signals = detect_database_signals()
        all_signals.extend(db_signals)
    except Exception as e:
        log(f"Database detector failed: {e}")

    # Detector 2b: News-based investor activity
    log("Running investor activity monitor...")
    try:
        inv_signals = detect_investor_signals()
        all_signals.extend(inv_signals)
    except Exception as e:
        log(f"Investor detector failed: {e}")

    # Detector 3: LinkedIn
    try:
        li_signals = detect_linkedin_signals()
        all_signals.extend(li_signals)
    except Exception as e:
        log(f"LinkedIn detector failed: {e}")

    # Detector 4: X placeholder
    try:
        detect_x_signals()
    except Exception as e:
        log(f"X detector failed: {e}")

    # Deduplication and add
    added = signals_store.add_signals(all_signals)

    stats = signals_store.get_stats()
    log(f"Deduplication: {len(all_signals) - added} signals already seen — skipped")
    log(f"Total new signals: {added} ({stats['critical']} Critical, {stats['high']} High, {stats['medium']} Medium)")
    log("Done.")

    from datetime import timezone as tz
    now = datetime.now(tz.utc)
    next_7am = _next_7am_israel(now)

    signals_store.set_run_status(
        "complete",
        log_lines=_log_lines,
        last_run=now.isoformat(),
        next_run=next_7am,
    )

    return {"total": len(all_signals), "added": added,
            "critical": stats["critical"], "high": stats["high"], "medium": stats["medium"]}


def _next_7am_israel(now=None):
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        try:
            from backports.zoneinfo import ZoneInfo
        except ImportError:
            return None
    israel_tz = ZoneInfo("Asia/Jerusalem")
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(israel_tz)
    target = local.replace(hour=7, minute=0, second=0, microsecond=0)
    if local >= target:
        target += timedelta(days=1)
    return target.isoformat()


if __name__ == "__main__":
    result = run_all_detectors()
    print(f"\nSummary: {result}")
