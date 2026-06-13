# 🧠 CDOD Enrichment Agent

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cdodenrichcsv.streamlit.app)

Free contact enrichment for coaching/crypto leads. Upload a CSV → get back enriched contacts with emails, phones, LinkedIn, addresses — all free.

## 🚀 Live App

**[→ Open the web app](https://cdodenrichcsv.streamlit.app)**

Works in any browser including Chromebook. No install needed.

---

## Cost
- **Search:** $0.00 — Google → DuckDuckGo → Baidu, all free libraries, no API keys
- **LLM:** $0.00 — Gemini 1.5 Flash free tier (15 req/min, 1M tokens/day)
- **50 rows:** ~$0.00 (Gemini) or $0.05–0.15 max (GPT-4o-mini)

---

## What It Does
1. Reads your CSV row by row
2. Searches the web using the free waterfall: **Google → DuckDuckGo → Baidu**
3. Sends results to Gemini Flash (free) to extract structured contact data
4. Splits output into:
   - `Enriched.csv` — rows where a valid personal email was found
   - `Fallback_EmailNeeded.csv` — rows with no email or only admin emails
5. Shows live progress log + download buttons

---

## Deploy Your Own (Free)

### Option A — Streamlit Community Cloud (Recommended)
1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select your fork → set main file to `app.py`
4. Add your Gemini key as a secret: `GEMINI_API_KEY = "your_key"`
5. Click **Deploy** — you get a free public URL

### Option B — GitHub Codespaces (Terminal)
1. Open this repo → Code → Codespaces → Create codespace
2. In terminal:
```bash
echo "GEMINI_API_KEY=your_key" > .env
pip install -r requirements.txt
streamlit run app.py
```
3. Click the forwarded port URL that appears

### Option C — Command Line
```bash
python enrich.py --input your_file.csv --batch 50
python enrich.py --input your_file.csv --batch 50 --start 50  # next batch
```

---

## Required CSV Columns

| Column | Required | Notes |
|--------|----------|-------|
| `Full Name` | ✅ Yes | Used for search |
| `Company/Brand` | ✅ Yes | Improves search accuracy |
| `Their Baby` | Optional | Flagship offer / product |
| `First Name` | Optional | Used to detect aliases |

All original columns are preserved in the output.

---

## Get Your Free Gemini API Key
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API key**
3. Paste it in the sidebar of the web app (never stored, never committed)

---

## Search Waterfall
Exactly mirrors how OpenManus handles web research:
```
Google (free) → DuckDuckGo (free) → Baidu (free)
```
No API keys needed for any search engine.
