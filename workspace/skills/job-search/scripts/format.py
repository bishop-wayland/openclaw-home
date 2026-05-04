"""Format Claude's judgment output into an HTML email body."""
from __future__ import annotations

import datetime as _dt
import html as _html


_TIER_LABEL = {
    "T1": "Tier 1 — Games (direct domain)",
    "T2": "Tier 2 — Big Tech (graphics, 3D, AI)",
    "T3": "Tier 3 — AI Labs, Robotics, Frontier Research",
    "T4": "Tier 4 — Mid-Size Adjacent",
}


def render(judgment: dict, run_meta: dict) -> tuple[str, str]:
    """Return (subject, html_body)."""
    results = judgment.get("results", [])
    skipped = judgment.get("skipped_companies", [])
    filtered_out_count = judgment.get("filtered_out_count", 0)

    by_tier: dict[str, list[dict]] = {}
    for r in results:
        by_tier.setdefault(r["tier"], []).append(r)

    n = len(results)
    today = _dt.datetime.now().strftime("%a %b %d, %Y")
    subject = f"Job digest — {today} — {n} new {'posting' if n == 1 else 'postings'}"

    parts: list[str] = []
    parts.append(
        f"<p>Weekly digest for <strong>{today}</strong>. "
        f"<strong>{n}</strong> new posting{'s' if n != 1 else ''} after dedup. "
        f"{filtered_out_count} considered and rejected this week.</p>"
    )

    if not results:
        parts.append("<p><em>No new matches this week.</em></p>")
    else:
        for tier in ("T1", "T2", "T3", "T4"):
            items = by_tier.get(tier, [])
            if not items:
                continue
            parts.append(f"<h3 style='margin-top:24px;'>{_html.escape(_TIER_LABEL[tier])}</h3>")
            parts.append("<ul style='padding-left: 18px;'>")
            for it in items:
                title = _html.escape(it["title"])
                company = _html.escape(it["company"])
                location = _html.escape(it["location"])
                url = _html.escape(it["url"], quote=True)
                blurb = _html.escape(it["relevance_blurb"])
                parts.append(
                    f"<li style='margin-bottom: 10px;'>"
                    f"<strong>{company}</strong> — {title}<br>"
                    f"<em>{location}</em><br>"
                    f"<a href='{url}'>{url}</a><br>"
                    f"<span style='color: #555;'>{blurb}</span>"
                    f"</li>"
                )
            parts.append("</ul>")

    if skipped:
        parts.append("<h3 style='margin-top:24px;'>Companies not successfully scanned</h3>")
        parts.append("<ul style='padding-left: 18px;'>")
        for s in skipped:
            parts.append(
                f"<li><strong>{_html.escape(s['company'])}</strong> — {_html.escape(s['reason'])}</li>"
            )
        parts.append("</ul>")

    # Footer with run metadata
    parts.append("<hr style='margin-top: 32px;'>")
    parts.append("<p style='color: #888; font-size: 11px;'>")
    parts.append(f"Run id: {_html.escape(run_meta.get('run_id', '?'))}<br>")
    parts.append(f"Layer 1 raw: {run_meta.get('layer1_raw', 0)} → "
                 f"after pre-filter: {run_meta.get('after_prefilter', 0)} → "
                 f"after Claude: {len(results) + filtered_out_count} → "
                 f"after dedup: {n}<br>")
    parts.append(f"Cost: ${run_meta.get('cost_usd', 0.0):.3f} "
                 f"(input {run_meta.get('input_tokens', 0)} tok, "
                 f"output {run_meta.get('output_tokens', 0)} tok)<br>")
    if run_meta.get("layer2_skipped"):
        parts.append("Layer 2 (web_search): skipped this run<br>")
    elif run_meta.get("layer2_searches", 0) > 0 or run_meta.get("layer2_cost_usd", 0.0) > 0:
        parts.append(
            f"Layer 2 (web_search): {run_meta.get('layer2_searches', 0)} searches, "
            f"${run_meta.get('layer2_cost_usd', 0.0):.3f}<br>"
        )
    parts.append(f"Forensic log: ~/.openclaw/workspace/skills/job-search/logs/run-"
                 f"{_html.escape(run_meta.get('run_id', '?'))}.jsonl")
    parts.append("</p>")

    body = (
        "<html><body style='font-family: -apple-system, system-ui, sans-serif; "
        "max-width: 720px; line-height: 1.45;'>"
        + "".join(parts)
        + "</body></html>"
    )
    return subject, body
