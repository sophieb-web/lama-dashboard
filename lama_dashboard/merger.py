import os
import pandas as pd
from datetime import date

import staging as st

DEALS_CSV = os.path.join(os.path.dirname(__file__), "data", "deals.csv")
LAMA_PORTFOLIO = {"Terra", "Orion Security", "Root", "Capsule", "Jit"}


def _load_df():
    df = pd.read_csv(DEALS_CSV, skiprows=2, dtype=str)
    df.columns = [c.strip() for c in df.columns]
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
        rows.append(",".join(
            f'"{str(v).replace(chr(34), chr(34)+chr(34))}"' if "," in str(v or "") or '"' in str(v or "") else str(v or "")
            for v in row
        ))

    with open(DEALS_CSV, "w", encoding="utf-8", newline="\n") as f:
        f.write(header1 + "\n")
        f.write(header2 + "\n")
        f.write(col_line + "\n")
        f.write("\n".join(rows) + "\n")


def merge_approved():
    approved = st.get_approved()
    if not approved:
        return {"merged": 0, "new_companies": 0, "new_rounds": 0, "acquisitions": 0}

    df = _load_df()
    pushed_ids = []
    counts = {"new_rounds": 0, "new_companies": 0, "acquisitions": 0}

    for finding in approved:
        # Skip portfolio companies — require manual review
        if finding.get("is_portfolio"):
            continue

        ftype = finding["type"]
        name = finding["company_name"]
        data = finding["data"]

        try:
            if ftype == "new_round" and finding.get("company_in_db"):
                existing = df[df["Company Name"].str.strip().str.lower() == name.strip().lower()]
                if existing.empty:
                    continue
                # Copy company profile from first matching row
                template = existing.iloc[0].copy()
                template["Round Type"] = data.get("round_type", "")
                template["Round Date"] = data.get("round_date", "")
                template["Round Size ($M)"] = data.get("round_size", "")
                template["Lead Investor"] = data.get("lead_investor", "")
                template["Co-Investors"] = data.get("co_investors", "")
                template["Round Valuation ($M)"] = ""
                template["Source"] = finding.get("source_url", finding.get("source_name", ""))
                template["Notes"] = f"Auto-added from {finding['source_name']} scrape"
                df = pd.concat([df, pd.DataFrame([template])], ignore_index=True)
                counts["new_rounds"] += 1

            elif ftype == "new_company":
                new_row = {col: "" for col in df.columns}
                new_row["Company Name"] = name
                new_row["Description (1 line)"] = data.get("description", "")
                new_row["HQ City / Region"] = data.get("hq", "")
                new_row["Sector Tag"] = data.get("sector_tag", "")
                new_row["Founding Year"] = data.get("founded", "")
                new_row["Round Type"] = data.get("round_type", "")
                new_row["Round Date"] = data.get("round_date", "")
                new_row["Round Size ($M)"] = data.get("round_size", "")
                new_row["Lead Investor"] = data.get("lead_investor", "")
                new_row["Co-Investors"] = data.get("co_investors", "")
                new_row["HQ Country"] = "Israel"
                new_row["Acquired?"] = "No"
                new_row["Source"] = finding.get("source_url", finding.get("source_name", ""))
                new_row["Notes"] = f"Auto-added from {finding['source_name']} — {finding['headline'][:80]}"
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                counts["new_companies"] += 1

            elif ftype == "acquisition":
                mask = df["Company Name"].str.strip().str.lower() == name.strip().lower()
                df.loc[mask, "Acquired?"] = "Yes"
                df.loc[mask, "Acquirer"] = data.get("acquirer", "")
                if data.get("exit_size"):
                    df.loc[mask, "Exit Size ($M)"] = data.get("exit_size", "")
                counts["acquisitions"] += 1

            pushed_ids.append(finding["id"])

        except Exception as e:
            print(f"[merger] Error processing {name}: {e}")
            continue

    _save_df(df)
    st.clear_pushed(pushed_ids)

    total = sum(counts.values())
    return {"merged": total, **counts}
