#!/usr/bin/env python3
"""
ynab-autocategorize.py

Fetches uncategorized YNAB transactions and applies rule-based categorization.

Modes:
  --dry-run   (default) Print what would be changed, no API writes
  --apply     Actually update YNAB
"""
import os, sys, re, json, subprocess, urllib.request, urllib.error
from datetime import datetime

BUDGET_ID = "2f6bc004-22ff-4e29-be77-a8907cb1c537"
BASE_URL = "https://api.ynab.com/v1"

# ─────────────────────────────────────────────
# Merchant → Category rules (case-insensitive regex)
# Category names must match YNAB exactly.
# ─────────────────────────────────────────────
# Transactions we intentionally skip (transfers, income, starting balances — not real spending)
SKIP_PATTERNS = [
    r"^Transfer :",
    r"META PAYROLL|META DIRECT DEP",
    r"^Starting Balance",
    r"^ZELLE (TO|FROM)",
    r"IRS\b",
    r"WA DIR ACH",
    r"BLM University",   # appears to be tuition/kid expense — leave for manual
    r"CONNECTYOURCARE|OPTUMCLAIM",  # HSA reimbursement
    r"Airbnb.*\+\$",  # Airbnb refunds
]

RULES = [
    # Housing / Mortgage
    (r"NewRez|Shellpoint|Mortgage",                         "🏠 Home (mortgage, property tax, etc.)"),

    # Home Maintenance
    (r"Holahousewa|Hola House|House Cleaner|Home Depot|Lowe.?s|Ace Hardware|True Value|Roto.?Rooter", "🛠️ Home Maintenance (upkeep, cleaners, etc.)"),

    # Auto
    (r"Buttera Motors|Autocare|Auto Care|Jiffy Lube|Valvoline|Midas|Meineke|Pep Boys|Washington Dep.* Licens|WA.*Licens|DOL |Dept of Licens|Honda of Kirkland|Discount Tire|76\b|76 Gas|76 - DBA|Chevron|ARCO|Minit Stop|Car Wash", "🚗 Automobile"),

    # Recreational Equipment (cycling, sports, outdoor, ski)
    (r"Fizik|REI\b|Backcountry|Competitive Cyclist|Chain Reaction|Wiggle|Trek Bicy|Specialized|Garmin|Wahoo|GoPro|Canyon Bicycles|Kirkland Bicycle|Assos|POC Sports|Boardsports|Fumpa Pumps|Vortello Cycling|BIKECLOSET|Enve Composites|Exposure Lights|LiteSmith|Uswe Sports|Evoc Sports|Rinsekit|Feathered Friends|Garage Grown|Christy.?Sports|Rocky Mountain Ski|Edge & Spoke|Fleischer Sport|EVO\b|EVO Outlet|EVO Rentals|Blue Owl Workshop|SP FUMPA|Movemint|Gravity Grabber|YETI\b|Summit Sage|Pro Guiding|Snowvana|Wild Willies", "🚴 Recreational Equipment"),

    # Dining / Coffee / Bars
    (r"Burgers?|Cafe\b|Caf[eé]\b|Salt & Straw|Bistro|Grill\b|Sushi|Pizza|Taco|7-Eleven|Seven.?Eleven|Hudson St|Wibbley|Bill.?s Cafe|Zona Rosa|Zoka|Dunn(?! Lumber)|Clementine|Red Radish|Trade Coffee|Starbucks|Peet.?s|Dutch Bros|Panera|Chiposte|MOD Pizza|Shake Shack|Dick.?s Drive|Ramen|Izakaya|Dough Zone|Ben & Jerry.?s|Cold Stone|McConnell.?s|Ice Crea|Creamery|Ice Cream|Cone|Pastry|Bakery|Coffee|Espresso|Roast|Ristorante|Osteria|Trattoria|Enoteca|Steakhouse|Brasserie|Tavern|Pub\b|Public House|Saloon|Brewing|Brewery|Taproom|Bar\b|Lounge|Kitchen|Restaurant|Feast|Bottle.*Bull|Walrus.*Carpenter|Well and Table|Smoothie|Taqueria|Pepino|Jam on|Little Griddle|Oro\b|Lovely.?s|Nightingale|Iron Duck|Locochon|Root Down|Truffle Pig|Thunderhead|Schmiggity|Sunpies|4th Street|Flour House|Finney.?s|Giuseppe|Novo Restaurant|Pearl Social|Pismo Beach Club|The Lark|The Nook|Helena Ave Bakery|Mountain View Diner|Pie Dive Bar|White Buffalo|8th Street Steak|Tastes on the Fly|Thruline|Coava|Sightglass|Pioneer Coffee|Scout Coffee|Dote Coffee|Great American Bagel|Laconia Market|Moguls Coffee|Java Ketchum|COFFEE & CONE|Ccs Espresso|Kortado|Scorpion|Camden Foods|Zip Market|Grand Avenue Market|Vg Grand Avenue|Fresh Pot|Kitchen & Market|The Markets|Village Market|Grocery Store|Lassen.?s Natural|Sun Valley Food|Sprouts Farmer|Mollie Stone.?s", "🍽️ Dining Out"),

    # Healthcare
    (r"Massage|Health Lab|Caremark|CVS\b|Walgreens|Pharmacy|Medical|Clinic|Kaiser|Providence|UW Med|Dental|Vision|Evergreen Health|Benevedes|Therapist|Therapy", "🏥 Healthcare (out of pocket, therapy, massage, etc.)"),

    # Subscriptions
    (r"HBO\b|Netflix|Strava|Spotify|Apple\.com/bill|Google Workspace|Sublime Hq|Wall Street Journal|WSJ\b|Hulu|Disney\+|Amazon Prime|Paramount|Peacock|YouTube Premium|iCloud|1Password|Notion|Premseat|Hinge\.co|Tinder\b|SP SPOTMINDERS", "📺 Subscriptions (Netflix, Strava, WSJ, etc.)"),

    # Groceries (expanded)
    (r"PCC\b|Whole Foods|Safeway|QFC\b|Fred Meyer|Marche|Trader Joe|Costco|Kroger|Metropolitan Market|Central Co.?op|Uwajimaya|H Mart|New Seasons|Town & Country|Sprouts Farm", "🛒 🥑 Groceries"),

    # Clothing
    (r"Sunspel|Mission Workshop|Norse Projects|Reigning Champ|Dickies|Allister|Filson|Patagonia|Arc.?teryx|Columbia Sport|Nordstrom|Banana Republic|Uniqlo|Buck Mason|Vuori|James Perse|SP JAMES PERSE|Aritzia|Marine Layer|Zara\b|Saks Fifth|Bloomingdale|Hugo Boss|Warby Parker|Sephora|Ten Thousand|Vans\b|Fjorn|Zappos|Stio Mountain", "👖 Clothing"),

    # Electronics & Software
    (r"Apple Store|Best Buy|B&H Photo|Adorama|Apple Online|Microsoft|Amazon\.com.*device|Steam\b|Humble Bundle|SP GLAZERS CAMERA|Glazers Camera|Anthropic|Backblaze|Fatcow|Ipage|YouTube Videos|Meta Store", "💻 Electronics and Software"),

    # Art Supplies
    (r"Epson|Crafted Elements|Blick|Art Supply|Jerry.?s Artarama|Utrecht|Gamblin|Golden Artist|Winsor|Rosemary and Co|Rosemary & Co|Big Duck Canvas|SD Framing|Rockler Woodworking|Dunn Lumber|SP MEEDEN ART", "🎨 Art Supplies"),

    # Media (books, records, digital)
    (r"Half Price Books|Powell.?s|Amazon.*books|Bandcamp|Discogs|Vinyl|Record Store|Barnes.*Noble|Kindle|Elliott Bay Book|Jackpot Records|Boo Boo Records|Selector Records|Bleep\b|Raarecords|Lighthouse Publications|Phoenix Books", "📚 Media (books, records, digital movies)"),

    # Entertainment
    (r"Park Stevens Pass|Stevens Pass|Liftopia|Ticketmaster|AXS\b|Eventbrite|AMC\b|Regal\b|Fandango|Museum|Seattle Art|SAM\b|Cinemark|See Tickets|Snowvana|The Audacity|Ba Start Arcade|Life on Mars|SHOOTOUT LACROSSE", "🎟️ Entertainment (ski tickets, events, museums, etc.)"),

    # Vacation Transportation
    (r"Delta Air Lines|United\b|Southwest|Alaska Air|American Air|British Airways|Amtrak|MTA NYCT|KONA AIRPORT|Santa Barbara Airport|Washington State Ferries|PARKLINQ|LAZ Parking|Diamond Parking|Impark|Rainier Square", "✈️ Vacation Transportation (Flights, Rental Cars, Etc.)"),

    # Vacation Lodging
    (r"Airbnb|VRBO|Hotel\b|Hotelcom|Aava Whistler|Parkjames|North Cascades Lodge|Stehekin Valley|Marina Beach Motel|Sunrise Inn|Hotel Ketchum|Four Points Lodge", "🏨 Vacation Lodging (Hotels, AirBnB, etc.)"),

    # Home Maintenance (expanded)
    (r"Holahousewa|Hola House|Home Depot|Lowe.?s|Ace Hardware|True Value|Roto.?Rooter|Dunn Lumber|King County Ww|KC Solid Waste|CSC Serviceworks|Kirkland Glass|Restaurant Furniture|Lake Washington Garage Door|Rose Hill Car Wash|ZELLE TO LAKE WASHINGTON", "🛠️ Home Maintenance (upkeep, cleaners, etc.)"),

    # Household / Furnishings
    (r"Container Store|Wayfair|Article\.com|ARTICLE \d|Yamazaki|Heath Ceramics|SP CAPITAL COOKWARE|Prettypegs|Sur La Table|Ravenna Gardens|Ecovibe|Tender Loving Empire|Glasswing|Karst Goods", "🛋️ Furnishings and Decor"),

    # Gifts
    (r"Gifts|Gift Card|Seeds\b|Urbanite|Tender Loving|Ecovibe", "🎁 Gifts (xmas, birthdays, etc.)"),

    # Kids / College
    (r"Cal Poly|Whittier College|University of Washington|BLM University|SHOOTOUT LACROSSE", "👬🏻 Kids (child expenses, personal budget)"),

    # Vacation Transportation (gas, parking on trips)
    (r"Orbitz|World Oil|The Fuel Stop|Boise Depot|Kona International", "✈️ Vacation Transportation (Flights, Rental Cars, Etc.)"),

    # More dining I missed
    (r"Brooklyn Bros|El Rinconsito|9th & Pike|Dan Gui|Devoción|Just Poke|Las Brisas|TST\*HUMPY|TWO BASIN ADVENTURE|Dough Zone|Lovely.?s Fifty|Jam on Hawthorne|Pepino.?s|Little Griddle|Oro\b|The Grape Choice|San Luis Taqueria|McDonald|Reimer.?s Candies|Short Stop|Steamboat Ski|Midnight Cookie|Friends & Co Ice|Mountain Village|Laundry and Creekside|Umauma|Euphoria|Aurora Borealis", "🍽️ Dining Out"),

    # Healthcare (expanded)
    (r"Premier Periodontics|MultiCare|Dental|Optum|CONNECTYOURCARE|Jadeyoga", "🏥 Healthcare (out of pocket, therapy, massage, etc.)"),

    # Financial / Divorce related
    (r"D J\b",                                               "💔 Divorce"),

    # Utilities / Tax
    (r"WA DIR ACH|Puget Sound Energy|PSE\b|Comcast|Xfinity|T-Mobile|Verizon|CenturyLink|Lumen|Seattle City Light|Seattle Public Util|Waste Management", "⚡️ Utilities (Electric, Phone, Internet, etc.)"),

    # Financial
    (r"CPA|Advisor|Bank Fee|Wire Fee|Overdraft|Schwab|Fidelity|Vanguard|TurboTax|H&R Block", "💼 Financial (CPA, Advisor, Banks Fees, etc.)"),

    # Shipping / Misc household
    (r"FedEx|UPS\b|USPS|Shipping", "📦 Household Supplies (Amazon)"),

    # Kids
    (r"Mobile Banking Deposit",                             "👬🏻 Kids (child expenses, personal budget)"),
]

