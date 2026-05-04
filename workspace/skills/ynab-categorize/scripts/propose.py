#!/usr/bin/env python3
"""
YNAB Categorizer — Main orchestrator.

Pulls uncategorized transactions from YNAB, classifies them via lookup + web search + LLM,
and delivers email + iMessage digests with new-merchant approval prompts.

Flags:
  --dry-send    Skip email/iMessage delivery
  --no-apply    Skip YNAB PATCH (for testing)
  --limit-txns  Limit to N transactions (for testing)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from logger import RunLogger
import merchant_lookup
import classify
import deliver


def load_config() -> dict:
    """Load config.json."""
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


def get_ynab_token() -> str:
    """Fetch YNAB token from 1Password."""
    proc = subprocess.run(
        ["/Users/bishop/.openclaw/scripts/op-ynab-key.sh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def get_anthropic_key() -> str:
    """Fetch Anthropic API key from 1Password."""
    proc = subprocess.run(
        ["/Users/bishop/.openclaw/scripts/op-anthropic-key.sh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    envelope = json.loads(proc.stdout)
    return envelope["values"]["value"]


def ynab_get(endpoint: str, token: str, timeout: int = 30) -> dict | None:
    """Make a GET request to YNAB API."""
    url = f"https://api.ynab.com/v1{endpoint}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {token}", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        return None
    except Exception:
        return None


def ynab_patch(endpoint: str, data: dict, token: str, timeout: int = 30) -> tuple[bool, dict]:
    """Make a PATCH request to YNAB API."""
    url = f"https://api.ynab.com/v1{endpoint}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "-X", "PATCH",
             "-H", f"Authorization: Bearer {token}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(data),
             url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            result = json.loads(proc.stdout)
            return True, result
        return False, {"error": proc.stderr or "curl failed"}
    except Exception as e:
        return False, {"error": str(e)}


def _extract_category_id(categories: list, category_name: str) -> str | None:
    """Find category ID by name."""
    for cat in categories:
        if cat.get("name") == category_name:
            return cat.get("id")
    return None


def _compose_email_digest(config: dict, auto_apply: list, pending: list, manual: list, run_id: str) -> str:
    """Compose HTML email digest."""
    week_of = datetime.now().strftime("%Y-%m-%d")
    
    auto_rows = ""
    for txn_id, txn, result in auto_apply:
        auto_rows += f"""
    <tr>
        <td>{txn.get('date')}</td>
        <td>{txn.get('payee_name')}</td>
        <td>${txn.get('amount', 0)/1000:.2f}</td>
        <td>{result['category']}</td>
    </tr>
"""
    
    pending_rows = ""
    for txn_id, txn, result in pending:
        web_snippet = result.get('evidence', {}).get('web_snippet', 'N/A') if result.get('evidence') else 'N/A'
        if isinstance(web_snippet, str) and len(web_snippet) > 100:
            web_snippet = web_snippet[:100]
        elif not isinstance(web_snippet, str):
            web_snippet = 'N/A'
        pending_rows += f"""
    <tr>
        <td>{txn.get('payee_name')}</td>
        <td>{result['category']} (confidence: {result['confidence']:.0%})</td>
        <td>{web_snippet}</td>
        <td>${txn.get('amount', 0)/1000:.2f}</td>
    </tr>
"""
    
    manual_rows = ""
    for txn_id, txn, result in manual:
        manual_rows += f"""
    <tr>
        <td>{txn.get('date')}</td>
        <td>{txn.get('payee_name')}</td>
        <td>${txn.get('amount', 0)/1000:.2f}</td>
        <td>Manual review needed</td>
    </tr>
"""
    
    html = f"""<html><body style="font-family: sans-serif;">
<h2>YNAB Categorizer — {week_of}</h2>
<p><strong>Summary:</strong></p>
<ul>
    <li>Auto-categorized: {len(auto_apply)}</li>
    <li>Pending approval: {len(pending)}</li>
    <li>Manual review: {len(manual)}</li>
</ul>

<h3>Auto-Categorized</h3>
<table border="1" cellpadding="5">
    <tr><th>Date</th><th>Payee</th><th>Amount</th><th>Category</th></tr>
    {auto_rows}
</table>

<h3>Pending Approval</h3>
<table border="1" cellpadding="5">
    <tr><th>Payee</th><th>Proposed</th><th>Web Context</th><th>Amount</th></tr>
    {pending_rows}
