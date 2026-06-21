import os
import threading
from flask import Flask, render_template, jsonify, request

from data_loader import load_data, get_companies, get_stats, get_investors, get_taxonomy, get_raw_df, SECTOR_COLORS, LAMA_PORTFOLIO
from context_loader import load_context, get_combined_context

app = Flask(__name__)

# Load everything at startup
load_data()
load_context()

# Start background scheduler (Monday 9am Israel time auto-scrape)
try:
    from scheduler import start_scheduler
    start_scheduler()
except Exception as _e:
    app.logger.warning(f"Scheduler not started: {_e}")


# ─── API routes ──────────────────────────────────────────────────────────────

@app.route("/api/companies")
def api_companies():
    companies = get_companies()
    return jsonify(companies)


@app.route("/api/companies/<path:name>")
def api_company(name):
    companies = get_companies()
    match = next((c for c in companies if c["name"].lower() == name.lower()), None)
    if not match:
        return jsonify({"error": "Not found"}), 404

    # Related companies (same sector, excluding self)
    same_sector = [c for c in companies
                   if c["sector"] == match["sector"] and c["name"] != match["name"]]
    same_sector.sort(key=lambda x: -(x["total_raised"] or 0))
    match["related"] = same_sector[:5]
    return jsonify(match)


@app.route("/api/investors")
def api_investors():
    return jsonify(get_investors())


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/taxonomy")
def api_taxonomy():
    return jsonify(get_taxonomy())


@app.route("/api/deals")
def api_deals():
    import numpy as np
    df = get_raw_df()
    # Only rows that have a round type filled in
    deal_rows = df[df["Round Type"].notna() & (df["Round Type"].str.strip() != "")]
    deals = []
    for _, row in deal_rows.iterrows():
        def v(col):
            val = row.get(col)
            if val is None: return None
            if isinstance(val, float) and np.isnan(val): return None
            s = str(val).strip()
            return None if s.lower() in ("nan", "none", "") else s

        def vf(col):
            val = row.get(col)
            if val is None: return None
            try:
                f = float(val)
                return None if np.isnan(f) else f
            except (ValueError, TypeError):
                return None

        deals.append({
            "company":         v("Company Name"),
            "sector":          v("Sector Tag") or "Unknown",
            "round_type":      v("Round Type"),
            "round_date":      v("Round Date"),
            "round_size":      vf("Round Size ($M)"),
            "lead_investor":   v("Lead Investor"),
            "co_investors":    v("Co-Investors"),
            "round_valuation": vf("Round Valuation ($M)"),
            "is_portfolio":    v("Company Name") in LAMA_PORTFOLIO,
        })
    return jsonify(deals)


@app.route("/api/query", methods=["POST"])
def api_query():
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    from query_engine import query
    companies = get_companies()
    # Slim down company objects for the API
    slim = [{
        "name": c["name"], "sector": c["sector"], "founding_year": c["founding_year"],
        "total_raised": c["total_raised"], "valuation": c["valuation"],
        "stage": c["stage"], "acquired": c["acquired"], "acquirer": c["acquirer"],
        "is_portfolio": c["is_portfolio"], "is_8200": c["is_8200"],
        "military_unit": c["military_unit"], "founders": c["founders"],
        "description": c["description"], "employees": c["employees"],
        "lead_investors": c["lead_investors"], "notes": c["notes"],
    } for c in companies]

    context = get_combined_context(30000)
    answer = query(question, slim, context)
    return jsonify({"answer": answer})


# ─── Page routes ─────────────────────────────────────────────────────────────

@app.route("/")
def map_page():
    stats = get_stats()
    sector_colors_json = SECTOR_COLORS
    return render_template("map.html", stats=stats, sector_colors=sector_colors_json)


@app.route("/companies")
def companies_page():
    return render_template("companies.html")


@app.route("/investors")
def investors_page():
    return render_template("investors.html")


@app.route("/intelligence")
def intelligence_page():
    stats = get_stats()
    return render_template("intelligence.html", stats=stats)


@app.route("/deals")
def deals_page():
    return render_template("deals.html")


@app.route("/query")
def query_page():
    return render_template("query.html")


@app.route("/update")
def update_page():
    return render_template("update.html")


# ─── Update Center API ────────────────────────────────────────────────────────

@app.route("/api/staging")
def api_staging():
    import staging as st
    data = st.load_staging()
    return jsonify(data)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    import staging as st
    data = st.load_staging()
    if data.get("scrape_status") == "running":
        return jsonify({"status": "already_running"})

    def _run():
        try:
            from scraper import run_scrape
            run_scrape()
        except Exception as e:
            app.logger.error(f"Scrape error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/api/approve/<fid>", methods=["POST"])
def api_approve(fid):
    import staging as st
    st.approve_finding(fid)
    return jsonify(st.load_staging())


@app.route("/api/reject/<fid>", methods=["POST"])
def api_reject(fid):
    import staging as st
    st.reject_finding(fid)
    return jsonify(st.load_staging())


@app.route("/api/approve-all", methods=["POST"])
def api_approve_all():
    import staging as st
    st.approve_all()
    return jsonify(st.load_staging())


@app.route("/api/reject-all", methods=["POST"])
def api_reject_all():
    import staging as st
    st.reject_all()
    return jsonify(st.load_staging())


@app.route("/api/edit/<fid>", methods=["POST"])
def api_edit(fid):
    import staging as st
    field_updates = request.get_json() or {}
    st.update_finding(fid, field_updates)
    return jsonify({"status": "updated"})


@app.route("/api/push", methods=["POST"])
def api_push():
    def _push():
        import staging as st
        data = st.load_staging()
        data["push_status"] = "running"
        data["push_result"] = None
        st.save_staging(data)
        try:
            from merger import merge_approved
            summary = merge_approved()
            app.logger.info(f"[push] merge summary: {summary}")
            from pusher import push_to_github
            result = push_to_github(summary)
            app.logger.info(f"[push] push result: {result}")
            data = st.load_staging()
            data["push_status"] = "success" if result["success"] else "error"
            data["push_result"] = result["message"]
            data["push_summary"] = summary
            st.save_staging(data)
        except Exception as e:
            app.logger.error(f"[push] fatal error: {e}", exc_info=True)
            data = st.load_staging()
            data["push_status"] = "error"
            data["push_result"] = str(e)
            st.save_staging(data)

    t = threading.Thread(target=_push, daemon=True)
    t.start()
    return jsonify({"status": "started"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
