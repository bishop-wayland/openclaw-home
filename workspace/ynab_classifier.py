#!/usr/bin/env python3
"""
YNAB Transaction Classifier — Componentized Pipeline

Five-stage classification pipeline:
1. Exact Lookup — hash table from history
2. Pattern Rules — regex matching
3. Recurring Detection — algorithmic pattern matching
4. Web Enrichment — fetch + parse business info
5. LLM Arbitration — final decision with evidence synthesis

Each stage is independently callable. Main orchestration via classify_transaction().
"""

import json
import re
import subprocess
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import urllib.request
import urllib.parse

# ─────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────

VALID_CATEGORIES = [
    "🏠 Home (mortgage, property tax, etc.)",
    "🛠️ Home Maintenance (upkeep, cleaners, etc.)",
    "🚗 Automobile",
    "⚡️ Utilities (Electric, Phone, Internet, etc.)",
    "💔 Divorce",
    "👬🏻 Kids (child expenses, personal budget)",
    "🛒 🥑 Groceries",
    "📦 Household Supplies (Amazon)",
    "💼 Financial (CPA, Advisor, Banks Fees, etc.)",
    "🏥 Healthcare (out of pocket, therapy, massage, etc.)",
    "👖 Clothing",
    "🛋️ Furnishings and Decor",
    "🚴 Recreational Equipment",
    "💻 Electronics and Software",
    "🏋️ Gym Classes",
    "🍽️ Dining Out",
    "🎟️ Entertainment (ski tickets, events, museums, etc.)",
    "🎁 Gifts (xmas, birthdays, etc.)",
    "🎨 Art Supplies",
    "📚 Media (books, records, digital movies)",
    "✈️ Vacation Transportation (Flights, Rental Cars, Etc.)",
    "🏨 Vacation Lodging (Hotels, AirBnB, etc.)",
    "📺 Subscriptions (Netflix, Strava, WSJ, etc.)",
]

@dataclass
class ClassificationResult:
    category: Optional[str]
    confidence: float  # 0.0 to 1.0
    stage: str  # which stage returned the result
    evidence: Dict
    reasoning: str

@dataclass
class WebEnrichmentResult:
    business_type: Optional[str]
    category_hint: Optional[str]
    confidence: float
    raw_search: Dict

@dataclass
class RecurringResult:
    is_recurring: bool
    frequency: str  # "monthly", "weekly", etc.
    occurrence_count: int
    suggested_category: Optional[str]
    confidence: float

@dataclass
class LLMResult:
    category: str
    confidence: float
    reasoning: str


# ─────────────────────────────────────────────────────────────
# Stage 1: Exact Lookup
# ─────────────────────────────────────────────────────────────

def stage1_exact_lookup(payee_name: str, lookup_table: Dict) -> Optional[ClassificationResult]:
    """Check merchant lookup table (from history)."""
    if not payee_name:
        return None
    
    # Exact match
    if payee_name in lookup_table:
        cat = lookup_table[payee_name]
        return ClassificationResult(
            category=cat,
            confidence=0.99,
            stage="Exact Lookup",
            evidence={"match_type": "exact", "payee": payee_name},
            reasoning=f"Found in merchant history: {payee_name} → {cat}"
        )
    
    # Partial match (key is substring of payee)
    for key, cat in lookup_table.items():
        if len(key) > 4 and key.lower() in payee_name.lower():
            return ClassificationResult(
                category=cat,
                confidence=0.85,
                stage="Exact Lookup",
                evidence={"match_type": "partial", "key": key, "payee": payee_name},
                reasoning=f"Partial match in history: '{key}' found in '{payee_name}' → {cat}"
            )
    
    return None


# ─────────────────────────────────────────────────────────────
# Stage 2: Pattern Rules
# ─────────────────────────────────────────────────────────────

