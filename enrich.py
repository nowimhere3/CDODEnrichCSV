"""
CDODEnrichCSV — Free Contact Enrichment Agent
==============================================
Mimics OpenManus enrichment behavior but:
  - Uses free search waterfall (Google → DDG → Baidu → Bing)
  - Uses Gemini 1.5 Flash free tier (or GPT-4o-mini as fallback)
  - 1 LLM call per row (not 3-4 like a full agent loop)
  - Cost: ~$0.00 with Gemini, ~$0.05-0.15 with GPT-4o-mini for 50 rows

Usage:
  python enrich.py --input your_file.csv --batch 50
  python enrich.py --input your_file.csv --batch 50 --start 50  # next batch
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION — change these if needed
# ─────────────────────────────────────────────

LLM_PROVIDER = "gemini"   # "gemini" (free) or "openai" (~$0.05-0.15/50 rows)
GEMINI_MODEL = "gemini-1.5-flash"     # Free tier: 15 req/min, 1M tokens/day
OPENAI_MODEL = "gpt-4o-mini"          # Cheap: ~$0.003 per 50 rows

SEARCH_PAUSE = 2.0   # Seconds between searches (be polite, avoid rate limits)
MAX_SEARCH_RESULTS = 6

# Search engine order — matches OpenManus exactly
SEARCH_ORDER = ["google", "duckduckgo", "baidu"]

# Admin email prefixes to reject
ADMIN_PREFIXES = [
    "info", "support", "contact", "hello", "help", "sales",
    "team", "admin", "service", "office", "enquiries", "enquiry",
    "mail", "noreply", "no-reply", "webmaster", "postmaster"
]

# ─────────────────────────────────────────────
# SEARCH WATERFALL (all free, no API keys)
# ─────────────────────────────────────────────

def search_google(query: str, num: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Google search via googlesearch-python (free, no key)"""
    try:
        from googlesearch import search
        results = []
        for url in search(query, num_results=num, lang="en", sleep_interval=1):
            results.append({"title": "", "body": "", "href": url})
        return results
    except Exception as e:
        print(f"  [Google] Failed: {e}")
        return []


def search_duckduckgo(query: str, num: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """DuckDuckGo search (free, no key)"""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num))
        return [{"title": r.get("title",""), "body": r.get("body",""), "href": r.get("href","")} for r in results]
    except Exception as e:
        print(f"  [DuckDuckGo] Failed: {e}")
        return []