# ─────────────────────────────────────────────
# Auth + API helpers
# ─────────────────────────────────────────────

def get_token():
    env_path = "/Users/bishop/.openclaw/.env"
    with open(env_path) as f:
        for line in f:
            if "OP_SERVICE_ACCOUNT_TOKEN" in line:
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    result = subprocess.run(
        ["/opt/homebrew/Caskroom/1password-cli/2.33.1/op", "read", "op://Bishop/YnabApiKey/credential"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"1Password error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def ynab_get(path, token):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def ynab_patch(path, body, token):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ─────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────

def is_skip(payee_name):
    """Return True if this transaction should be silently skipped (transfers, income, etc.)"""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, payee_name or "", re.IGNORECASE):
            return True
    return False


def classify(payee_name):
    """Return a category name if we have a confident rule match, else None."""
    for pattern, category in RULES:
        if re.search(pattern, payee_name or "", re.IGNORECASE):
            return category
    return None


# Load merchant lookup table
LOOKUP_PATH = "/Users/bishop/.openclaw/workspace/merchant-lookup.json"
try:
    with open(LOOKUP_PATH) as f:
        MERCHANT_LOOKUP = json.load(f)
except FileNotFoundError:
    MERCHANT_LOOKUP = {}


def lookup_merchant(payee_name):
    """Check the history-based merchant lookup table first."""
    if not payee_name:
        return None
    # Exact match
    if payee_name in MERCHANT_LOOKUP:
        return MERCHANT_LOOKUP[payee_name]
    # Partial match — check if any lookup key is contained in the payee name
    for key, cat in MERCHANT_LOOKUP.items():
        if len(key) > 4 and key.lower() in payee_name.lower():
            return cat
    return None


def get_category_id(categories_by_name, name):
    return categories_by_name.get(name)


def main():
    dry_run = "--apply" not in sys.argv
    mode = "DRY RUN" if dry_run else "LIVE — WRITING TO YNAB"

    token = get_token()

    # Load all categories
    cats_data = ynab_get(f"/budgets/{BUDGET_ID}/categories", token)
    categories_by_name = {}
    for group in cats_data["data"]["category_groups"]:
        for cat in group["categories"]:
            categories_by_name[cat["name"]] = cat["id"]

    # Fetch all transactions (full backlog)
    txns_data = ynab_get(f"/budgets/{BUDGET_ID}/transactions", token)
    txns = txns_data["data"]["transactions"]

    # Filter uncategorized (no category_id or category is null)
    uncategorized = [t for t in txns if not t.get("category_id")]

    print(f"\n{'='*72}")
    print(f"  YNAB Auto-Categorizer — {mode}")
    print(f"{'='*72}")
    print(f"  Uncategorized transactions: {len(uncategorized)}")
    print(f"  Mode: {mode}\n")

    to_update = []
    skipped = []

    for t in sorted(uncategorized, key=lambda x: x["date"]):
        payee = t.get("payee_name") or "Unknown"
        amount = t["amount"] / 1000.0
        date = t["date"]

        # Silently skip transfers, income, and other non-spending entries
        if is_skip(payee):
            continue

        # Try lookup table first (history-based), then rules
        category = lookup_merchant(payee) or classify(payee)

        if category:
            cat_id = get_category_id(categories_by_name, category)
            if cat_id:
                to_update.append((t["id"], date, payee, amount, category, cat_id))
            else:
                skipped.append((date, payee, amount, f"CATEGORY NOT FOUND IN YNAB: '{category}'"))
        else:
            skipped.append((date, payee, amount, "No rule match — needs manual review"))

    # Print what will be categorized
    if to_update:
        print(f"  ✅ WILL CATEGORIZE ({len(to_update)} transactions):")
        print(f"  {'-'*68}")
        for txn_id, date, payee, amount, category, cat_id in to_update:
            print(f"  {date}  {payee:<32} ${abs(amount):>9.2f}  →  {category}")
        print()

    # Print skipped
    if skipped:
        print(f"  ⚠️  SKIPPED ({len(skipped)} transactions — manual review needed):")
        print(f"  {'-'*68}")
        for date, payee, amount, reason in skipped:
            sign = "+" if amount > 0 else "-"
            print(f"  {date}  {payee:<32} {sign}${abs(amount):>8.2f}  →  {reason}")
        print()

    if dry_run:
        print(f"  — Dry run complete. Run with --apply to write changes to YNAB.")
        print(f"{'='*72}\n")
        return

    # Apply changes
    print(f"  Applying {len(to_update)} updates to YNAB...")
    success = 0
    for txn_id, date, payee, amount, category, cat_id in to_update:
        try:
            ynab_patch(
                f"/budgets/{BUDGET_ID}/transactions/{txn_id}",
                {"transaction": {"category_id": cat_id}},
                token
            )
            print(f"  ✓ {payee:<32} → {category}")
            success += 1
        except Exception as e:
            print(f"  ✗ {payee:<32} → ERROR: {e}")

    print(f"\n  Done. {success}/{len(to_update)} transactions categorized.")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    main()