PATTERN_RULES = [
    (r"🏠|Home|Mortgage|NewRez|Shellpoint", "🏠 Home (mortgage, property tax, etc.)"),
    (r"Cafe|Coffee|Espresso|Roast|Starbucks|Peet|Dutch Bros", "🍽️ Dining Out"),
    (r"Restaurant|Bistro|Grill|Sushi|Pizza|Taco|Burgers?", "🍽️ Dining Out"),
    (r"Grocery|Groceries|Safeway|QFC|Fred Meyer|Costco|Whole Foods|PCC", "🛒 🥑 Groceries"),
    (r"Auto|Car|Chevron|Shell|ARCO|Gas Station|Jiffy Lube|Valvoline", "🚗 Automobile"),
    (r"Airline|Delta|United|Southwest|Alaska Air|Amtrak", "✈️ Vacation Transportation (Flights, Rental Cars, Etc.)"),
    (r"Hotel|AirBnB|VRBO|Lodging", "🏨 Vacation Lodging (Hotels, AirBnB, etc.)"),
    (r"Netflix|HBO|Spotify|Hulu|Strava|WSJ|Apple Music|Disney", "📺 Subscriptions (Netflix, Strava, WSJ, etc.)"),
    (r"Apple Store|Best Buy|Amazon|Electronics|Software", "💻 Electronics and Software"),
    (r"Yoga|Gym|Fitness|Health Club|Planet Fitness|Peloton", "🏋️ Gym Classes"),
    (r"Clothing|Apparel|Sunspel|Norse|Reigning Champ|Zara|H&M|Nike", "👖 Clothing"),
    (r"Furniture|Sofa|Bed|Decor|IKEA|Article|Wayfair", "🛋️ Furnishings and Decor"),
    (r"Book|Record|Vinyl|Media|Amazon Prime Video|Audible", "📚 Media (books, records, digital movies)"),
    (r"Doctor|Healthcare|Clinic|Pharmacy|CVS|Walgreens|Massage|Therapy", "🏥 Healthcare (out of pocket, therapy, massage, etc.)"),
]

def stage2_pattern_rules(payee_name: str) -> Optional[ClassificationResult]:
    """Match against regex rules."""
    if not payee_name:
        return None
    
    for pattern, category in PATTERN_RULES:
        if re.search(pattern, payee_name, re.IGNORECASE):
            return ClassificationResult(
                category=category,
                confidence=0.75,
                stage="Pattern Rules",
                evidence={"pattern": pattern, "payee": payee_name},
                reasoning=f"Matched pattern '{pattern}' → {category}"
            )
    
    return None


# ─────────────────────────────────────────────────────────────
# Stage 3: Recurring Pattern Detection
# ─────────────────────────────────────────────────────────────

def stage3_recurring_detection(
    payee_name: str,
    amount: float,
    date: str,
    all_transactions: List[Dict]
) -> Optional[RecurringResult]:
    """
    Detect if payee+amount appears regularly (monthly pattern).
    Returns a result if recurring pattern found.
    """
    if not payee_name or not all_transactions:
        return None
    
    # Find all transactions with this payee
    matching = [
        t for t in all_transactions
        if t.get("payee_name") == payee_name and abs(t.get("amount", 0) / 1000 - amount) < 1.0
    ]
    
    if len(matching) < 3:
        return None
    
    # Sort by date
    matching.sort(key=lambda t: t["date"])
    
    # Check if spacing is roughly monthly (25-35 days apart)
    dates = [datetime.strptime(t["date"], "%Y-%m-%d") for t in matching]
    gaps = []
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i-1]).days
        gaps.append(gap)
    
    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    is_monthly = 25 <= avg_gap <= 35
    
    if is_monthly and len(matching) >= 3:
        # This is a recurring monthly transaction
        suggested_cat = None
        if amount > 4000:
            suggested_cat = "💔 Divorce"  # likely alimony
        elif amount < 500:
            suggested_cat = "📺 Subscriptions (Netflix, Strava, WSJ, etc.)"
        
        return RecurringResult(
            is_recurring=True,
            frequency="monthly",
            occurrence_count=len(matching),
            suggested_category=suggested_cat,
            confidence=0.9 if len(matching) >= 6 else 0.7
        )
    
    return None


# ─────────────────────────────────────────────────────────────
# Stage 4: Web Enrichment
# ─────────────────────────────────────────────────────────────

