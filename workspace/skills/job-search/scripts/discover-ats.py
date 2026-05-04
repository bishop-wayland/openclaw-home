"""ATS discovery: probe Greenhouse / Lever / Ashby public APIs for each company.

For each company, try a few slug variants. First hit with >0 jobs wins.
Output: tier | company | ats | slug | job_count
Companies with no hits go into LAYER_2 (will need web_search).
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

COMPANIES = [
    ("T1", "Pixar"),
    ("T1", "Walt Disney Animation Studios"),
    ("T1", "Industrial Light & Magic"),
    ("T1", "DreamWorks Animation"),
    ("T1", "Netflix Animation"),
    ("T1", "Sony Pictures Imageworks"),
    ("T1", "Epic Games"),
    ("T1", "Unity"),
    ("T1", "Riot Games"),
    ("T1", "Bungie"),
    ("T1", "Naughty Dog"),
    ("T1", "Insomniac Games"),
    ("T1", "Respawn Entertainment"),
    ("T1", "Blizzard Entertainment"),
    ("T1", "Weta FX"),
    ("T1", "DNEG"),
    ("T1", "Framestore"),
    ("T1", "MPC"),
    ("T2", "Apple"),
    ("T2", "Google"),
    ("T2", "NVIDIA"),
    ("T2", "Adobe"),
    ("T2", "Autodesk"),
    ("T2", "Microsoft"),
    ("T2", "Amazon"),
    ("T2", "Roblox"),
    ("T2", "Netflix"),
    ("T2", "Snap"),
    ("T3", "Anthropic"),
    ("T3", "OpenAI"),
    ("T3", "Scale AI"),
    ("T3", "Runway"),
    ("T3", "Luma AI"),
    ("T3", "Midjourney"),
    ("T3", "World Labs"),
    ("T3", "Physical Intelligence"),
    ("T3", "Skydio"),
    ("T3", "Figure"),
    ("T3", "1X"),
    ("T3", "Boston Dynamics"),
    ("T3", "Waymo"),
    ("T3", "Wayve"),
    ("T4", "Niantic"),
    ("T4", "Discord"),
    ("T4", "Figma"),
    ("T4", "Linear"),
    ("T4", "Notion"),
    ("T4", "Anduril"),
]

ENDPOINTS = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"),
]


def slug_variants(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()
    parts = base.split()
    out = []
    if parts:
        out.append("".join(parts))
        out.append("-".join(parts))
        if len(parts) > 1:
            out.append(parts[0])
    # de-dup, preserve order
    seen = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def fetch(url: str, timeout: int = 8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "openclaw-job-search-discovery/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, None


def parse_count(ats: str, body: bytes):
    try:
        data = json.loads(body)
    except Exception:
        return None
    if ats == "greenhouse":
        return len(data.get("jobs", [])) if isinstance(data.get("jobs"), list) else None
    if ats == "lever":
        return len(data) if isinstance(data, list) else None
    if ats == "ashby":
        return len(data.get("jobs", [])) if isinstance(data.get("jobs"), list) else None
    return None


def discover(name: str):
    for slug in slug_variants(name):
        for ats, tmpl in ENDPOINTS:
            url = tmpl.format(slug=slug)
            status, body = fetch(url)
            if status == 200 and body:
                count = parse_count(ats, body)
                if count and count > 0:
                    return (ats, slug, count)
            time.sleep(0.05)
    return None


print(f"{'Tier':<5} {'Company':<32} {'ATS':<11} {'Slug':<28} {'Jobs':>6}")
print("-" * 84)

layer1 = []
layer2 = []
for tier, name in COMPANIES:
    result = discover(name)
    if result:
        ats, slug, count = result
        layer1.append((tier, name, ats, slug, count))
        print(f"{tier:<5} {name:<32} {ats:<11} {slug:<28} {count:>6}")
    else:
        layer2.append((tier, name))
        print(f"{tier:<5} {name:<32} {'(none)':<11} {'-':<28} {'-':>6}")

print()
print(f"Layer 1 (deterministic ATS): {len(layer1)} / {len(COMPANIES)}")
print(f"Layer 2 (web_search needed): {len(layer2)} / {len(COMPANIES)}")
print()
print("Layer 1 totals by ATS:")
ats_count = {}
for _, _, ats, _, _ in layer1:
    ats_count[ats] = ats_count.get(ats, 0) + 1
for k, v in sorted(ats_count.items()):
    print(f"  {k}: {v}")
print()
total_jobs = sum(j for _, _, _, _, j in layer1)
print(f"Total Layer 1 raw postings (pre-filter): {total_jobs}")
