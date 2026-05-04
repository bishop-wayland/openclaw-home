"""Classification logic: lookup, web search, LLM arbitration."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import merchant_lookup


def _clean_payee(payee: str) -> str:
    """Clean up payee name for web search."""
    # Strip common prefixes
    payee = re.sub(r"^(SP\s+|TST\*|PAYPAL\s+)", "", payee, flags=re.IGNORECASE).strip()
    # Strip everything after @
    payee = payee.split("@")[0].strip()
    # Trim transaction codes (trailing hex-like patterns)
    payee = re.sub(r"\s+[A-F0-9]{8,}$", "", payee, flags=re.IGNORECASE).strip()
    return payee


def web_search(query: str, timeout: float = 5.0) -> dict | None:
    """
    Query DuckDuckGo Instant Answer API.
    
    Returns: {
        "succeeded": bool,
        "snippet": str or None,
        "raw_text": str or None
    }
    """
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "skip_disambig": 1,
        })
        req = urllib.request.Request(url, headers={"User-Agent": "ynab-categorize/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Extract Instant Answer if present, else Abstract
            instant_answer = data.get("Answer") or data.get("AbstractText") or ""
            return {
                "succeeded": bool(instant_answer),
                "snippet": instant_answer[:200] if instant_answer else None,
            }
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        return {
            "succeeded": False,
            "snippet": None,
        }


def classify_with_llm(
    payee: str,
    amount: float,
    date: str,
    category_names: list[str],
    web_snippet: str | None,
    recent_payee_history: list[dict],
    anthropic_key: str,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 200,
) -> dict[str, Any]:
    """
    Call Claude Haiku to classify a transaction.
    
    Returns: {
        "category": str,
        "confidence": float,
        "reasoning": str,
        "tokens_input": int,
        "tokens_output": int,
        "cost_usd": float,
    }
    """
    # Build context
    valid_categories_str = "\n".join(f"  • {cat}" for cat in category_names)
    
    recent_txns_str = ""
    if recent_payee_history:
        recent_txns_str = "\n\nRecent transactions from this merchant:\n"
        for txn in recent_payee_history[-3:]:  # Last 3
            recent_txns_str += f"  • {txn.get('date')} {txn.get('amount')} {txn.get('memo', '')}\n"
    
    web_context = ""
    if web_snippet:
        web_context = f"\n\nWeb search result: {web_snippet}"
    
    prompt = f"""Categorize this YNAB transaction:

Merchant: {payee}
Amount: ${amount:.2f}
Date: {date}{recent_txns_str}{web_context}

Valid categories:
{valid_categories_str}

Return JSON with keys: category, confidence (0.0-1.0), reasoning (1-2 sentences).
Only use categories from the list above."""
    
    try:
        resp = subprocess.run(
            ["curl", "-s", "-X", "POST", "https://api.anthropic.com/v1/messages",
             "-H", "x-api-key: " + anthropic_key,
             "-H", "anthropic-version: 2023-06-01",
             "-H", "content-type: application/json",
             "-d", json.dumps({
                 "model": model,
                 "max_tokens": max_tokens,
                 "messages": [{
                     "role": "user",
                     "content": prompt,
                 }],
             })],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if resp.returncode != 0:
            return {
                "category": None,
                "confidence": 0,
                "reasoning": f"LLM call failed: {resp.stderr[:100]}",
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_usd": 0,
            }
        
        result = json.loads(resp.stdout)
        
        # Extract tokens + cost
        usage = result.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        # Haiku: ~$0.80/$20 per 1M in/out tokens
        cost = (input_tokens * 0.80 + output_tokens * 2.0) / 1_000_000
        
        # Parse response text
        text = result.get("content", [{}])[0].get("text", "{}")
        # Extract JSON from response (handle prose preamble)
        json_match = None
        # Try to find ```json block first
        import re as regex
        json_block = regex.search(r"```(?:json)?\s*(\{[^`]*\})\s*```", text, regex.DOTALL)
        if json_block:
            json_match = json_block.group(1)
        else:
            # Fall back to finding outermost {...}
            json_match = regex.search(r"\{.*\}", text, regex.DOTALL)
            if json_match:
                json_match = json_match.group(0)
        
        if not json_match:
            return {
                "category": None,
                "confidence": 0,
                "reasoning": f"Could not parse JSON from LLM response",
                "tokens_input": input_tokens,
                "tokens_output": output_tokens,
                "cost_usd": cost,
            }
        
        parsed = json.loads(json_match)
        return {
            "category": parsed.get("category"),
            "confidence": float(parsed.get("confidence", 0)),
            "reasoning": parsed.get("reasoning", ""),
            "tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "cost_usd": cost,
        }
    except Exception as e:
        return {
            "category": None,
            "confidence": 0,
            "reasoning": f"LLM call exception: {type(e).__name__}: {str(e)[:100]}",
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_usd": 0,
        }


def classify_transaction(
    txn: dict,
    lookup: dict[str, str],
    category_names: list[str],
    anthropic_key: str,
    config: dict,
) -> dict[str, Any]:
    """
    Full classification pipeline for one transaction.
    
    Returns: {
        "kind": "auto_apply" | "pending_approval" | "manual_review_needed",
        "category": str or None,
        "confidence": float,
        "evidence": dict,
        "reasoning": str,
    }
    """
    payee = txn.get("payee_name", "Unknown")
    
    # Step 1: Lookup hit
    cat, match_type, conf = merchant_lookup.lookup_hit(
        payee, 
        lookup,
        min_partial_key_length=config.get("partial_match_min_key_length", 5),
    )
    if cat:
        return {
            "kind": "auto_apply",
            "category": cat,
            "confidence": conf,
            "evidence": {
                "lookup_hit": True,
                "match_type": match_type,
                "payee": payee,
            },
            "reasoning": f"Found in merchant lookup ({match_type} match)",
        }
    
    # Step 2: Web search + LLM
    cleaned_payee = _clean_payee(payee)
    web_result = web_search(
        f"{cleaned_payee}",
        timeout=config.get("web_search_timeout_seconds", 5),
    )
    snippet = web_result.get("snippet") if web_result.get("succeeded") else None
    
    # Stub: recent_payee_history would come from YNAB's recent txns with same payee
    recent_history = txn.get("_recent_same_payee_txns", [])
    
    llm_result = classify_with_llm(
        payee=cleaned_payee,
        amount=txn.get("amount", 0) / 1000.0,  # YNAB stores as milliunits
        date=txn.get("date", ""),
        category_names=category_names,
        web_snippet=snippet,
        recent_payee_history=recent_history,
        anthropic_key=anthropic_key,
        model=config.get("llm_model", "claude-haiku-4-5"),
        max_tokens=config.get("llm_classify_max_tokens", 200),
    )
    
    if not llm_result["category"]:
        return {
            "kind": "manual_review_needed",
            "category": None,
            "confidence": 0,
            "evidence": {
                "lookup_hit": False,
                "web_search_succeeded": web_result.get("succeeded", False),
                "llm_error": llm_result["reasoning"],
            },
            "reasoning": llm_result["reasoning"],
        }
    
    return {
        "kind": "pending_approval",
        "category": llm_result["category"],
        "confidence": llm_result["confidence"],
        "evidence": {
            "lookup_hit": False,
            "web_snippet": snippet,
            "llm_reasoning": llm_result["reasoning"],
        },
        "reasoning": llm_result["reasoning"],
    }
