import pandas as pd
import numpy as np
import os
import re

DATA_FILE = "data/deals.csv"
TAXONOMY_FILE = "data/taxonomy.csv"
EXCEL_FILE = "data/Lama_Israeli_Cyber_Deal_Database_v8.xlsx"

LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}

SECTOR_COLORS = {
    "AI Security": "#E11D48",
    "Cloud Security": "#0EA5E9",
    "Data Security": "#10B981",
    "Identity & Access": "#F59E0B",
    "Application Security": "#EF4444",
    "Supply Chain Security": "#06B6D4",
    "Security Operations": "#6366F1",
    "Network Security": "#84CC16",
    "Endpoint & XDR": "#F97316",
    "OT / ICS / IoT": "#EC4899",
    "GRC & Compliance": "#14B8A6",
    "Threat Intelligence": "#D97706",
}

# Investor name normalization map
INVESTOR_NORMALIZE = {
    "bessemer": "Bessemer Venture Partners",
    "bessemer venture": "Bessemer Venture Partners",
    "bessemer venture partners": "Bessemer Venture Partners",
    "battery ventures": "Battery Ventures",
    "battery": "Battery Ventures",
    "insight partners": "Insight Partners",
    "insight venture partners": "Insight Partners",
    "yl ventures": "YL Ventures",
    "cyberstarts": "CyberStarts",
    "glilot capital": "Glilot Capital Partners",
    "glilot": "Glilot Capital Partners",
    "glilot capital partners": "Glilot Capital Partners",
    "sequoia capital": "Sequoia Capital",
    "sequoia": "Sequoia Capital",
    "lightspeed": "Lightspeed Venture Partners",
    "lightspeed venture partners": "Lightspeed Venture Partners",
    "lightspeed venture partners israel": "Lightspeed Venture Partners",
    "greylock": "Greylock",
    "greylock partners": "Greylock",
    "team8": "Team8",
    "team 8": "Team8",
    "pico venture partners": "PICO Venture Partners",
    "lama partners": "Lama Partners",
    "norwest": "Norwest Venture Partners",
    "norwest venture partners": "Norwest Venture Partners",
    "viola ventures": "Viola Ventures",
    "viola": "Viola Ventures",
}

LAMA_LP_INVESTORS = {
    "Battery Ventures", "Bessemer Venture Partners", "Insight Partners",
    "Scott Tobin", "Bob Goodman", "Jeff Horing"
}

_df = None
_companies = None
_taxonomy = None


def _normalize_investor(name):
    key = name.strip().lower()
    return INVESTOR_NORMALIZE.get(key, name.strip())


