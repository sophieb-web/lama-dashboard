import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROFILES_FILE = os.path.join(DATA_DIR, "Lama_Customer_Profiles.xlsx")

_customer_data = None
_overlap_data = None
_industry_data = None
_testimonials_by_company = None


def _str(v):
    s = str(v).strip() if v is not None else ""
    return "" if s.lower() in ("nan", "none") else s


def _int(v, default=0):
    try:
        f = float(v)
        return int(f) if not pd.isna(f) else default
    except (TypeError, ValueError):
        return default


def load_customer_profiles():
    global _customer_data, _overlap_data, _industry_data, _testimonials_by_company

    if not os.path.exists(PROFILES_FILE):
        print(f"[customer_loader] File not found: {PROFILES_FILE}")
        _customer_data, _overlap_data, _industry_data = {}, [], []
        return

    try:
        xl = pd.ExcelFile(PROFILES_FILE)
    except Exception as e:
        print(f"[customer_loader] Failed to open {PROFILES_FILE}: {e}")
        _customer_data, _overlap_data, _industry_data = {}, [], []
        return

    try:
        # ── Company Customer Profiles ─────────────────────────────────────────
        df = pd.read_excel(xl, sheet_name="Company Customer Profiles", header=1)
        customer_data = {}
        for _, row in df.iterrows():
            name = _str(row.get("Company"))
            if not name:
                continue
            industries_raw = _str(row.get("Top Industries (customers)"))
            industries = [i.strip() for i in industries_raw.split(",") if i.strip()]
            roles_raw = _str(row.get("Top Buyer Roles"))
            roles = [r.strip() for r in roles_raw.split(",") if r.strip()]
            customer_data[name] = {
                "total_testimonials": _int(row.get("Total Testimonials")),
                "ciso_count": _int(row.get("CISO Count")),
                "thesis_alignment_score": _int(row.get("Thesis Alignment Score")),
                "top_industries": industries,
                "top_buyer_roles": roles,
                "thesis_quote": _str(row.get("Thesis-Aligned Quote (best)")),
                "why_lama_relevant": _str(row.get("Why Lama-Relevant")),
                "key_customer_orgs": _str(row.get("Key Customer Orgs")),
            }
        _customer_data = customer_data

        # ── Customer Overlap ──────────────────────────────────────────────────
        df2 = pd.read_excel(xl, sheet_name="Customer Overlap", header=1)
        overlap_data = []
        for _, row in df2.iterrows():
            org = _str(row.get("Organization"))
            if not org:
                continue
            overlap_data.append({
                "organization": org,
                "industry": _str(row.get("Industry")),
                "count": _int(row.get("# Israeli Cyber Cos")),
                "companies": _str(row.get("Companies Used")),
                "buyer_roles": _str(row.get("Buyer Role(s)")),
                "implication": _str(row.get("Lama Implication")),
                "quote": _str(row.get("Quote Sample")),
            })
        _overlap_data = overlap_data

        # ── Industry Analysis ─────────────────────────────────────────────────
        df3 = pd.read_excel(xl, sheet_name="Industry Analysis", header=1)
        industry_data = []
        for _, row in df3.iterrows():
            industry = _str(row.get("Industry"))
            if not industry:
                continue
            industry_data.append({
                "industry": industry,
                "companies_serving": _int(row.get("# Companies Serving")),
                "testimonials": _int(row.get("# Testimonials")),
                "top_companies": _str(row.get("Top Companies in Industry")),
                "key_roles": _str(row.get("Key Buyer Roles")),
            })
        _industry_data = industry_data

        # ── All Testimonials ──────────────────────────────────────────────────
        df4 = pd.read_excel(xl, sheet_name="All Testimonials", header=1)
        by_company = {}
        for _, row in df4.iterrows():
            company = _str(row.get("Company"))
            if not company:
                continue
            quote = _str(row.get("Quote"))
            if not quote:
                continue
            t = {
                "organization": _str(row.get("Organization")),
                "role": _str(row.get("Role")),
                "industry": _str(row.get("Industry")),
                "thesis_aligned": _str(row.get("Thesis Aligned?")) == "✓ YES",
                "quote": quote,
            }
            by_company.setdefault(company, []).append(t)
        _testimonials_by_company = by_company

        print(f"[customer_loader] Loaded {len(customer_data)} profiles, "
              f"{len(overlap_data)} overlap records, {len(industry_data)} industries, "
              f"{sum(len(v) for v in by_company.values())} testimonials")

    except Exception as e:
        print(f"[customer_loader] Error reading data: {e}")
        if _customer_data is None:
            _customer_data = {}
        if _overlap_data is None:
            _overlap_data = []
        if _industry_data is None:
            _industry_data = []
        if _testimonials_by_company is None:
            _testimonials_by_company = {}


def get_customer_data():
    if _customer_data is None:
        load_customer_profiles()
    return _customer_data or {}


def get_testimonials(company_name):
    if _testimonials_by_company is None:
        load_customer_profiles()
    return (_testimonials_by_company or {}).get(company_name, [])


def get_overlap_data():
    if _overlap_data is None:
        load_customer_profiles()
    return _overlap_data or []


def get_industry_data():
    if _industry_data is None:
        load_customer_profiles()
    return _industry_data or []
