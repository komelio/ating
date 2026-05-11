#!/usr/bin/env python3
"""
V3.1 Dashboard — 数据刷新入口。
调用 scraper.py（东方财富API → SQLite），然后 db.py（SQLite → JSON）。
gen_data.py 仅保留作为向后兼容的入口，实际逻辑在 v3-dashboard/ 下。
"""
import subprocess, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
V3 = os.path.join(ROOT, "v3-dashboard")

def run(script, cwd=V3):
    """Run a Python script and exit on failure."""
    path = os.path.join(cwd, script)
    result = subprocess.run(
        [sys.executable, path],
        cwd=cwd, capture_output=True, text=True, timeout=120
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == "__main__":
    print("=" * 50)
    print("  V3.1 Dashboard — Data Refresh")
    print("=" * 50)

    # Step 1: Scrape → SQLite (增量写入)
    print("\n📥 Step 1/2: Scraping → SQLite")
    run("scraper.py")

    # Step 2: SQLite → JSON (导出给前端)
    print("\n📤 Step 2/2: SQLite → JSON")
    # Import and call db.py's export function
    sys.path.insert(0, V3)
    from db import init_db, export_all_json
    init_db()
    export_all_json()

    print("\n✅ All done. JSON files ready in v3-dashboard/data/")