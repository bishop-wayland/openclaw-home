#!/usr/bin/env python3
"""
Apply merchant additions from Dave's approval reply.

Parses iMessage replies like:
  "approve"
  "approve, but change Zona Rosa to Gifts"
  "approve all except Hola House"

Usage:
  python3 apply-additions.py --run-id <id> --message "<reply text>"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from logger import RunLogger
import merchant_lookup
import deliver


def parse_approval_reply(message: str, pending_data: list[dict]) -> dict:
    """
    Parse Dave's reply and extract approvals + overrides.
    
    Returns: {
        "approve_all": bool,
        "overrides": {"merchant_name": "new_category", ...},
        "skip": ["merchant_name", ...],
    }
    """
    result = {
        "approve_all": False,
        "overrides": {},
        "skip": [],
    }
    
    message_lower = message.lower()
    
    # Check for "approve" keyword
    if "approve" not in message_lower:
        return result
    
    # Check for "approve all except X"
    except_match = re.search(r"approve\s+all\s+except\s+(.+?)(?:\.|,|$)", message_lower)
    if except_match:
        skip_text = except_match.group(1)
        # Extract merchant names from the except clause
        for item in skip_text.split(","):
            skip_name = item.strip().title()
            for pending in pending_data:
                if skip_name.lower() in pending["payee"].lower():
                    result["skip"].append(pending["payee"])
        result["approve_all"] = True
    
    # Check for "approve, but change X to Y"
    change_matches = re.findall(r"change\s+(.+?)\s+to\s+(.+?)(?:,|$)", message, re.IGNORECASE)
    for from_name, to_category in change_matches:
        from_name = from_name.strip()
        to_category = to_category.strip()
        # Find matching merchant in pending
        for pending in pending_data:
            if from_name.lower() in pending["payee"].lower():
                result["overrides"][pending["payee"]] = to_category
    
    if "approve" in message_lower and not (except_match or change_matches):
        result["approve_all"] = True
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Apply merchant additions from approval reply")
    parser.add_argument("--run-id", required=True, help="Run ID from pending approval file")
    parser.add_argument("--message", required=True, help="Dave's reply message")
    args = parser.parse_args()
    
    logger = RunLogger(run_id=args.run_id)
    
    try:
        # Load the pending file
        pending_path = Path(__file__).parent.parent / "state" / f"pending-{args.run_id}.json"
        if not pending_path.exists():
            logger.emit("error", message=f"Pending file not found: {pending_path}")
            sys.exit(1)
        
        with open(pending_path, "r") as f:
            pending_data = json.load(f)
        
        logger.emit("load_pending", path=str(pending_path), count=len(pending_data))
        
        # Parse the reply
        approval = parse_approval_reply(args.message, pending_data)
        logger.emit("parse_reply", approve_all=approval["approve_all"],
                   override_count=len(approval["overrides"]),
                   skip_count=len(approval["skip"]))
        
        # Load lookup
        lookup_path = Path(__file__).parent.parent / "state" / "merchant-lookup.json"
        lookup = merchant_lookup.load_lookup(lookup_path)
        
        # Apply additions
        additions = {}
        for pending in pending_data:
            payee = pending["payee"]
            
            # Skip if in skip list
            if payee in approval["skip"]:
                logger.emit("approval_skip", payee=payee, reason="Explicitly skipped")
                continue
            
            # Use override if present, else proposed
            category = approval["overrides"].get(payee, pending["proposed_category"])
            
            # Add to lookup
            merchant_lookup.append_to_lookup(payee, category, lookup)
            additions[payee] = category
            logger.emit("approval_add", payee=payee, category=category)
        
        # Save lookup
        merchant_lookup.save_lookup(lookup, lookup_path)
        logger.emit("save_lookup", path=str(lookup_path), new_entries=len(additions))
        
        # Send confirmation iMessage
        confirm_text = f"✅ Added {len(additions)} merchant{'s' if len(additions) != 1 else ''}:\n"
        for payee, category in additions.items():
            confirm_text += f"  • {payee} → {category}\n"
        confirm_text += f"\nActive next Sunday. run_id: {args.run_id}"
        
        ok, detail = deliver.send_imessage(confirm_text)
        if ok:
            logger.emit("deliver_confirmation", status=detail.get("status", 200))
        else:
            logger.emit("error", hop="deliver_confirmation", message=str(detail))
        
        logger.emit("done", exit_status=0, additions_count=len(additions))
        
    except Exception as e:
        logger.emit("error", message=str(e))
        sys.exit(1)
    finally:
        logger.close()


if __name__ == "__main__":
    main()
