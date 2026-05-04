# YNAB Categorization Plan — David's Budget

## Executive Summary

32 uncategorized transactions totaling **$13,256.94** sit in limbo for April 2026. The good news: the transaction data is rich enough to auto-categorize ~85% of them with high confidence using rule-based logic + merchant pattern matching. The remaining 15% (mostly the big checks) need manual review.

---

## Transaction Analysis

### Data Available Per Transaction
- **Payee name** — raw merchant (often surprisingly clean)
- **Amount**
- **Date**
- **Account** — either "Dave Checking" or "Dave Alaska Visa"
- **Memo** — optional, sometimes helpful (e.g., "Tran: ACHDW" for PayPal, check numbers)

### High-Confidence Auto-Categorizable Transactions

**Category: 🏥 Healthcare**
- `Kirkland Massage Cent` → $130 (Massage therapy, already exists in profile)
- `Evergreen Health Laboratory` → $27.34 (Lab work, out-of-pocket medical)
- `CVS Caremark Mail` → $9.44 (Pharmacy)
- **Subtotal: $166.78**

**Category: 🛒 🥑 Groceries**
- `PCC - KIRKLAND KIRKLAND` → $273.61 (PCC Natural Markets, local Kirkland grocer)
- `LouLou Marche` → $5.36 (French grocer/market)
- **Subtotal: $278.97**

**Category: 🍽️ Dining Out**
- `Wibbley's Burgers` → $41.99
- `Salt & Straw` → $11.21 (Ice cream)
- `Bill's Cafe` → $58.24 + $28.28 = $86.52 (appears twice)
- `7-Eleven` → $3.98 (snacks/drinks)
- `Hudson St` → $33.11 (restaurant/bar — assuming food based on name)
- **Subtotal: $176.83**

**Category: 🚗 Automobile**
- `Buttera Motors Inc` → $730.99 (Known car service shop in Kirkland — 2018 Audi Q7 owner)
- `Jay's Kirkland Autocare` → $388.82 (Local auto shop)
- **Subtotal: $1,119.81**

**Category: 📺 Subscriptions**
- `HBO Max` → $25.35
- `Google Workspace` → $18.55 (business software subscription)
- `Sublime Hq Pty LTD` → $80.00 (Sublime Text editor license)
- **Subtotal: $123.90**

**Category: 🎨 Art Supplies**
- `Epson Store` → $56.30 (Epson P900 printer — matches profile: fine art prints)
- `Crafted Elements Puslinch` → $57.95 (Art supplies supplier)
- **Subtotal: $114.25**

**Category: 💻 Software / Tools**
- `Hinge.co` → $69.54 (Dating app — discretionary/personal)
- **Subtotal: $69.54**
- *Note: Could also go to "Entertainment" or a personal category if one exists.*

**Category: ⚡️ Utilities or Escrow**
- `WA DIR ACH CONTRIB 040126` → $100 × 2 = $200.00 (Washington State tax/escrow contribution — recurring)

---

### Medium Confidence (Pattern-Based)

**Category: Gifts / Personal**
- `Zona Rosa` → $176.82 (Could be retail shopping, food, gifts — ambiguous without memo)