def clean_payee_name(raw_payee: str) -> str:
    """Remove junk from payee names for web search."""
    if not raw_payee:
        return ""
    
    # Remove common prefixes
    cleaned = re.sub(r"^(SP |TST\*|PAYPAL |CHECK )", "", raw_payee)
    # Remove transaction codes/numbers at end
    cleaned = re.sub(r"\s+\d{6,}.*$", "", cleaned)
    cleaned = re.sub(r"CHECKOUT\.\w+$", "", cleaned)
    cleaned = re.sub(r"@.*$", "", cleaned)
    
    return cleaned.strip()

def stage4_web_enrichment(payee_name: str) -> Optional[WebEnrichmentResult]:
    """
    Search for business info using DuckDuckGo instant answers.
    Returns business type and category hint.
    """
    if not payee_name:
        return None
    
    clean_name = clean_payee_name(payee_name)
    if not clean_name or len(clean_name) < 3:
        return None
    
    try:
        query = urllib.parse.quote(clean_name)
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Bishop/1.0"})
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        
        # Look for type info
        abstract = data.get("AbstractText", "")
        answer = data.get("Answer", "")
        
        # Simple heuristics based on keywords
        text = f"{abstract} {answer}".lower()
        category_hint = None
        business_type = None
        
        if any(w in text for w in ["restaurant", "cafe", "bar", "burger", "pizza"]):
            category_hint = "🍽️ Dining Out"
            business_type = "dining"
        elif any(w in text for w in ["yoga", "gym", "fitness", "studio"]):
            category_hint = "🏋️ Gym Classes"
            business_type = "fitness"
        elif any(w in text for w in ["furniture", "decor", "sofa", "bed"]):
            category_hint = "🛋️ Furnishings and Decor"
            business_type = "furniture"
        elif any(w in text for w in ["hotel", "lodging", "motel"]):
            category_hint = "🏨 Vacation Lodging (Hotels, AirBnB, etc.)"
            business_type = "lodging"
        
        if category_hint or business_type:
            return WebEnrichmentResult(
                business_type=business_type,
                category_hint=category_hint,
                confidence=0.65,
                raw_search={"abstract": abstract, "answer": answer}
            )
    
    except Exception as e:
        pass  # Silent fail — web search is optional
    
    return None


# ─────────────────────────────────────────────────────────────
# Stage 5: LLM Arbitration
# ─────────────────────────────────────────────────────────────