def search_baidu(query: str, num: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Baidu search (free, no key)"""
    try:
        from baidusearch.baidusearch import search
        results = list(search(query, num_results=num))
        return [{"title": r.get("title",""), "body": r.get("abstract",""), "href": r.get("url","")} for r in results]
    except Exception as e:
        print(f"  [Baidu] Failed: {e}")
        return []


def run_search_waterfall(query: str) -> str:
    """
    Tries Google → DuckDuckGo → Baidu in order.
    Returns formatted search results string for the LLM.
    Stops as soon as one engine returns results.
    """
    search_fns = {
        "google": search_google,
        "duckduckgo": search_duckduckgo,
        "baidu": search_baidu,
    }

    for engine_name in SEARCH_ORDER:
        print(f"  → Trying {engine_name}...", end=" ")
        results = search_fns[engine_name](query)
        if results:
            print(f"✓ got {len(results)} results")
            formatted = []
            for r in results:
                line = f"- {r['title']}: {r['body']} | {r['href']}"
                formatted.append(line.strip(" |:"))
            return "\n".join(formatted)
        else:
            print("✗ no results, trying next...")

    print("  ⚠️  All search engines failed for this query.")
    return ""


# ─────────────────────────────────────────────
# LLM EXTRACTION (1 call per row)
# ─────────────────────────────────────────────

def build_extraction_prompt(name: str, company: str, flagship_offer: str, search_results: str) -> str:
    return f"""You are a contact data researcher. Extract contact information for this person from the search results below.

Person: {name}
Company/Brand: {company}
Flagship Offer / Main Product: {flagship_offer}

Search Results:
{search_results}

Extract the following fields:
- website: Official website URL (NOT a LinkedIn URL, NOT a social media profile)
- email: Personal or direct professional email only. Must contain the person's name (e.g. john@company.com, j.smith@gmail.com). REJECT any email starting with: info, support, contact, hello, help, sales, team, admin, service, office, noreply.
- phone: Direct line or main business phone number
- address: Full street address. US format: Street, Suite, City, State ZIP. International: full address with country. Single line.
- linkedin: Direct LinkedIn profile URL only (must contain linkedin.com/in/)
- other: Notable achievements, certifications, social media handles (Twitter/X, Instagram, YouTube), specialties, awards

Rules:
- If a field cannot be confirmed from the search results, use empty string ""
- Do NOT invent or guess information
- Do NOT put a LinkedIn URL in the website field
- Do NOT include admin/generic emails
- Respond with ONLY valid JSON, no markdown, no explanation:

{{"website":"","email":"","phone":"","address":"","linkedin":"","other":""}}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_gemini(prompt: str) -> dict:
    """Call Gemini 1.5 Flash using the new google-genai SDK (free tier)"""
    try:
        # Try new SDK first (google-genai >= 0.8)
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
    except (ImportError, AttributeError):
        # Fallback to older google-generativeai SDK
        import google.generativeai as genai_old
        genai_old.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai_old.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        text = response.text.strip()

    # Strip markdown code fences if present
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_openai(prompt: str) -> dict:
    """Call OpenAI GPT-4o-mini (~$0.001 per call)"""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = response.choices[0].message.content.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def extract_contact_data(name: str, company: str, flagship_offer: str, search_results: str) -> dict:
    """One LLM call per row to extract all contact fields."""
    empty = {"website":"","email":"","phone":"","address":"","linkedin":"","other":""}
    if not search_results:
        return empty

    prompt = build_extraction_prompt(name, company, flagship_offer, search_results)

    try:
        if LLM_PROVIDER == "gemini":
            return call_gemini(prompt)
        else:
            return call_openai(prompt)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error: {e}")
        return empty
    except Exception as e:
        print(f"  ⚠️  LLM error: {e}")
        return empty


# ─────────────────────────────────────────────
# EMAIL CLASSIFIER
# ─────────────────────────────────────────────

def is_personal_email(email: str, full_name: str) -> bool:
    """
    Returns True if the email looks personal/direct.
    Rejects admin emails and emails with no name match.
    """
    if not email or "@" not in email:
        return False

    email = email.lower().strip()
    local = email.split("@")[0]

    # Reject known admin prefixes
    for prefix in ADMIN_PREFIXES:
        if local == prefix or local.startswith(prefix + ".") or local.startswith(prefix + "_"):
            return False

    # Accept if local part contains part of the person's name
    name_parts = [p.lower() for p in full_name.split() if len(p) > 2]
    for part in name_parts:
        if part in local:
            return True

    # Accept common personal patterns even without name match (e.g. ty@coinbound.io)
    # if the email is clearly not an admin address and is short/personal-looking
    if len(local) <= 10 and not any(local.startswith(p) for p in ADMIN_PREFIXES):
        return True

    return False


# ─────────────────────────────────────────────
# MAIN ENRICHMENT LOOP
# ─────────────────────────────────────────────

NEW_COLUMNS = ["Website", "Email", "Phone", "Address", "LinkedIn", "Other"]


def enrich_csv(input_file: str, batch_size: int = 50, start_row: int = 0):
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ File not found: {input_file}")
        return

    # Re-read to get fieldnames correctly
    with open(input_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        original_fields = list(reader.fieldnames or [])
        all_rows = list(reader)

    batch = all_rows[start_row : start_row + batch_size]
    print(f"\n📋 Loaded {len(all_rows)} total rows. Processing rows {start_row+1}–{start_row+len(batch)}.\n")

    enriched_rows = []
    fallback_rows = []

    for i, row in enumerate(batch):
        full_name = row.get("Full Name", "").strip()
        company   = row.get("Company/Brand", "").strip()
        flagship  = row.get("Their Baby", row.get("Flagship Offer", "")).strip()

        # Skip aliases and brands with no real name
        first_name = row.get("First Name", "").strip()
        if first_name.startswith("(") or full_name.startswith("("):
            print(f"[{i+1}/{len(batch)}] ⏭️  Skipping alias: {full_name}")
            row.update({col: "" for col in NEW_COLUMNS})
            fallback_rows.append(row)
            continue

        print(f"[{i+1}/{len(batch)}] 🔍 Searching: {full_name} @ {company}")

        # Build search query
        query = f'"{full_name}" {company} email website LinkedIn contact'
        search_results = run_search_waterfall(query)

        # LLM extraction — 1 call per row
        print(f"  → Extracting with {LLM_PROVIDER} ({GEMINI_MODEL if LLM_PROVIDER == 'gemini' else OPENAI_MODEL})...")
        contact = extract_contact_data(full_name, company, flagship, search_results)

        # Merge enriched data into row
        row["Website"]  = contact.get("website", "")
        row["Email"]    = contact.get("email", "")
        row["Phone"]    = contact.get("phone", "")
        row["Address"]  = contact.get("address", "")
        row["LinkedIn"] = contact.get("linkedin", "")
        row["Other"]    = contact.get("other", "")

        email = contact.get("email", "")
        if is_personal_email(email, full_name):
            print(f"  ✅ Personal email found: {email}")
            enriched_rows.append(row)
        else:
            reason = f"admin email: {email}" if email else "no email found"
            print(f"  📋 Fallback ({reason})")
            fallback_rows.append(row)

        # Polite pause between rows
        if i < len(batch) - 1:
            time.sleep(SEARCH_PAUSE)

    # ─── Write output files ───
    out_fields = list(original_fields) + [c for c in NEW_COLUMNS if c not in original_fields]
    batch_suffix = f"_rows{start_row+1}-{start_row+len(batch)}"

    enriched_file = f"Enriched{batch_suffix}.csv"
    fallback_file = f"Fallback_EmailNeeded{batch_suffix}.csv"

    with open(enriched_file, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(enriched_rows)

    with open(fallback_file, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(fallback_rows)

    total = len(batch)
    success = len(enriched_rows)
    fallback = len(fallback_rows)
    rate = (success / total * 100) if total > 0 else 0

    summary = f"""
## Enrichment Summary — Batch rows {start_row+1}–{start_row+len(batch)}

| Metric | Count |
|--------|-------|
| Total rows processed | {total} |
| ✅ Enriched (personal email found) | {success} |
| 📋 Fallback (no/admin email) | {fallback} |
| 🎯 Success rate | {rate:.1f}% |

**Output files:**
- `{enriched_file}` — ready to use
- `{fallback_file}` — needs manual review

**LLM:** {LLM_PROVIDER} / {GEMINI_MODEL if LLM_PROVIDER == 'gemini' else OPENAI_MODEL}
**Search waterfall:** {' → '.join(SEARCH_ORDER)}
"""

    print(summary)

    # Save summary to file too
    summary_file = f"Summary{batch_suffix}.md"
    with open(summary_file, "w", encoding='utf-8') as f:
        f.write(summary)
    print(f"📄 Summary saved to {summary_file}")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Free CSV contact enrichment — Google→DDG→Baidu→Bing + Gemini Flash"
    )
    parser.add_argument("--input",  required=True,  help="Input CSV file path")
    parser.add_argument("--batch",  type=int, default=50, help="Number of rows to process (default: 50)")
    parser.add_argument("--start",  type=int, default=0,  help="Row index to start from (default: 0, for next batch use 50, 100, etc.)")
    parser.add_argument("--llm",    default=None, choices=["gemini","openai"], help="Override LLM provider")
    args = parser.parse_args()

    if args.llm:
        LLM_PROVIDER = args.llm

    # Validate API key is present
    if LLM_PROVIDER == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY not set. Add it to your .env file.")
        print("   Get a free key at: https://aistudio.google.com")
        exit(1)
    if LLM_PROVIDER == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Add it to your .env file.")
        exit(1)

    enrich_csv(args.input, batch_size=args.batch, start_row=args.start)