def load_data():
    global _df, _companies, _taxonomy

    from customer_loader import get_customer_data
    customer_data = get_customer_data()

    base = os.path.dirname(__file__)

    # Load taxonomy
    tax_path = os.path.join(base, TAXONOMY_FILE)
    tax_df = pd.read_csv(tax_path, skiprows=1)
    tax_df.columns = ["#", "Sector Tag", "Description", "Example Companies"]
    _taxonomy = tax_df.to_dict("records")

    # Load deals — skip first 2 header rows (row 0 = title, row 1 = section labels)
    csv_path = os.path.join(base, DATA_FILE)
    try:
        df = pd.read_csv(csv_path, skiprows=2, dtype=str)
    except Exception:
        xlsx_path = os.path.join(base, EXCEL_FILE)
        df = pd.read_excel(xlsx_path, sheet_name="Deals", skiprows=2, dtype=str)

    # Normalize column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # Drop completely empty rows
    df = df.dropna(how="all")
    df = df[df["Company Name"].notna() & (df["Company Name"].str.strip() != "")]

    # Numeric coercion
    for col in ["Total Raised ($M)", "Post-Money Valuation ($M)", "Round Size ($M)",
                "Round Valuation ($M)", "Exit Size ($M)", "Founding Year"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(",", "").str.replace("$", ""),
                                    errors="coerce")

    # Normalize sector tags
    df["Sector Tag"] = df["Sector Tag"].fillna("Unknown").str.strip()

    # Portfolio flag
    df["is_portfolio"] = df["Company Name"].isin(LAMA_PORTFOLIO)

    # 8200 flag
    df["is_8200"] = df["Military Unit"].fillna("").str.contains("8200", case=False)

    # Acquired flag
    df["is_acquired"] = df["Acquired?"].fillna("").str.strip().str.lower() == "yes"

    _df = df

    # Build deduplicated company list (keep first row per company for profile data,
    # but aggregate deal info)
    companies = []
    for name, group in df.groupby("Company Name", sort=False):
        first = group.iloc[0]
        # Latest round info — include rows with a date or size even if Round Type is empty
        has_type = group["Round Type"].notna() & (group["Round Type"].str.strip() != "")
        has_date = group["Round Date"].notna() & (group["Round Date"].str.strip() != "")
        has_size = group["Round Size ($M)"].notna()
        deal_rows = group[has_type | has_date | has_size]

        # Determine stage from round types
        stage = _determine_stage(deal_rows, first)

        # Collect all investors
        lead_investors = []
        for _, row in deal_rows.iterrows():
            lead = str(row.get("Lead Investor", "") or "").strip()
            if lead and lead.lower() not in ("nan", ""):
                lead_investors.append(_normalize_investor(lead))

        co_investors = []
        for _, row in deal_rows.iterrows():
            co = str(row.get("Co-Investors", "") or "").strip()
            if co and co.lower() not in ("nan", ""):
                for inv in co.split(","):
                    inv = inv.strip()
                    if inv:
                        co_investors.append(_normalize_investor(inv))

        # Deals list for funding history
        deals = []
        for _, row in deal_rows.iterrows():
            deals.append({
                "round_type": str(row.get("Round Type", "") or ""),
                "round_date": str(row.get("Round Date", "") or ""),
                "round_size": _safe_float(row.get("Round Size ($M)")),
                "lead_investor": _normalize_investor(str(row.get("Lead Investor", "") or "")),
                "co_investors": str(row.get("Co-Investors", "") or ""),
                "round_valuation": _safe_float(row.get("Round Valuation ($M)")),
            })

        company = {
            "name": name,
            "website": str(first.get("Website", "") or ""),
            "pitchbook_url": str(first.get("PitchBook URL", "") or ""),
            "founding_year": _safe_int(first.get("Founding Year")),
            "employees": str(first.get("Employees", "") or ""),
            "description": str(first.get("Description (1 line)", "") or ""),
            "hq_city": str(first.get("HQ City / Region", "") or ""),
            "hq_country": str(first.get("HQ Country", "") or ""),
            "sector": str(first.get("Sector Tag", "") or "Unknown"),
            "sector_color": SECTOR_COLORS.get(str(first.get("Sector Tag", "") or ""), "#6366F1"),
            "founders": str(first.get("Founders", "") or ""),
            "military_unit": str(first.get("Military Unit", "") or ""),
            "last_role": str(first.get("Last Role Before Founding", "") or ""),
            "founder_linkedin": str(first.get("Founder LinkedIn (to fill)", "") or ""),
            "angels": str(first.get("Angels Involved", "") or ""),
            "customers": str(first.get("Customers (public)", "") or ""),
            "total_raised": _safe_float(first.get("Total Raised ($M)")),
            "valuation": _safe_float(first.get("Post-Money Valuation ($M)")),
            "acquired": bool(first.get("is_acquired", False)),
            "acquirer": str(first.get("Acquirer", "") or ""),
            "exit_size": _safe_float(first.get("Exit Size ($M)")),
            "is_portfolio": bool(first.get("is_portfolio", False)),
            "is_8200": bool(first.get("is_8200", False)),
            "stage": stage,
            "lead_investors": list(dict.fromkeys(lead_investors)),
            "all_investors": list(dict.fromkeys(lead_investors + co_investors)),
            "deals": deals,
            "notes": str(first.get("Notes", "") or ""),
            "source": str(first.get("Source", "") or ""),
        }

        # Merge customer profile data
        cp = customer_data.get(name, {})
        company["total_testimonials"] = cp.get("total_testimonials", 0)
        company["ciso_count"] = cp.get("ciso_count", 0)
        company["thesis_alignment_score"] = cp.get("thesis_alignment_score", 0)
        company["top_industries"] = cp.get("top_industries", [])
        company["top_buyer_roles"] = cp.get("top_buyer_roles", [])
        company["thesis_quote"] = cp.get("thesis_quote", "")
        company["why_lama_relevant"] = cp.get("why_lama_relevant", "")
        company["key_customer_orgs"] = cp.get("key_customer_orgs", "")

        companies.append(company)

    _companies = companies
    print(f"[data_loader] Loaded {len(_df)} deal rows, {len(_companies)} unique companies")
    return _companies


