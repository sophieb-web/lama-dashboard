"""
Customer testimonial scraper for Israeli cyber companies.
Scrapes name, role, organization, and quote from each company's website.
"""

import asyncio
import json
import re
import time
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import httpx
from bs4 import BeautifulSoup
import anthropic as _anthropic


# ── Config ────────────────────────────────────────────────────────────────────
CONCURRENCY = 8          # parallel requests
REQUEST_TIMEOUT = 20     # seconds per page
MAX_PAGES_PER_SITE = 6   # homepage + top candidate pages
OUTPUT_FILE = "customer_testimonials.xlsx"
LOG_FILE = "scraper.log"
CHECKPOINT_FILE = "scraper_checkpoint.json"

TESTIMONIAL_PAGES = [
    "", "/customers", "/customer-stories", "/case-studies", "/testimonials",
    "/success-stories", "/references", "/clients", "/reviews", "/about",
    "/trust", "/social-proof",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────
def normalize_url(website: str) -> str:
    if not website.startswith("http"):
        website = "https://" + website
    parsed = urlparse(website)
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_text_blocks(html: str) -> str:
    """Strip HTML, keep text content under 12k chars for LLM context."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines)[:12000]



async def fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str, str] | tuple[None, None]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            final_url = str(r.url)
            return r.text, final_url
    except Exception as e:
        log.debug(f"  fetch failed {url}: {e}")
    return None, None


TESTIMONIAL_LINK_KEYWORDS = [
    "customer", "testimonial", "case-stud", "success-stor", "review",
    "social-proof", "trust", "references", "clients",
]

def find_testimonial_links(html: str, base_url: str) -> list[str]:
    """Extract internal links from homepage that look like testimonial pages."""
    soup = BeautifulSoup(html, "html.parser")
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0].strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        # Only follow links within the same domain
        if not full.startswith(base_url):
            continue
        path = urlparse(full).path.lower()
        if any(kw in path for kw in TESTIMONIAL_LINK_KEYWORDS):
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links[:MAX_PAGES_PER_SITE - 1]  # leave room for homepage


async def collect_site_text(client: httpx.AsyncClient, base_url: str) -> str:
    """Fetch homepage, discover real testimonial links, then fetch those."""
    homepage_html, final_base = await fetch_page(client, base_url)
    if not homepage_html:
        return ""

    real_base = f"{urlparse(final_base).scheme}://{urlparse(final_base).netloc}"
    homepage_text = extract_text_blocks(homepage_html)
    texts = [homepage_text]

    candidate_urls = find_testimonial_links(homepage_html, real_base)
    if not candidate_urls:
        candidate_urls = [real_base + p for p in TESTIMONIAL_PAGES[1:MAX_PAGES_PER_SITE]]

    for url in candidate_urls:
        if len(texts) >= MAX_PAGES_PER_SITE:
            break
        html, _ = await fetch_page(client, url)
        if html:
            texts.append(extract_text_blocks(html))

    combined = "\n\n---PAGE BREAK---\n\n".join(texts)
    if _os.environ.get("DEBUG_TEXT"):
        with open("debug_extracted_text.txt", "w", encoding="utf-8") as f:
            f.write(combined)
        log.info("  Wrote extracted text to debug_extracted_text.txt")
    return combined


# ── LLM extraction ────────────────────────────────────────────────────────────
import os as _os
_api_key = _os.environ.get("ANTHROPIC_API_KEY") or _os.environ.get("ANTHROPIC_KEY")
if not _api_key:
    raise EnvironmentError(
        "Set ANTHROPIC_API_KEY before running:\n"
        "  Windows PowerShell:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
        "  Windows CMD:         set ANTHROPIC_API_KEY=sk-ant-...\n"
        "  or add it to a .env file and load it with python-dotenv."
    )
_client = _anthropic.Anthropic(api_key=_api_key)

EXTRACT_PROMPT = """You are extracting customer testimonials from website text.

Return a JSON array of testimonial objects. Each object must have ONLY these keys:
- "name": full name of the person quoted (string, or null if unknown)
- "role": their job title (string, or null)
- "organization": the specific company or organization name the person works at (string, or null). Must be a real named entity — NOT a generic industry label.
- "industry": the industry or sector (e.g. "Financial Services", "Healthcare", "Retail", "Government") — null if not mentioned
- "quote": the exact testimonial text (string)

IMPORTANT distinction:
- "organization" = a specific named entity, e.g. "Goldman Sachs", "Pfizer", "U.S. Army"
- "industry" = a sector category, e.g. "Financial Services", "Healthcare", "Defense"
- If you only see an industry label with no specific company name, set organization=null and put it in industry instead.

Rules:
- Only include real customer testimonials/quotes — not employee bios, press quotes, or generic marketing copy
- If there are no testimonials, return []
- Do not invent or infer data — use null for missing fields
- Return ONLY the JSON array, no other text

Website text:
\"\"\"
{text}
\"\"\"
"""


TESTIMONIAL_KEYWORDS = [
    "testimonial", "quote", "said", "says", "review", "customer story",
    "case study", "success story", "our customers", "what our", "hear from",
    "trusted by", "clients say", "used by", "customer logo", '"', "“",
]

def has_testimonial_signals(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in TESTIMONIAL_KEYWORDS)


def extract_testimonials_llm(company: str, text: str) -> list[dict]:
    if not text.strip():
        return []
    if not has_testimonial_signals(text):
        log.info(f"  {company}: no testimonial signals, skipping LLM call")
        return []
    try:
        msg = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": EXTRACT_PROMPT.format(text=text[:12000])}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception as e:
        log.warning(f"  LLM extraction failed for {company}: {e}")
    return []


# ── Checkpoint ────────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(done: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(done, f)


# ── Main scrape loop ──────────────────────────────────────────────────────────
async def scrape_company(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    company: str,
    website: str,
) -> list[dict]:
    async with sem:
        base_url = normalize_url(website)
        log.info(f"Scraping {company} → {base_url}")
        text = await collect_site_text(client, base_url)
        if not text:
            log.info(f"  No content fetched for {company}")
            return []
        testimonials = extract_testimonials_llm(company, text)
        log.info(f"  {company}: {len(testimonials)} testimonials found")
        for t in testimonials:
            t["company"] = company
            t["website"] = website
        return testimonials


async def run(companies: list[tuple[str, str]]) -> list[dict]:
    checkpoint = load_checkpoint()
    all_results = []

    # Restore previous results
    for company, _ in companies:
        if company in checkpoint:
            all_results.extend(checkpoint[company])

    pending = [(c, w) for c, w in companies if c not in checkpoint]
    log.info(f"Resuming: {len(checkpoint)} done, {len(pending)} remaining")

    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(max_connections=CONCURRENCY + 4, max_keepalive_connections=CONCURRENCY)

    async def scrape_and_tag(c, w):
        try:
            results = await scrape_company(sem, client, c, w)
            return c, results
        except Exception as e:
            log.error(f"Unhandled error for {c}: {e}")
            return c, []

    async with httpx.AsyncClient(headers=HEADERS, limits=limits) as client:
        tagged = await asyncio.gather(
            *[scrape_and_tag(c, w) for c, w in pending]
        )

        for done_count, (company_name, results) in enumerate(tagged, 1):
            checkpoint[company_name] = results
            all_results.extend(results)

            if done_count % 10 == 0:
                save_checkpoint(checkpoint)
                log.info(f"Progress: {done_count}/{len(pending)} companies processed")

    save_checkpoint(checkpoint)
    return all_results


def main(test_mode: bool = False, company_filter: str = None):
    df = pd.read_excel("Lama_Israeli_Cyber_Deal_Database_v8.xlsx", header=2)
    companies = (
        df[["Company Name", "Website"]]
        .dropna(subset=["Website"])
        .drop_duplicates("Company Name")
        .values.tolist()
    )
    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c[0].lower()]
        log.info(f"Filtered to {len(companies)} companies matching '{company_filter}'")
    elif test_mode:
        companies = companies[:10]
        log.info(f"TEST MODE: running {len(companies)} companies only")
    else:
        log.info(f"Loaded {len(companies)} companies")

    results = asyncio.run(run(companies))

    if results:
        out_df = pd.DataFrame(results, columns=["company", "website", "name", "role", "organization", "industry", "quote"])
        out_df.to_excel(OUTPUT_FILE, index=False)
        log.info(f"Saved {len(results)} testimonials to {OUTPUT_FILE}")
    else:
        log.info("No testimonials found.")


if __name__ == "__main__":
    import sys
    test = "--test" in sys.argv
    company_filter = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--company"), None)
    main(test_mode=test, company_filter=company_filter)