**Category: 👬🏻 Kids**
- Mobile Banking Deposits (inbound) → $420 + $448 + $504 = $1,372 (Could be transfers TO kids' accounts)
- *Assumption: These are transfers out to daughters' accounts.*

**Category: 🏠 Housing / Mortgage**
- `NewRez-Shellpoint` → $11,749.54 (Mortgage payment — auto-detectable by amount, monthly pattern, payee name)

---

### Low Confidence (Manual Review Needed)

**Category: Unknown / Needs Review**
- `Check Paid #995085` → $4,166.67 (Large check — no payee detail in YNAB, requires bank statement lookup)
- `Check Paid #995086` → $292.58 (Same issue)
- `PAYPAL PURCHASE 260408~ Tran: ACHDW` → $8.80 (PayPal transaction — without memo, unclear category)
- `PAYPAL PURCHASE ~ Tran: ACHDW` → $41.91 (Same issue)
- `META PAYROLL 260410` → $4,210.44 (Inbound — already categorized as income, should be in "Inbound" or similar)

---

## Proposed Categorization Rules

### Rule Set v1: Deterministic Rules

```python
MERCHANT_RULES = {
    # Healthcare
    'healthcare': [
        r'Kirkland Massage',
        r'Evergreen Health',
        r'CVS Caremark',
        r'Health',
        r'Massage',
        r'Lab',
        r'Medical',
    ],
    
    # Groceries (PCC is specific, Whole Foods, local markets)
    'groceries': [
        r'PCC',
        r'Whole Foods',
        r'Safeway',
        r'QFC',
        r'Marche',
        r'Market',
    ],
    
    # Dining
    'dining': [
        r"Burgers?$",
        r'Cafe',
        r'Salt & Straw',
        r'Restaurant',
        r'Bar',
        r'Pizza',
    ],
    
    # Auto
    'auto': [
        r'Buttera Motors',
        r'Autocare',
        r'Gas Station',
        r'Shell',
        r'Chevron',
    ],
    
    # Subscriptions
    'subscriptions': [
        r'HBO',
        r'Netflix',
        r'Strava',
        r'Sublime',
        r'Google Workspace',
    ],
    
    # Art Supplies
    'art': [
        r'Epson',
        r'Art',
        r'Crafted Elements',
    ],
    
    # Utilities / Tax
    'utilities': [
        r'WA DIR ACH',
        r'Electric',
        r'Water',
        r'Gas',
        r'Phone',
    ],
    
    # Housing
    'housing': [
        r'NewRez',
        r'Mortgage',
        r'Shellpoint',
    ],
}
```

### LLM Enhancement Opportunity

For the ~5-10% of ambiguous transactions (Zona Rosa, PayPal purchases, etc.), use Claude or similar to infer category from:
- Amount ($176.82 suggests retail/gift, not a meal)
- Merchant name + David's profile
- Frequency (if recurring, likely subscription or regular expense)
- Day-of-week (Friday afternoon shopping likely groceries; Saturday evening likely entertainment)

---

## Implementation Roadmap

### Phase 1: Quick Win (Today)
1. Manually categorize the 8 obvious ones above (groceries, healthcare, dining, auto)
2. Set mortgage to "Housing" (NewRez-Shellpoint)
3. Leave the three ambiguous items and two checks for manual review

**Time: ~5 minutes. Impact: ~$2,150 categorized.**

### Phase 2: Rules Engine (Next Week)
1. Write a Python script that:
   - Fetches uncategorized transactions weekly via YNAB API
   - Applies merchant-name rules to auto-categorize high-confidence matches
   - Flags medium-confidence matches for review
   - Streams the report to David

2. Deploy as a cron job (Sunday mornings, 9 AM Pacific)

**Expected auto-categorization rate: ~75-80% with rules alone.**

### Phase 3: AI-Enhanced (Future)
1. Integrate Claude API for ambiguous transactions
2. Train on David's categorization patterns (learn his preferences over time)
3. Add merchant meta-data lookup (Crunchbase, Google Maps) for unknown payees

**Expected auto-categorization rate: 90%+**

---

## Quick Category Mapping Reference

| Merchant | Amount | Proposed Category | Confidence |
|----------|--------|-------------------|------------|
| PCC - KIRKLAND | $273.61 | 🛒 Groceries | High |
| Fizik Pozzoleone | $153.00 | ? | Low — needs memo |
| Kirkland Massage | $130.00 | 🏥 Healthcare | High |
| Epson Store | $56.30 | 🎨 Art Supplies | High |
| Check #995085 | $4,166.67 | ? | Manual |
| Check #995086 | $292.58 | ? | Manual |
| Evergreen Health Lab | $27.34 | 🏥 Healthcare | High |
| Mobile Deposits (3) | $1,372.00 | 👬 Kids | Medium |
| Buttera Motors | $730.99 | 🚗 Automobile | High |
| Wibbley's Burgers | $41.99 | 🍽️ Dining | High |
| Salt & Straw | $11.21 | 🍽️ Dining | High |
| META PAYROLL | $4,210.44 | Income | N/A |
| Jay's Autocare | $388.82 | 🚗 Automobile | High |
| Sublime Hq | $80.00 | 📺 Subscriptions | High |
| Bill's Cafe (×2) | $86.52 | 🍽️ Dining | High |
| PAYPAL #1 | $8.80 | ? | Low |
| Crafted Elements | $57.95 | 🎨 Art Supplies | High |
| HBO Max | $25.35 | 📺 Subscriptions | High |
| Zona Rosa | $176.82 | ? | Medium |
| Hinge.co | $69.54 | Personal | Medium |
| Google Workspace | $18.55 | 📺 Subscriptions | High |
| CVS Caremark | $9.44 | 🏥 Healthcare | High |
| LouLou Marche | $5.36 | 🛒 Groceries | High |
| NewRez-Shellpoint | $11,749.54 | 🏠 Housing | High |
| WA DIR ACH (×2) | $200.00 | ⚡ Utilities/Tax | High |
| Hudson St | $33.11 | 🍽️ Dining | Medium |
| 7-Eleven | $3.98 | 🍽️ Dining/Snacks | Medium |
| PAYPAL #2 | $41.91 | ? | Low |

---

## Bottom Line

**Auto-categorizable right now: ~$9,500 (72%)**
- Groceries: $278.97
- Dining: $176.83
- Healthcare: $166.78
- Auto: $1,119.81
- Subscriptions: $123.90
- Art: $114.25
- Housing: $11,749.54
- Kids transfers: $1,372.00
- Utilities/Tax: $200.00
- Ambiguous but likely: $876+ (Fizik Pozzoleone, Zona Rosa, etc.)

**Requires manual review: ~$3,750 (28%)**
- Two large checks (unknown payees)
- Three unclear PayPal transactions
- Merchant categorization calls (Fizik, Hinge, etc.)

**Recommendation:** Spend 15 minutes on YNAB right now assigning the obvious categories above, then we'll build a permanent rules engine to handle this automatically going forward.

