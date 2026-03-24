"""
Smoke test — hits every API endpoint and writes results to smoke_results.json.
Run from repo root:  python scripts/smoke_test.py
Requires: pip install requests  (or it's already in requirements-dev.txt)
Server must be running: docker compose up web
"""
import io
import json
import sys
import time
from datetime import datetime
import requests

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
OUT  = "smoke_results.json"

results = {}


def hit(label, method, path, **kwargs):
    url = BASE + path
    resp = getattr(requests, method)(url, **kwargs)
    entry = {
        "url":        url,
        "method":     method.upper(),
        "status":     resp.status_code,
        "body":       _trim(resp),
    }
    results[label] = entry
    status_icon = "✅" if resp.status_code < 400 else "❌"
    print(f"  {status_icon}  [{resp.status_code}]  {method.upper()} {path}")
    return resp


def _trim(resp):
    """Return parsed JSON, truncating large arrays to 3 items for readability."""
    try:
        data = resp.json()
    except Exception:
        return resp.text[:500]

    if isinstance(data, dict):
        trimmed = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 3:
                trimmed[k] = v[:3] + [f"... ({len(v)} total)"]
            else:
                trimmed[k] = v
        return trimmed
    if isinstance(data, list) and len(data) > 3:
        return data[:3] + [f"... ({len(data)} total)"]
    return data


# ── 1. Health ──────────────────────────────────────────────────────────────────
print("\n── Health ──")
hit("health", "get", "/health/")


# ── 2. Job list — basic ────────────────────────────────────────────────────────
print("\n── Job list ──")
hit("list_default",         "get", "/jobs/")
hit("list_page_size_20",    "get", "/jobs/?page_size=20")
hit("list_page_size_5",     "get", "/jobs/?page_size=5")


# ── 3. Ordering ────────────────────────────────────────────────────────────────
print("\n── Ordering ──")
hit("order_fetched_at_desc",   "get", "/jobs/?ordering=-fetched_at&page_size=3")
hit("order_posted_at_desc",    "get", "/jobs/?ordering=-posted_at&page_size=3")
hit("order_last_seen_desc",    "get", "/jobs/?ordering=-last_seen_at&page_size=3")
hit("order_title_asc",         "get", "/jobs/?ordering=title&page_size=3")
hit("order_company_asc",       "get", "/jobs/?ordering=company&page_size=3")


# ── 4. Location filters ────────────────────────────────────────────────────────
print("\n── Location filters ──")
# Fetch first 20 to find real city/state/region values
r20 = requests.get(f"{BASE}/jobs/?page_size=20").json()
jobs_20 = r20.get("results", [])

# Gather unique non-null values from the 20 jobs
cities   = list({j["city"]   for j in jobs_20 if j.get("city")})[:2]
states   = list({j["state"]  for j in jobs_20 if j.get("state")})[:2]
regions  = list({j["region"] for j in jobs_20 if j.get("region")})[:2]

for city in cities:
    hit(f"filter_city_{city[:10]}", "get", f"/jobs/?city={city}&page_size=5")

for state in states:
    hit(f"filter_state_{state[:10]}", "get", f"/jobs/?state={state}&page_size=5")

for region in regions:
    hit(f"filter_region_{region[:10]}", "get", f"/jobs/?region={region}&page_size=5")

# Combined
if cities and regions:
    hit("filter_city_region_combined", "get",
        f"/jobs/?city={cities[0]}&region={regions[0]}&page_size=5")


# ── 5. Free-text search ────────────────────────────────────────────────────────
print("\n── Search ──")
hit("search_python",             "get", "/jobs/?search=python&page_size=5")
hit("search_backend",            "get", "/jobs/?search=backend&page_size=5")
hit("search_python_tlv",         "get", "/jobs/?search=python&city=Tel Aviv&page_size=5")
hit("search_no_results",         "get", "/jobs/?search=zzznomatchxxx&page_size=5")


# ── 6. Job detail ──────────────────────────────────────────────────────────────
print("\n── Job detail ──")
job_ids = [j["id"] for j in jobs_20[:3]]
for jid in job_ids:
    hit(f"detail_job_{jid}", "get", f"/jobs/{jid}/")

hit("detail_nonexistent", "get", "/jobs/999999/")


# ── 7. Summary endpoint — three cache layers ──────────────────────────────────
print("\n── Summary (cache layers) ──")
# First call — may be Layer 3 (AI) or Layer 2 (Postgres), warms Redis
hit(f"summary_job_{job_ids[0]}_first",  "get", f"/jobs/{job_ids[0]}/summary/")
# Second call — should be Layer 1 (Redis hit)
hit(f"summary_job_{job_ids[0]}_cached", "get", f"/jobs/{job_ids[0]}/summary/")

if len(job_ids) > 1:
    hit(f"summary_job_{job_ids[1]}", "get", f"/jobs/{job_ids[1]}/summary/")
if len(job_ids) > 2:
    hit(f"summary_job_{job_ids[2]}", "get", f"/jobs/{job_ids[2]}/summary/")

hit("summary_nonexistent", "get", "/jobs/999999/summary/")


# ── 8. Bulk summarize ─────────────────────────────────────────────────────────
print("\n── Bulk summarize ──")
r_bulk = hit("bulk_summarize_basic",  "post", "/jobs/summarize-bulk/?limit=5")
r_bulk_loc = hit("bulk_summarize_with_filters",
                 "post", "/jobs/summarize-bulk/?limit=5&locations=Israel,Tel Aviv&search=python,django")

# Poll task status
for label, resp in [("bulk_summarize_basic", r_bulk),
                    ("bulk_summarize_with_filters", r_bulk_loc)]:
    if resp.status_code == 202:
        task_id = resp.json().get("task_id")
        if task_id:
            print(f"  ⏳  Polling task {task_id[:8]}…")
            for attempt in range(6):
                time.sleep(2)
                poll = requests.get(f"{BASE}/jobs/tasks/{task_id}/")
                results[f"{label}_poll_{attempt+1}"] = {
                    "url": f"{BASE}/jobs/tasks/{task_id}/",
                    "method": "GET",
                    "status": poll.status_code,
                    "body": poll.json(),
                }
                status = poll.json().get("status")
                print(f"     attempt {attempt+1}: {status}")
                if status in ("done", "failed"):
                    break


# ── 9. Fetch endpoint ─────────────────────────────────────────────────────────
print("\n── Fetch (trigger RapidAPI pull) ──")
hit("fetch_defaults",       "post", "/jobs/fetch/")
hit("fetch_custom_query",   "post", "/jobs/fetch/?query=Django+Developer&location=Israel")


# ── 10. Skills trending ───────────────────────────────────────────────────────
print("\n── Skills trending ──")
hit("trending_default",   "get", "/skills/trending/")
hit("trending_limit_5",   "get", "/skills/trending/?limit=5")
hit("trending_limit_10",  "get", "/skills/trending/?limit=10")


# ── Write output ──────────────────────────────────────────────────────────────
output = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "base_url":     BASE,
    "total_jobs_in_db": r20.get("count"),
    "sample_size":  len(jobs_20),
    "endpoints_tested": len(results),
    "results": results,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

# Summary table
print(f"\n{'─'*60}")
print(f"  Results written to: {OUT}")
print(f"  Endpoints tested:   {len(results)}")
passed = sum(1 for v in results.values() if isinstance(v.get('status'), int) and v['status'] < 400)
failed = len(results) - passed
print(f"  ✅ Passed: {passed}   ❌ Failed: {failed}")
print(f"{'─'*60}\n")