</table>

<h3>Manual Review</h3>
<table border="1" cellpadding="5">
    <tr><th>Date</th><th>Payee</th><th>Amount</th><th>Note</th></tr>
    {manual_rows}
</table>

<p><small>run_id: {run_id}</small></p>
</body></html>"""
    
    return html


def _compose_imessage_summary(config: dict, auto_apply: list, pending: list, manual: list, run_id: str) -> str:
    """Compose iMessage summary."""
    summary = f"""YNAB digest — {datetime.now().strftime('%Y-%m-%d')}

Auto-categorized: {len(auto_apply)}
Pending approval: {len(pending)}
Manual review: {len(manual)}

"""
    
    if pending:
        summary += "New merchants for approval:\n"
        for i, (txn_id, txn, result) in enumerate(pending[:3], 1):
            summary += f"  {i}. {txn.get('payee_name')} → {result['category']}\n"
    
    if len(pending) > 3:
        summary += f"  ... and {len(pending) - 3} more\n"
    
    summary += f"\nReply 'approve' to lock in new merchants.\nrun_id: {run_id}"
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="YNAB Categorizer")
    parser.add_argument("--dry-send", action="store_true", help="Skip email/iMessage delivery")
    parser.add_argument("--no-apply", action="store_true", help="Skip YNAB PATCH")
    parser.add_argument("--limit-txns", type=int, default=None, help="Limit to N transactions (for testing)")
    args = parser.parse_args()
    
    config = load_config()
    logger = RunLogger()
    
    try:
        # Hop 1: triggered
        logger.emit("triggered", dry_send=args.dry_send, no_apply=args.no_apply)
        
        # Hop 2: auth
        try:
            ynab_token = get_ynab_token()
            anthropic_key = get_anthropic_key()
            logger.emit("auth", ynab_token_obtained=True, anthropic_key_obtained=True)
        except Exception as e:
            logger.emit("error", hop="auth", message=str(e))
            sys.exit(1)
        
        budget_id = config["budget_id"]
        
        # Hop 3: fetch_categories
        resp = ynab_get(f"/budgets/{budget_id}/categories", ynab_token)
        if not resp or "data" not in resp:
            logger.emit("error", hop="fetch_categories", message="Failed to fetch categories")
            sys.exit(1)
        
        all_categories = resp["data"]["category_groups"]
        categories_flat = []
        for group in all_categories:
            for cat in group.get("categories", []):
                if not cat.get("hidden") and cat.get("name") != "Transfer : Savings":
                    categories_flat.append(cat)
        
        category_names = [c["name"] for c in categories_flat]
        logger.emit("fetch_categories", category_count=len(category_names), category_names=category_names[:5])
        
        # Hop 4: fetch_uncategorized
        since_date = (datetime.now(timezone.utc) - timedelta(days=config["lookback_days"])).strftime("%Y-%m-%d")
        resp = ynab_get(f"/budgets/{budget_id}/transactions?since_date={since_date}", ynab_token)
        if not resp or "data" not in resp:
            logger.emit("error", hop="fetch_uncategorized", message="Failed to fetch transactions")
            sys.exit(1)
        
        uncategorized_txns = [
            t for t in resp["data"]["transactions"]
            if t.get("category_id") is None and not t.get("transfer_transaction_id")
        ]
        
        # Limit for testing
        if args.limit_txns:
            uncategorized_txns = uncategorized_txns[:args.limit_txns]
        
        logger.emit("fetch_uncategorized", since_date=since_date, count=len(uncategorized_txns))
        
        # Hop 5: load_lookup
        lookup_path = Path(__file__).parent.parent / "state" / "merchant-lookup.json"
        try:
            lookup = merchant_lookup.load_lookup(lookup_path)
            logger.emit("load_lookup", path=str(lookup_path), entry_count=len(lookup))
        except FileNotFoundError as e:
            logger.emit("error", hop="load_lookup", message=str(e))
            sys.exit(1)
        
        # Hop 6: classify
        auto_apply_list = []
        pending_approval_list = []
        manual_review_list = []
        total_cost = 0.0
        
        for txn in uncategorized_txns:
            txn_id = txn.get("id")
            payee = txn.get("payee_name", "Unknown")
            
            result = classify.classify_transaction(
                txn,
                lookup,
                category_names,
                anthropic_key,
                config,
            )
            
            # Log per-transaction detail
            if result["kind"] == "auto_apply":
                logger.emit("classify_lookup_hit",
                           txn_id=txn_id, payee=payee, category=result["category"],
                           match_type=result["evidence"].get("match_type"))
                auto_apply_list.append((txn_id, txn, result))
            elif result["kind"] == "pending_approval":
                logger.emit("classify_llm_call",
                           txn_id=txn_id, payee=payee,
                           proposed_category=result["category"],
                           confidence=result["confidence"])
                pending_approval_list.append((txn_id, txn, result))
            elif result["kind"] == "manual_review_needed":
                logger.emit("classify_error",
                           txn_id=txn_id, payee=payee,
                           error=result["reasoning"])
                manual_review_list.append((txn_id, txn, result))
        
        logger.emit("classify_summary",
                   auto_apply=len(auto_apply_list),
                   pending_approval=len(pending_approval_list),
                   manual_review_needed=len(manual_review_list),
                   total=len(uncategorized_txns))
        
        # Hop 7: apply_known
        applied_count = 0
        if not args.no_apply:
            for txn_id, txn, result in auto_apply_list:
                category_id = _extract_category_id(categories_flat, result["category"])
                if not category_id:
                    logger.emit("apply_known_error", txn_id=txn_id, error="Category ID not found")
                    manual_review_list.append((txn_id, txn, result))
                    continue
                
                success, resp = ynab_patch(
                    f"/budgets/{budget_id}/transactions/{txn_id}",
                    {"transaction": {"category_id": category_id}},
                    ynab_token,
                )
                
                if success:
                    logger.emit("apply_known_success", txn_id=txn_id)
                    applied_count += 1
                else:
                    logger.emit("apply_known_error", txn_id=txn_id, error=str(resp)[:200])
                    manual_review_list.append((txn_id, txn, result))
        else:
            logger.emit("apply_known_skipped", count=len(auto_apply_list))
        
        # Hop 8: compose_digest (email body)
        email_body = _compose_email_digest(
            config,
            auto_apply_list,
            pending_approval_list,
            manual_review_list,
            logger.run_id,
        )
        logger.emit("compose_digest", email_chars=len(email_body))
        
        # Hop 9: compose_imessage
        imessage_text = _compose_imessage_summary(
            config,
            auto_apply_list,
            pending_approval_list,
            manual_review_list,
            logger.run_id,
        )
        logger.emit("compose_imessage", message_chars=len(imessage_text))
        
        # Hop 10: deliver_email
        if args.dry_send:
            logger.emit("deliver_email_skipped", recipient=config["email_recipient"])
        else:
            ok, detail = deliver.send_email(
                subject=f"YNAB digest — {datetime.now().strftime('%Y-%m-%d')}",
                html_body=email_body,
                to=config["email_recipient"],
            )
            if ok:
                logger.emit("deliver_email_sent", recipient=config["email_recipient"],
                           status=detail.get("status", 200))
            else:
                logger.emit("error", hop="deliver_email", message=str(detail))
                sys.exit(1)
        
        # Hop 11: deliver_imessage
        if args.dry_send:
            logger.emit("deliver_imessage_skipped", target=config["imessage_target"])
        else:
            ok, detail = deliver.send_imessage(imessage_text)
            if ok:
                logger.emit("deliver_imessage_sent", target=config["imessage_target"],
                           status=detail.get("status", 200))
            else:
                logger.emit("error", hop="deliver_imessage", message=str(detail))
                sys.exit(1)
        
        # Hop 12: persist_pending
        pending_path = Path(__file__).parent.parent / "state" / f"pending-{logger.run_id}.json"
        pending_data = [
            {
                "txn_id": txn_id,
                "date": txn.get("date"),
                "payee": txn.get("payee_name"),
                "amount": txn.get("amount") / 1000.0,
                "proposed_category": result["category"],
                "confidence": result["confidence"],
            }
            for txn_id, txn, result in pending_approval_list
        ]
        with open(pending_path, "w") as f:
            json.dump(pending_data, f, indent=2)
        logger.emit("persist_pending", path=str(pending_path), pending_count=len(pending_data))
        
        # Hop 13: done
        logger.emit("cost_total", cost_usd=total_cost)
        logger.emit("done", exit_status=0)
        
    except Exception as e:
        logger.emit("error", hop="main", message=str(e), traceback=str(e))
        sys.exit(1)
    finally:
        logger.close()


if __name__ == "__main__":
    main()