def get_llm_api_key() -> str:
    """Fetch Anthropic API key from 1Password."""
    env_path = "/Users/bishop/.openclaw/.env"
    with open(env_path) as f:
        for line in f:
            if "OP_SERVICE_ACCOUNT_TOKEN" in line:
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    
    result = subprocess.run(
        ["/opt/homebrew/Caskroom/1password-cli/2.33.1/op", "read", "op://Bishop/AnthropicApiKey/credential"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch Anthropic API key: {result.stderr}")
    return result.stdout.strip()


def stage5_llm_arbitration(
    payee_name: str,
    amount: float,
    evidence: Dict
) -> Optional[LLMResult]:
    """
    Use Claude Haiku to arbitrate conflicting signals or verify evidence.
    Input: payee, amount, and evidence dict from prior stages.
    Output: final category pick with reasoning.
    """
    try:
        api_key = get_llm_api_key()
    except Exception as e:
        # LLM is optional — if auth fails, return None and caller handles it
        return None
    
    # Build evidence summary
    evidence_text = "Evidence gathered:\n"
    if evidence.get("pattern_match"):
        evidence_text += f"- Pattern rule suggests: {evidence['pattern_match']}\n"
    if evidence.get("web_search"):
        evidence_text += f"- Web search suggests: {evidence['web_search']}\n"
    if evidence.get("recurring"):
        evidence_text += f"- Recurring pattern detected: {evidence['recurring']}\n"
    
    prompt = f"""You are a transaction categorization expert. Given a merchant name and evidence, pick the correct expense category.

Merchant: {payee_name}
Amount: ${amount:.2f}

{evidence_text}

Valid categories:
{chr(10).join(VALID_CATEGORIES)}

Based on the evidence, what is the most likely category? Respond with ONLY:
CATEGORY: [category name]
CONFIDENCE: [0.0-1.0]
REASONING: [one line explanation]"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=150,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse response
        lines = response_text.strip().split("\n")
        category = None
        confidence = 0.0
        reasoning = ""
        
        for line in lines:
            if line.startswith("CATEGORY:"):
                category = line.replace("CATEGORY:", "").strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except:
                    confidence = 0.5
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()
        
        if category and category in VALID_CATEGORIES:
            return LLMResult(
                category=category,
                confidence=min(confidence, 0.95),  # cap at 0.95 — never fully certain
                reasoning=reasoning or "LLM decision based on evidence synthesis"
            )
    
    except Exception as e:
        pass  # Silent fail
    
    return None


# ─────────────────────────────────────────────────────────────
# Main Orchestration
# ─────────────────────────────────────────────────────────────

def classify_transaction(
    payee_name: str,
    amount: float,
    date: str,
    all_transactions: List[Dict],
    merchant_lookup: Dict,
    use_llm: bool = True
) -> ClassificationResult:
    """
    Main classification pipeline. Each stage can return a result;
    if it does, we're done. Otherwise, move to the next stage.
    
    Returns a ClassificationResult with category, confidence, evidence, and reasoning.
    """
    
    # Stage 1: Exact Lookup
    result = stage1_exact_lookup(payee_name, merchant_lookup)
    if result:
        return result
    
    # Stage 2: Pattern Rules
    result = stage2_pattern_rules(payee_name)
    if result:
        return result
    
    # Stage 3: Recurring Detection
    recurring = stage3_recurring_detection(payee_name, amount, date, all_transactions)
    if recurring and recurring.is_recurring:
        # Only use if we have a suggested category
        if recurring.suggested_category:
            return ClassificationResult(
                category=recurring.suggested_category,
                confidence=recurring.confidence,
                stage="Recurring Detection",
                evidence={"count": recurring.occurrence_count, "frequency": recurring.frequency},
                reasoning=f"Recurring {recurring.frequency} transaction ({recurring.occurrence_count} occurrences)"
            )
    
    # Stage 4: Web Enrichment
    web_result = stage4_web_enrichment(payee_name)
    
    # Stage 5: LLM Arbitration (if enabled and we have some evidence)
    if use_llm and (web_result or recurring):
        evidence = {}
        if web_result:
            evidence["web_search"] = web_result.category_hint
        if recurring:
            evidence["recurring"] = recurring.suggested_category
        
        llm_result = stage5_llm_arbitration(payee_name, amount, evidence)
        if llm_result:
            return ClassificationResult(
                category=llm_result.category,
                confidence=llm_result.confidence,
                stage="LLM Arbitration",
                evidence=evidence,
                reasoning=llm_result.reasoning
            )
    
    # No classification found
    return ClassificationResult(
        category=None,
        confidence=0.0,
        stage="None",
        evidence={},
        reasoning="Could not classify this transaction"
    )


# ─────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Load test data
    import sys
    sys.path.insert(0, '/Users/bishop/.openclaw/workspace')
    
    # Load merchant lookup
    try:
        with open('/Users/bishop/.openclaw/workspace/merchant-lookup.json') as f:
            lookup = json.load(f)
    except:
        lookup = {}
    
    # Test cases
    test_cases = [
        ("Arete", 6.73, "2026-02-02"),  # Climbing gym
        ("TMLV KIRKLAND", 42.36, "2025-06-27"),  # Fitness studio
        ("Gbonomi", 156.42, "2026-02-09"),  # Unknown (likely decor)
        ("The Coalman", 81.28, "2025-10-09"),  # Financial/analysis
        ("Hola House", 50.00, "2025-05-01"),  # Yoga studio
    ]
    
    print("Testing YNAB Classifier Pipeline\n" + "="*60)
    
    for payee, amount, date in test_cases:
        result = classify_transaction(payee, amount, date, [], lookup, use_llm=False)
        print(f"\nPayee: {payee}")
        print(f"Amount: ${amount:.2f}")
        print(f"Stage: {result.stage}")
        print(f"Category: {result.category or 'Uncategorized'}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Reasoning: {result.reasoning}")