def _safe_float(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    f = _safe_float(val)
    return int(f) if f is not None else None


def _determine_stage(deal_rows, first_row):
    """Determine the most advanced stage from all deal rows."""
    if bool(first_row.get("is_acquired", False)):
        return "Acquired"

    stage_order = {
        "ipo/public": "Public",
        "public": "Public",
        "series d": "Series D+",
        "series e": "Series D+",
        "series f": "Series D+",
        "growth": "Series D+",
        "later stage vc": "Series C+",
        "series c": "Series C+",
        "series b": "Series B",
        "series a": "Series A",
        "early stage vc": "Series A",
        "seed": "Seed",
        "accelerator": "Seed",
        "angel": "Seed",
        "pre-seed": "Seed",
    }
    stage_rank = {
        "Public": 7, "Series D+": 6, "Series C+": 5,
        "Series B": 4, "Series A": 3, "Seed": 2, "Unknown": 1
    }

    best = "Unknown"
    for _, row in deal_rows.iterrows():
        rt = str(row.get("Round Type", "") or "").strip().lower()
        mapped = stage_order.get(rt)
        if mapped and stage_rank.get(mapped, 0) > stage_rank.get(best, 0):
            best = mapped
    return best


def get_companies():
    if _companies is None:
        load_data()
    return _companies


def get_raw_df():
    if _df is None:
        load_data()
    return _df


def get_taxonomy():
    if _taxonomy is None:
        load_data()
    return _taxonomy


def get_stats():
    companies = get_companies()
    df = get_raw_df()

    total_raised = sum(c["total_raised"] for c in companies if c["total_raised"])
    unicorns = [c for c in companies if c["valuation"] and c["valuation"] >= 1000]
    acquired = [c for c in companies if c["acquired"]]
    eight200 = [c for c in companies if c["is_8200"]]
    pct_8200 = round(len(eight200) / len(companies) * 100) if companies else 0

    # Exits in last 2 years (2024-2026)
    recent_exits = [c for c in acquired if True]  # all acquired for now

    # Funding by year
    yearly = {}
    for _, row in df.iterrows():
        date_str = str(row.get("Round Date", "") or "")
        size = _safe_float(row.get("Round Size ($M)"))
        if not size or not date_str or date_str.lower() == "nan":
            continue
        year = None
        m = re.search(r"(20\d\d)", date_str)
        if m:
            year = int(m.group(1))
        if year and 2015 <= year <= 2026:
            if year not in yearly:
                yearly[year] = {"total": 0, "count": 0}
            yearly[year]["total"] += size
            yearly[year]["count"] += 1

    # Sector breakdown
    sector_data = {}
    for c in companies:
        s = c["sector"]
        if s not in sector_data:
            sector_data[s] = {"count": 0, "total_raised": 0, "color": c["sector_color"]}
        sector_data[s]["count"] += 1
        if c["total_raised"]:
            sector_data[s]["total_raised"] += c["total_raised"]

    return {
        "total_companies": len(companies),
        "total_raised_b": round(total_raised / 1000, 2),
        "total_raised_m": round(total_raised, 0),
        "unicorn_count": len(unicorns),
        "acquired_count": len(acquired),
        "eight200_count": len(eight200),
        "eight200_pct": pct_8200,
        "portfolio_count": len([c for c in companies if c["is_portfolio"]]),
        "yearly_funding": {str(k): v for k, v in sorted(yearly.items())},
        "sector_breakdown": sector_data,
        "sector_colors": SECTOR_COLORS,
    }


def get_investors():
    companies = get_companies()
    investor_map = {}

    for company in companies:
        for _, row in get_raw_df()[get_raw_df()["Company Name"] == company["name"]].iterrows():
            round_type = str(row.get("Round Type", "") or "").strip()
            round_date = str(row.get("Round Date", "") or "").strip()
            round_size = _safe_float(row.get("Round Size ($M)"))
            sector = company["sector"]

            # Lead investor
            lead = str(row.get("Lead Investor", "") or "").strip()
            if lead and lead.lower() not in ("nan", ""):
                lead_norm = _normalize_investor(lead)
                _add_investor_deal(investor_map, lead_norm, company["name"], sector,
                                   round_type, round_date, round_size, is_lead=True)

            # Co-investors
            co = str(row.get("Co-Investors", "") or "").strip()
            if co and co.lower() not in ("nan", ""):
                for inv in co.split(","):
                    inv = inv.strip()
                    if inv:
                        inv_norm = _normalize_investor(inv)
                        _add_investor_deal(investor_map, inv_norm, company["name"], sector,
                                           round_type, round_date, round_size, is_lead=False)

    # Build sorted list
    result = []
    for name, data in investor_map.items():
        result.append({
            "name": name,
            "portfolio_count": len(data["companies"]),
            "total_deployed": round(data["total_deployed"], 1),
            "lead_count": data["lead_count"],
            "companies": sorted(data["companies"]),
            "sectors": dict(sorted(data["sectors"].items(), key=lambda x: -x[1])[:5]),
            "stage_focus": _determine_investor_stage(data["round_types"]),
            "most_recent_deal": data.get("most_recent_deal", ""),
            "is_lama_lp": name in LAMA_LP_INVESTORS,
        })

    result.sort(key=lambda x: -x["portfolio_count"])
    return result


def _add_investor_deal(investor_map, name, company, sector, round_type,
                       round_date, round_size, is_lead):
    if name not in investor_map:
        investor_map[name] = {
            "companies": set(),
            "total_deployed": 0,
            "lead_count": 0,
            "sectors": {},
            "round_types": [],
            "most_recent_deal": "",
        }
    d = investor_map[name]
    d["companies"].add(company)
    if round_size:
        d["total_deployed"] += round_size
    if is_lead:
        d["lead_count"] += 1
    if sector:
        d["sectors"][sector] = d["sectors"].get(sector, 0) + 1
    if round_type:
        d["round_types"].append(round_type.lower())
    if round_date and round_date.lower() not in ("nan", ""):
        if not d["most_recent_deal"] or round_date > d["most_recent_deal"]:
            d["most_recent_deal"] = round_date


def _determine_investor_stage(round_types):
    has_seed = any(rt in ("seed", "accelerator", "angel", "pre-seed") for rt in round_types)
    has_early = any("series a" in rt or "early stage" in rt for rt in round_types)
    has_growth = any(rt in ("series c", "series d", "series e", "growth", "later stage vc") for rt in round_types)
    if has_growth and has_early:
        return "Multi-stage"
    if has_growth:
        return "Growth"
    if has_early:
        return "Early"
    if has_seed:
        return "Seed"
    return "Unknown"
