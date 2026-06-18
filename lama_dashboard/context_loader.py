import os

CONTEXT_FILES = [
    "SNC_2025_Annual_Report_FULL.md",
    "Israeli_Cyber_Company_Tracker.md",
    "Israeli_Cyber_Investor_Landscape.md",
    "Israeli_VC_Cyber_Ecosystem_Report.md",
    "Unit_8200_Alumni_Association.md",
]

_context = {}


def load_context():
    global _context
    base = os.path.join(os.path.dirname(__file__), "data")
    for fname in CONTEXT_FILES:
        path = os.path.join(base, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                _context[fname] = f.read()
        else:
            _context[fname] = ""
    print(f"[context_loader] Loaded {len([v for v in _context.values() if v])} context files")
    return _context


def get_context():
    if not _context:
        load_context()
    return _context


def get_combined_context(max_chars=40000):
    ctx = get_context()
    combined = []
    total = 0
    for fname, content in ctx.items():
        if total + len(content) > max_chars:
            combined.append(f"\n\n=== {fname} (truncated) ===\n" + content[:max_chars - total])
            break
        combined.append(f"\n\n=== {fname} ===\n{content}")
        total += len(content)
    return "".join(combined)
