# CDODEnrichCSV — Free CSV Contact Enrichment Agent

Automatic contact enrichment for coaching/crypto leads. Uses a **free search waterfall** (no API keys needed for search) and **Google Gemini Flash** (free tier) for extraction.

## Cost
- **Search:** $0.00 — Google → DuckDuckGo → Baidu → Bing, all free libraries
- **LLM:** $0.00 — Gemini 1.5 Flash free tier (15 req/min, 1M tokens/day)
- **50 rows:** ~$0.00 to $0.15 max (only if you switch to GPT-4o-mini)

## What It Does
1. Reads your CSV file
2. Searches the web for each person using the free waterfall
3. Extracts: Website, Email, Phone, Address, LinkedIn, Other
4. Splits output into:
   - `Enriched.csv` — rows with a valid personal email found
   - `Fallback_EmailNeeded.csv` — rows with no email or only admin emails
5. Prints a markdown summary report

## Setup (Chromebook / GitHub Codespaces)

### Option A: GitHub Codespaces (Recommended — runs in your browser)
1. Open this repo on GitHub
2. Click the green **`<> Code`** button → **Codespaces** → **Create codespace on main**
3. Wait ~60 seconds for the environment to load
4. In the terminal that appears, run:
```bash
pip install -r requirements.txt
```
5. Copy your CSV into the codespace file explorer (drag and drop)
6. Add your Gemini API key to `.env` (see below)
7. Run:
```bash
python enrich.py --input your_file.csv --batch 50
```

### Option B: Google Colab
1. Go to [colab.research.google.com](https://colab.research.google.com)
2. Upload `enrich.py` and your CSV
3. In the first cell run: `!pip install -r requirements.txt`
4. In the next cell run: `!python enrich.py --input your_file.csv --batch 50`

## Get Your Free Gemini API Key
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API Key** → **Create API key**
3. Copy the key
4. Create a `.env` file in this repo:
```
GEMINI_API_KEY=your_key_here
```

## Input CSV Format
Your CSV must have at minimum a `Full Name` and `Company/Brand` column.
All original columns are preserved in the output.

## Output Files
| File | Contents |
|---|---|
| `Enriched.csv` | Rows where a personal/direct email was found |
| `Fallback_EmailNeeded.csv` | Rows with no email or only admin emails |
| Summary printed to terminal | Total, success rate, fallback count |

## Switching to OpenAI (Optional, ~$0.05–0.15 per 50 rows)
In `enrich.py`, change `LLM_PROVIDER = "gemini"` to `LLM_PROVIDER = "openai"` and add `OPENAI_API_KEY=your_key` to `.env`.

## Search Waterfall
The agent tries search engines in this order, exactly like OpenManus:
```
Google (free) → DuckDuckGo (free) → Baidu (free) → Bing (free)
```
No API keys needed for any of them.
