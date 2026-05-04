"""Job search orchestrator — Phase 1 + Phase 2.

Hops:
  1. load_config       — read companies.json, criteria.md
  2. layer1_fetch      — pull JSON from Greenhouse/Lever/Ashby APIs
  3. normalize         — common posting shape
  4. prefilter         — Python regex (cheap exclusions)
  5. claude_judge      — single Anthropic API call (Layer 1 candidates → judged results)
  6. layer2_search     — single Anthropic API call with web_search tool (bespoke companies)
  7. merge             — combine Layer 1 + Layer 2 results into one judgment
  8. validate          — combined output against schema.json
  9. dedup             — SQLite seen-postings store
 10. format            — HTML email body
 11. deliver           — gog gmail send
 12. mark_seen         — record what we just delivered

Each hop emits a JSONL log line via logger.RunLogger. Failures emit `event=error` with traceback.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

# Local imports — script runs as `python3 scripts/search.py`
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import dedup  # noqa: E402
import deliver  # noqa: E402
from format import render  # noqa: E402
from logger import RunLogger  # noqa: E402

SKILL_DIR = SCRIPT_DIR.parent
COMPANIES_JSON = SKILL_DIR / "companies.json"
CRITERIA_MD = SKILL_DIR / "criteria.md"
SCHEMA_JSON = SKILL_DIR / "schema.json"

OP_KEY_SCRIPT = "/Users/bishop/.openclaw/scripts/op-anthropic-key.sh"

ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# ---- pre-filter rules ----------------------------------------------------------------------
# v2: stricter. v1 was too permissive (3079 -> 909). Now adds non-engineering domain
# exclusions (sales, marketing, HR, ops, customer success, design management, etc.) and
# requires a domain anchor for non-AI-lab senior roles.
EXCLUDE_TITLE_PATTERNS = [
    # Level / commitment
    r"\bintern(ship)?\b",
    r"\bjunior\b", r"\bjr\.\b",
    r"\bassociate\b(?!\s+director)",
    r"\bnew[\s-]?grad\b", r"\bco[\s-]?op\b",
    r"\b(software\s+)?engineer\s+(I|II|III)\b",
    r"\bcontract(or)?\b", r"\bconsultant\b", r"\btemp\b",
    # Hardware-specific exclusions from criteria.md
    r"\bfirmware\b", r"\bembedded\b", r"\bkernel\b", r"\bdriver\b",
    r"\bsilicon\b", r"\bASIC\b", r"\bRTL\b", r"\bFPGA\b",
    # Non-engineering business / ops
    r"\bsales\b", r"\baccount\s+(executive|manager|director)\b",
    r"\bmarketing\b", r"\bbrand\b",
    r"\bpeople\s+(manager|operations|partner|ops|business)\b",
    r"\bhuman\s+resources\b",
    r"\blegal\b", r"\bfinance\b", r"\baccounting\b", r"\bcontroller\b", r"\btreasury\b",
    r"\bcustomer\s+(success|support|experience)\b", r"\bsupport\s+engineer\b",
    r"\bpartnership(s)?\b", r"\bbusiness\s+development\b",
    r"\bcommunications?\s+(manager|director|lead|specialist)\b",
    r"\bsourcer\b", r"\brecruiter\b", r"\btalent\s+(acquisition|partner)\b",
    r"\boperations\s+(manager|director|lead|analyst)\b",
    r"\bproduct\s+manager\b", r"\bproduct\s+marketing\b", r"\bgo[\s-]?to[\s-]?market\b",
    r"\bcommunity\s+(manager|lead)\b", r"\bsocial\s+media\b",
    # Design / creative roles (non-tech)
    r"\bdesign\s+(manager|lead|director)\b",
    r"\b(UX|UI)\s+(designer|researcher|writer)\b",
    r"\bwriter\b", r"\beditor\b",
    r"\bproducer\b(?!.*\btechnical\b)",
    r"\banimator\b(?!.*\b(technical|tools|pipeline)\b)",
    r"\b(concept|environment|character|prop|3d|2d)\s+artist\b",  # production artists, not tech artists
    # Pure infra (criteria says "pure compute infra" out)
    r"\bdevops\b", r"\bsite\s+reliability\b", r"\bSRE\b",
    r"\bdata\s+(engineer|analyst|scientist)\b(?!.*\b(ML|AI|graphics|3d|simulation|perception)\b)",
    r"\bsecurity\s+engineer\b", r"\bdetection\s+engineer\b",
    # Game-studio non-tech
    r"\b(level|world|game|narrative|combat|encounter|systems)\s+designer\b",
    r"\besports\b",
    r"\bquality\s+assurance\b",
    r"\baudio\s+(designer|engineer|programmer)\b(?!.*\b(tools|pipeline)\b)",
    r"\bvoice\s+(designer|actor|director)\b",
    # Generic non-relevant manager/director (no domain anchor) — caught later by INCLUDE re-pass
]

# Keep if title matches ANY of these AFTER exclusions. Each pattern requires a domain
# anchor — bare "senior + role" no longer qualifies.
INCLUDE_TITLE_PATTERNS = [
    # Technical art / TD
    r"\btechnical\s+art(ist|s)?\b",
    r"\btechnical\s+director\b",
    # Engineering management — must touch a relevant domain
    r"\bengineering\s+manager\b",
    r"\bmanager,?\s+(software\s+)?engineering\b",
    r"\b(senior\s+)?manager\b.*\b(graphics|rendering|tools|pipeline|3d|simulation|perception|robotics|technical\s+art|ML|AI|machine\s+learning|research|inference|training)\b",
    r"\b(director|head)\s+(of\s+)?(engineering|tools|platform|graphics|art|research|ML|AI|robotics|simulation|technical\s+art|inference)\b",
    # Senior IC SWE with domain anchor — highest affinity: 3D graphics, animation, characters
    r"\b(staff|principal|distinguished|senior\s+staff)\s+(software\s+)?engineer\b",
    r"\b(senior|sr\.?)\s+(software\s+)?engineer\b.*\b(graphics|rendering|shading|shader|tools|pipeline|3d|simulation|perception|robotics|technical\s+art|animation|character|rigging|cloth|hair|fur|ML|AI|machine\s+learning|research|infrastructure|inference|training|fine-?tuning|content|asset|platform|3D)\b",
    r"\b(graphics|rendering|tools|pipeline|3d|simulation|perception|robotics|animation|character|rigging)\s+(engineer|programmer|developer)\b",
    r"\b(senior|sr\.?|staff|principal|lead)\s+(graphics|rendering|tools|pipeline|3d|simulation|perception|robotics|technical\s+art|animation|character|rigging)\b",
    # Animation / character / rigging TDs (technical directors are common in these domains)
    r"\b(animation|character|rigging|cloth|hair|fur|crowd)\s+(technical\s+director|TD)\b",
    # Research / applied
    r"\bresearch\s+(engineer|scientist)\b",
    r"\bapplied\s+scientist\b",
    # ML / AI
    r"\b(machine\s+learning|ML|AI)\s+(engineer|scientist|systems\s+engineer|research\s+engineer)\b",
    r"\b(senior|sr\.?|staff|principal)\s+(ML|AI|machine\s+learning)\s+engineer\b",
]

EXCLUDE_RE = re.compile("|".join(EXCLUDE_TITLE_PATTERNS), re.IGNORECASE)
INCLUDE_RE = re.compile("|".join(INCLUDE_TITLE_PATTERNS), re.IGNORECASE)


# ---- ATS fetchers --------------------------------------------------------------------------
def _http_get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-job-search/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_greenhouse(slug: str) -> list[dict]:
    data = _http_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    out = []
    for j in data.get("jobs", []) or []:
        loc = j.get("location") or {}
        out.append({
            "title": j.get("title", ""),
            "location": loc.get("name", "") if isinstance(loc, dict) else str(loc),
            "url": j.get("absolute_url", ""),
            "department": "",  # not in summary endpoint
            "_raw": {"id": j.get("id"), "updated_at": j.get("updated_at")},
        })
    return out


def fetch_lever(slug: str) -> list[dict]:
    data = _http_get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(data, list):
        return []
    out = []
    for j in data:
        cats = j.get("categories") or {}
        out.append({
            "title": j.get("text", ""),
            "location": cats.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "department": cats.get("team", ""),
            "_raw": {"id": j.get("id"), "createdAt": j.get("createdAt")},
        })
    return out


def fetch_ashby(slug: str) -> list[dict]:
    data = _http_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in data.get("jobs", []) or []:
        out.append({
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("jobUrl", ""),
            "department": j.get("department", ""),
            "_raw": {"id": j.get("id"), "publishedDate": j.get("publishedDate")},
        })
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


# ---- pre-filter ----------------------------------------------------------------------------
def prefilter(postings: list[dict]) -> tuple[list[dict], int]:
    kept = []
    for p in postings:
        title = p.get("title", "")
        if not title:
            continue
        if EXCLUDE_RE.search(title):
            continue
        if not INCLUDE_RE.search(title):
            continue
        kept.append(p)
    return kept, len(postings) - len(kept)


# ---- Claude judgment -----------------------------------------------------------------------
def get_anthropic_key() -> str:
    proc = subprocess.run([OP_KEY_SCRIPT], capture_output=True, text=True, check=True, timeout=15)
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def _safe(s):
    if not s:
        return ""
    return " ".join(s.split())


def _extract_json(text: str) -> tuple[dict, str]:
    """Find a JSON object in Claude's output. Returns (judgment, prose_preamble).

    Tries (in order): ```json fenced block, ``` fenced block, outermost {...}.
    Claude often narrates analysis before the JSON; we keep that as 'notes'.
    """
    # Fenced block — tolerant of preamble before it.
    m = re.search(r"```(?:json)?\s*\n(.+?)\n```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1)), text[:m.start()].strip()
    # Bare object — find matching braces. Use simple find-first-{ to last-}.
    i = text.find("{")
    j = text.rfind("}")
    if i >= 0 and j > i:
        return json.loads(text[i:j + 1]), text[:i].strip()
    raise ValueError("no JSON object found in output")


def claude_judge(criteria_md: str, candidates: list[dict], api_key: str) -> tuple[dict, dict, str]:
    """Single API call. Returns (judgment_dict, usage_dict, prose_notes).

    prose_notes is any analysis Claude produced before/around the JSON — surfaced in the
    email footer as 'Bishop's commentary' so Dave sees the reasoning over time.
    """
    schema_text = SCHEMA_JSON.read_text()
    # Compress candidate payload — only what's needed for judgment
    compact = []
    for p in candidates:
        compact.append({
            "company": p["company"],
            "tier": p["tier"],
            "title": _safe(p.get("title")),
            "location": _safe(p.get("location")),
            "department": _safe(p.get("department"))[:120],
            "url": _safe(p.get("url")),
        })
    user_payload = json.dumps(compact, ensure_ascii=False)

    system_prompt = (
        "You are filtering job postings for Dave Otte. Apply the criteria in CRITERIA exactly. "
        "Be inclusive on borderline matches per the calibration notes. "
        "Return ONE JSON object matching the SCHEMA. No prose, no code fences, no preamble.\n\n"
        f"=== CRITERIA ===\n{criteria_md}\n\n"
        f"=== SCHEMA ===\n{schema_text}\n"
    )
    user_prompt = (
        "Below are pre-filtered job postings, one per JSON object. "
        "Apply the criteria, dedup any obvious cross-company duplicates, "
        "and return the JSON object per schema. "
        "filtered_out_count = (postings shown) - (results returned).\n\n"
        f"=== POSTINGS ({len(compact)}) ===\n{user_payload}"
    )

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 16384,
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        api_resp = json.loads(resp.read())

    text = "".join(b.get("text", "") for b in api_resp.get("content", []) if b.get("type") == "text").strip()
    try:
        judgment, prose = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        # Dump the raw response for forensic recovery
        from logger import LOG_DIR
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        import datetime as _dt
        dump_path = LOG_DIR / f"raw-response-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        dump_path.write_text(json.dumps({
            "stop_reason": api_resp.get("stop_reason"),
            "raw_text": text[:8000],
            "raw_text_len": len(text),
            "full_api_response": api_resp,
        }, indent=2))
        raise RuntimeError(f"Claude output had no parseable JSON. Raw dumped to {dump_path}. "
                           f"stop_reason={api_resp.get('stop_reason')!r}, "
                           f"text_len={len(text)}, "
                           f"err={e}")

    usage = api_resp.get("usage", {}) or {}
    return judgment, usage, prose


# ---- Layer 2: Claude web_search ------------------------------------------------------------
LAYER2_DEFAULT_MAX_SEARCHES = 10
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"
WEB_SEARCH_COST_PER_USE = 0.01  # USD per Anthropic web_search call


def claude_layer2_search(
    criteria_md: str,
    layer2_companies: list[dict],
    api_key: str,
    *,
    max_searches: int = LAYER2_DEFAULT_MAX_SEARCHES,
) -> tuple[dict, dict, str, int]:
    """Single API call with web_search tool. Returns (judgment_dict, usage, prose_notes, search_count).

    Claude is given the layer2 list with search_hints and asked to find current senior-level
    postings on each company's careers page that match the criteria. Output uses the same
    schema as Phase 1 so results can be merged.
    """
    schema_text = SCHEMA_JSON.read_text()
    compact = [
        {
            "company": c["company"],
            "tier": c["tier"],
            "search_hint": c.get("search_hint", ""),
        }
        for c in layer2_companies
    ]
    user_payload = json.dumps(compact, ensure_ascii=False, indent=2)

    system_prompt = (
        "You are searching for current job postings on the careers pages of specific companies. "
        "Apply the criteria in CRITERIA exactly. Be inclusive on borderline matches per the calibration notes.\n\n"
        f"You have a budget of up to {max_searches} web_search calls total across all companies. "
        "Allocate the budget by tier — T1/T2 first, then T3, then T4. For each company, search using "
        "the search_hint as a guide; one well-targeted query per company is usually enough. "
        "Skip a company (note in skipped_companies) if you cannot reach a usable careers page or "
        "if your budget runs out before you reach it.\n\n"
        "Return ONE JSON object matching the SCHEMA. The url for each posting MUST be a direct "
        "apply / posting link, not a generic careers homepage. If you only find a careers page with "
        "no posting-level URL, do NOT include that role.\n\n"
        f"=== CRITERIA ===\n{criteria_md}\n\n"
        f"=== SCHEMA ===\n{schema_text}\n"
    )
    user_prompt = (
        f"Search these {len(compact)} companies for current senior-level postings matching the criteria. "
        "Use the web_search tool. Return the JSON object per schema. "
        "filtered_out_count = your rough estimate of postings you considered and rejected.\n\n"
        f"=== COMPANIES ===\n{user_payload}"
    )

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 16384,
        "tools": [{
            "type": WEB_SEARCH_TOOL_TYPE,
            "name": "web_search",
            "max_uses": max_searches,
        }],
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        api_resp = json.loads(resp.read())

    # Concatenate all text blocks. server_tool_use / web_search_tool_result blocks are not text.
    text = "".join(
        b.get("text", "") for b in api_resp.get("content", []) if b.get("type") == "text"
    ).strip()

    # Count actual web_search invocations for cost accounting (Anthropic returns
    # `server_tool_use` blocks for tools the platform ran on Claude's behalf).
    search_count = sum(
        1 for b in api_resp.get("content", [])
        if b.get("type") == "server_tool_use" and b.get("name") == "web_search"
    )

    try:
        judgment, prose = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        from logger import LOG_DIR
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        import datetime as _dt
        dump_path = LOG_DIR / f"raw-response-layer2-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        dump_path.write_text(json.dumps({
            "stop_reason": api_resp.get("stop_reason"),
            "raw_text": text[:8000],
            "raw_text_len": len(text),
            "search_count": search_count,
            "full_api_response": api_resp,
        }, indent=2))
        raise RuntimeError(
            f"Layer 2 Claude output had no parseable JSON. Raw dumped to {dump_path}. "
            f"stop_reason={api_resp.get('stop_reason')!r}, "
            f"text_len={len(text)}, search_count={search_count}, err={e}"
        )

    usage = api_resp.get("usage", {}) or {}
    return judgment, usage, prose, search_count


def merge_judgments(j1: dict, j2: dict) -> dict:
    """Combine two judgment dicts (same schema). Concats results + skipped, sums filtered_out_count."""
    return {
        "results": (j1.get("results", []) or []) + (j2.get("results", []) or []),
        "skipped_companies": (j1.get("skipped_companies", []) or [])
                             + (j2.get("skipped_companies", []) or []),
        "filtered_out_count": int(j1.get("filtered_out_count", 0) or 0)
                              + int(j2.get("filtered_out_count", 0) or 0),
    }


def validate_judgment(j: dict, schema: dict) -> list[str]:
    """Lightweight validation — required top-level keys + per-result required fields. Returns errors list (empty = valid)."""
    errs = []
    for key in schema.get("required", []):
        if key not in j:
            errs.append(f"missing top-level key: {key}")
    if "results" in j:
        if not isinstance(j["results"], list):
            errs.append("results: not a list")
        else:
            req = schema["properties"]["results"]["items"]["required"]
            for i, r in enumerate(j["results"]):
                for k in req:
                    if k not in r:
                        errs.append(f"results[{i}]: missing {k}")
                        break
                if "tier" in r and r["tier"] not in {"T1", "T2", "T3", "T4"}:
                    errs.append(f"results[{i}]: bad tier {r['tier']}")
    if "skipped_companies" in j and not isinstance(j["skipped_companies"], list):
        errs.append("skipped_companies: not a list")
    if "filtered_out_count" in j and not isinstance(j["filtered_out_count"], int):
        errs.append("filtered_out_count: not an int")
    return errs


# ---- main pipeline -------------------------------------------------------------------------
def run(*, dry_send: bool = False, skip_layer2: bool = False,
        layer2_max_searches: int = LAYER2_DEFAULT_MAX_SEARCHES) -> int:
    log = RunLogger()
    log.emit("triggered", phase="1+2" if not skip_layer2 else "1",
             dry_send=dry_send, skip_layer2=skip_layer2,
             layer2_max_searches=layer2_max_searches)

    # Hop 1: config
    try:
        companies = json.loads(COMPANIES_JSON.read_text())
        criteria = CRITERIA_MD.read_text()
        schema = json.loads(SCHEMA_JSON.read_text())
        layer1 = companies.get("layer1", [])
        log.emit("config_loaded", layer1_count=len(layer1), layer2_count=len(companies.get("layer2", [])))
    except Exception as e:
        log.emit("error", hop="config", message=str(e), traceback=traceback.format_exc())
        log.close()
        return 2

    # Hop 2: layer 1 fetch
    raw: list[dict] = []
    fetch_failures: list[dict] = []
    for c in layer1:
        ats, slug = c["ats"], c["slug"]
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            fetch_failures.append({"company": c["company"], "reason": f"no fetcher for ats={ats}"})
            continue
        try:
            postings = fetcher(slug)
            for p in postings:
                p["company"] = c["company"]
                p["tier"] = c["tier"]
                p["ats"] = ats
            raw.extend(postings)
            log.emit("layer1_fetch", company=c["company"], ats=ats, slug=slug, n=len(postings))
        except Exception as e:
            fetch_failures.append({"company": c["company"], "reason": f"{type(e).__name__}: {e}"})
            log.emit("layer1_fetch_error", company=c["company"], message=str(e))
        time.sleep(0.05)
    log.emit("layer1_complete", raw_count=len(raw), fetch_failures=len(fetch_failures))

    # Hop 3+4: normalize (already done) + pre-filter
    candidates, dropped = prefilter(raw)
    log.emit("prefiltered", kept=len(candidates), dropped=dropped)
    if not candidates:
        log.emit("noop", reason="no candidates after pre-filter")
        log.close()
        return 0

    # Hop 5: Claude judgment
    try:
        api_key = get_anthropic_key()
    except Exception as e:
        log.emit("error", hop="api_key", message=str(e), traceback=traceback.format_exc())
        log.close()
        return 3
    log.emit("claude_invoked", model=ANTHROPIC_MODEL, candidates=len(candidates))
    try:
        judgment, usage, prose_notes = claude_judge(criteria, candidates, api_key)
    except urllib.error.HTTPError as e:
        log.emit("error", hop="claude_call", http=e.code, body=e.read().decode()[:500])
        log.close()
        return 4
    except Exception as e:
        log.emit("error", hop="claude_call", message=str(e), traceback=traceback.format_exc())
        log.close()
        return 4
    # Merge in Layer 1 fetch failures as skipped_companies
    judgment.setdefault("skipped_companies", []).extend(fetch_failures)
    in_tok = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
    cache_in = usage.get("cache_read_input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    cost = (in_tok * 3 + cache_in * 0.3 + out_tok * 15) / 1_000_000
    log.emit("claude_responded", input_tokens=in_tok, cache_read_tokens=cache_in,
             output_tokens=out_tok, cost_usd=round(cost, 4),
             prose_notes_len=len(prose_notes))

    # Hop 6: Layer 2 (web_search) — optional, controlled by skip_layer2
    layer2 = companies.get("layer2", []) or []
    layer2_prose = ""
    layer2_cost = 0.0
    layer2_search_count = 0
    if skip_layer2 or not layer2:
        log.emit("layer2_skipped",
                 reason="--skip-layer2" if skip_layer2 else "no layer2 in companies.json",
                 layer2_count=len(layer2))
    else:
        log.emit("layer2_invoked", model=ANTHROPIC_MODEL, companies=len(layer2),
                 max_searches=layer2_max_searches)
        try:
            j2, usage2, layer2_prose, layer2_search_count = claude_layer2_search(
                criteria, layer2, api_key, max_searches=layer2_max_searches,
            )
        except urllib.error.HTTPError as e:
            log.emit("error", hop="layer2_call", http=e.code, body=e.read().decode()[:500])
            # Layer 2 is enrichment — don't fail the whole run. Note in skipped_companies and continue.
            judgment["skipped_companies"].append({
                "company": "(Layer 2 batch)",
                "reason": f"web_search call failed: HTTP {e.code}",
            })
        except Exception as e:
            log.emit("error", hop="layer2_call", message=str(e), traceback=traceback.format_exc())
            judgment["skipped_companies"].append({
                "company": "(Layer 2 batch)",
                "reason": f"web_search call failed: {type(e).__name__}: {e}"[:200],
            })
        else:
            in2 = usage2.get("input_tokens", 0) + usage2.get("cache_creation_input_tokens", 0)
            cache2 = usage2.get("cache_read_input_tokens", 0)
            out2 = usage2.get("output_tokens", 0)
            layer2_cost = (
                (in2 * 3 + cache2 * 0.3 + out2 * 15) / 1_000_000
                + layer2_search_count * WEB_SEARCH_COST_PER_USE
            )
            log.emit("layer2_responded",
                     input_tokens=in2, cache_read_tokens=cache2, output_tokens=out2,
                     web_searches=layer2_search_count,
                     cost_usd=round(layer2_cost, 4),
                     l2_results=len(j2.get("results", [])),
                     l2_skipped=len(j2.get("skipped_companies", [])),
                     prose_notes_len=len(layer2_prose))
            judgment = merge_judgments(judgment, j2)
            in_tok += in2
            out_tok += out2
            cost += layer2_cost

    # Hop 7: validate (combined)
    errs = validate_judgment(judgment, schema)
    if errs:
        log.emit("error", hop="validate", errors=errs[:10])
        log.close()
        return 5
    log.emit("validated", results=len(judgment.get("results", [])),
             skipped=len(judgment.get("skipped_companies", [])),
             filtered_out_count=judgment.get("filtered_out_count", 0))

    # Hop 7: dedup (filter to new only)
    new, already = dedup.filter_new(judgment["results"])
    log.emit("deduped", new=len(new), already_seen=len(already))
    judgment["results"] = new  # email shows only NEW postings

    # Save run artifacts (judgment json + prose notes) to logs/ for forensic preview
    from logger import LOG_DIR
    judgment_path = LOG_DIR / f"judgment-{log.run_id}.json"
    judgment_path.write_text(json.dumps(judgment, indent=2, ensure_ascii=False))
    notes_path = None
    if prose_notes or layer2_prose:
        notes_path = LOG_DIR / f"notes-{log.run_id}.md"
        sections = []
        if prose_notes:
            sections.append("# Layer 1 (deterministic ATS pull)\n\n" + prose_notes)
        if layer2_prose:
            sections.append("# Layer 2 (web_search)\n\n" + layer2_prose)
        notes_path.write_text("\n\n---\n\n".join(sections))
    log.emit("artifacts_saved", judgment=str(judgment_path.name),
             notes=str(notes_path.name) if notes_path else None)

    # Hop 8: format
    run_meta = {
        "run_id": log.run_id,
        "layer1_raw": len(raw),
        "after_prefilter": len(candidates),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": cost,
        "layer2_skipped": skip_layer2 or not layer2,
        "layer2_searches": layer2_search_count,
        "layer2_cost_usd": layer2_cost,
    }
    subject, html = render(judgment, run_meta)
    log.emit("email_formatted", subject=subject, body_bytes=len(html))

    # Hop 9: deliver
    if dry_send:
        log.emit("deliver_skipped", reason="dry_send=True")
    else:
        ok, detail = deliver.send_html(subject=subject, html_body=html)
        log.emit("gmail_sent" if ok else "gmail_send_error", ok=ok, detail=detail[:300])
        if not ok:
            log.close()
            return 6

    # Hop 10: mark_seen ONLY on real send. Dry runs are rehearsals — don't commit state.
    if dry_send:
        log.emit("marked_seen_skipped", reason="dry_send=True", would_insert=len(new))
    else:
        inserted = dedup.mark_seen(new)
        log.emit("marked_seen", inserted=inserted, store_stats=dedup.stats())

    log.emit("done", ok=True, results_emailed=len(new))
    log.close()
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-send", action="store_true",
                    help="Run pipeline but skip the gog gmail send (for testing).")
    ap.add_argument("--skip-layer2", action="store_true",
                    help="Skip the Layer 2 web_search call (Phase 1 only). Use for cheap smoke tests.")
    ap.add_argument("--layer2-max-searches", type=int, default=LAYER2_DEFAULT_MAX_SEARCHES,
                    help=f"Max web_search calls Claude may make in Layer 2 "
                         f"(default {LAYER2_DEFAULT_MAX_SEARCHES}, ~$0.01 per use).")
    args = ap.parse_args()
    sys.exit(run(
        dry_send=args.dry_send,
        skip_layer2=args.skip_layer2,
        layer2_max_searches=args.layer2_max_searches,
    ))
