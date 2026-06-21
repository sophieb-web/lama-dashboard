import os
import pandas as pd
from datetime import date

import staging as st

DEALS_CSV = os.path.join(os.path.dirname(__file__), "data", "deals.csv")
LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}


def _log(msg):
    print(f"[merger] {msg}", flush=True)


def _s(v):
    """Convert any value to string for insertion into the str-typed DataFrame."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def _load_df():
    df = pd.read_csv(DEALS_CSV, skiprows=2, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    _log(f"Loaded {len(df)} rows from {DEALS_CSV}")
    return df


def _save_df(df):
    # Re-sort: portfolio first, then alphabetical
    df["_portfolio"] = df["Company Name"].isin(LAMA_PORTFOLIO)
    df = df.sort_values(["_portfolio", "Company Name"], ascending=[False, True])
    df = df.drop(columns=["_portfolio"])

    # Preserve the two-row header
    header1 = ("Israeli Cyber Ecosystem — Deal Database | Lama Partners | Jun 2026 | "
                "331 companies | 485 deal rows | Sources: PitchBook + Startup Nation Finder + Web Scraping"
                + "," * 27)
    header2 = ("COMPANY INFO — repeats on every deal row" + "," * 18 +
                "DEAL INFO — changes per row" + "," * 5 + "META,")
    col_line = ",".join(df.columns)

    rows = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            s = "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
            if "," in s or '"' in s or "\n" in s:
                s = '"' + s.replace('"', '""') + '"'
            cells.append(s)
        rows.append(",".join(cells))

    with open(DEALS_CSV, "w", encoding="utf-8", newline="\n") as f:
        f.write(header1 + "\n")
        f.write(header2 + "\n")
        f.write(col_line + "\n")
        f.write("\n".join(rows) + "\n")

    _log(f"Saved {len(df)} rows to {DEALS_CSV}")


def merge_approved():
    approved = st.get_approved()
    _log(f"Found {len(approved)} approved finding(s)")

    if not approved:
        return {"merged": 0, "new_companies": 0, "new_rounds": 0, "acquisitions": 0}

    df = _load_df()
    rows_before = len(df)
    pushed_ids = []
    counts = {"new_rounds": 0, "new_companies": 0, "acquisitions": 0}

    for finding in approved:
        name = finding["company_name"]

        # Portfolio companies require manual review
        if finding.get("is_portfolio"):
            _log(f"SKIP (portfolio): {name}")
            continue

        ftype = finding["type"]
        data = finding["data"]
        _log(f"Processing [{ftype}] {name} (round={data.get('round_type')} size={data.get('round_size')}M)")

        try:
            if ftype == "new_round" and finding.get("company_in_db"):
                existing = df[df["Company Name"].str.strip().str.lower() == name.strip().lower()]
                if existing.empty:
                    _log(f"  SKIP: '{name}' marked company_in_db but not found in CSV")
                    continue
                template = existing.iloc[0].copy()
                template["Round Type"] = _s(data.get("round_type"))
                template["Round Date"] = _s(data.get("round_date"))
                template["Round Size ($M)"] = _s(data.get("round_size"))
                template["Lead Investor"] = _s(data.get("lead_investor"))
                template["Co-Investors"] = _s(data.get("co_investors"))
                template["Round Valuation ($M)"] = ""
                template["Source"] = _s(finding.get("source_url") or finding.get("source_name"))
                template["Notes"] = f"Auto-added from {finding['source_name']} scrape"
                df = pd.concat([df, pd.DataFrame([template])], ignore_index=True)
                counts["new_rounds"] += 1
                _log(f"  + New round row added for {name}")

            elif ftype == "new_company":
                new_row = {col: "" for col in df.columns}
                new_row["Company Name"] = name
                new_row["Description (1 line)"] = _s(data.get("description"))
                new_row["HQ City / Region"] = _s(data.get("hq"))
                new_row["Sector Tag"] = _s(data.get("sector_tag"))
                new_row["Founding Year"] = _s(data.get("founded"))
                new_row["Round Type"] = _s(data.get("round_type"))
                new_row["Round Date"] = _s(data.get("round_date"))
                new_row["Round Size ($M)"] = _s(data.get("round_size"))
                new_row["Lead Investor"] = _s(data.get("lead_investor"))
                new_row["Co-Investors"] = _s(data.get("co_investors"))
                new_row["HQ Country"] = "Israel"
                new_row["Acquired?"] = "No"
                new_row["Source"] = _s(finding.get("source_url") or finding.get("source_name"))
                new_row["Notes"] = f"Auto-added from {finding['source_name']} — {finding['headline'][:80]}"
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                counts["new_companies"] += 1
                _log(f"  + New company row added for {name}")

            elif ftype == "acquisition":
                mask = df["Company Name"].str.strip().str.lower() == name.strip().lower()
                matched = int(mask.sum())
                df.loc[mask, "Acquired?"] = "Yes"
                df.loc[mask, "Acquirer"] = _s(data.get("acquirer"))
                if data.get("exit_size"):
                    df.loc[mask, "Exit Size ($M)"] = _s(data.get("exit_size"))
                counts["acquisitions"] += 1
                _log(f"  + Acquisition flagged for {name} ({matched} row(s) updated)")

            pushed_ids.append(finding["id"])

        except Exception as e:
            _log(f"  ERROR processing {name}: {e}")
            continue

    _log(f"Rows before: {rows_before} | after: {len(df)} | delta: {len(df) - rows_before}")
    _save_df(df)
    st.clear_pushed(pushed_ids)

    total = sum(counts.values())
    _log(f"Done — merged {total} finding(s): {counts}")
    return {"merged": total, **counts}
