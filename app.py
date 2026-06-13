import streamlit as st
import csv
import io
import json
import os
import time

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="CDOD Enrichment Agent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .main { padding: 1rem 2rem; }
    .stProgress > div > div { background-color: #00c853; }
    .metric-box {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 1rem 1.5rem;
        text-align: center;
        border: 1px solid #333;
    }
    .log-box {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 1rem;
        font-family: monospace;
        font-size: 0.82rem;
        height: 320px;
        overflow-y: auto;
        color: #e6edf3;
    }
    .tag-success { color: #3fb950; font-weight: bold; }
    .tag-fallback { color: #d29922; font-weight: bold; }
    .tag-skip { color: #8b949e; font-weight: bold; }
    .tag-error { color: #f85149; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# IMPORTS FROM enrich.py (the brain)
# ─────────────────────────────────────────────
from enrich import (
    run_search_waterfall,
    extract_contact_data,
    is_personal_email,
    NEW_COLUMNS,
    ADMIN_PREFIXES,
)
import enrich as enrich_module

# ─────────────────────────────────────────────
# SIDEBAR — CONFIGURATION
# ─────────────────────────────────────────────
with st.sidebar:
    st.image("https://raw.githubusercontent.com/nowimhere3/CDODEnrichCSV/main/assets/logo.png", use_container_width=True) if False else None
    st.title("🧠 CDOD Enrichment")
    st.caption("Free contact enrichment powered by\nGoogle → DuckDuckGo → Baidu + Gemini")
    st.divider()

    st.subheader("🔑 API Key")
    llm_choice = st.radio(
        "LLM Provider",
        options=["gemini", "openai"],
        format_func=lambda x: "✨ Gemini Flash (FREE)" if x == "gemini" else "💰 GPT-4o-mini (~$0.15/50 rows)",
        index=0,
    )

    if llm_choice == "gemini":
        api_key = st.text_input(
            "Gemini API Key",
            type="password",
            placeholder="AIza...",
            help="Get free key at aistudio.google.com",
        )
        st.caption("[Get free key →](https://aistudio.google.com/apikey)")
    else:
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            placeholder="sk-...",
        )

    st.divider()
    st.subheader("⚙️ Batch Settings")
    batch_size = st.number_input("Rows per batch", min_value=1, max_value=200, value=50, step=10)
    start_row  = st.number_input("Start at row #", min_value=0, value=0, step=50,
                                  help="0 = first batch, 50 = second batch, etc.")

    st.divider()
    st.subheader("🔍 Search Waterfall")
    st.markdown("Google → DuckDuckGo → Baidu")
    st.caption("All free. No API keys needed for search.")
    search_pause = st.slider("Pause between rows (sec)", 1.0, 5.0, 2.0, 0.5,
                              help="Higher = slower but less likely to hit rate limits")

# ─────────────────────────────────────────────
# MAIN AREA
# ─────────────────────────────────────────────
st.title("🧠 CDOD Contact Enrichment Agent")
st.caption("Upload your CSV → Get enriched contacts with emails, phones, LinkedIn & more — free.")

# File upload
st.subheader("📁 Upload CSV")
uploaded_file = st.file_uploader(
    "Drop your coaches/contacts CSV here",
    type=["csv"],
    help="Must have at least 'Full Name' and 'Company/Brand' columns"
)

if uploaded_file:
    # Preview
    content = uploaded_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    all_rows = list(reader)
    fieldnames = list(reader.fieldnames or [])

    # Re-read for fieldnames
    reader2 = csv.DictReader(io.StringIO(content))
    fieldnames = list(reader2.fieldnames or [])
    all_rows = list(reader2)

    batch = all_rows[start_row : start_row + batch_size]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total rows in file", len(all_rows))
    col2.metric("This batch", len(batch))
    col3.metric("Start row", start_row + 1)

    with st.expander("👀 Preview first 5 rows", expanded=False):
        st.dataframe(
            [{k: v for k, v in row.items()} for row in all_rows[:5]],
            use_container_width=True
        )

    st.divider()

    # Validate before run
    ready = True
    if not api_key:
        st.warning(f"⚠️ Enter your {'Gemini' if llm_choice == 'gemini' else 'OpenAI'} API key in the sidebar.")
        ready = False
    if "Full Name" not in fieldnames and "full name" not in [f.lower() for f in fieldnames]:
        st.error("❌ CSV must have a 'Full Name' column.")
        ready = False
    if "Company/Brand" not in fieldnames and "company" not in [f.lower() for f in fieldnames]:
        st.warning("⚠️ No 'Company/Brand' column found — search quality may be lower.")

    if ready:
        run_btn = st.button("🚀 Run Enrichment", type="primary", use_container_width=True)
    else:
        run_btn = False
        st.button("🚀 Run Enrichment", disabled=True, use_container_width=True)

    # ─── RUN ───
    if run_btn:
        # Inject API key into environment for enrich.py brain
        os.environ["GEMINI_API_KEY" if llm_choice == "gemini" else "OPENAI_API_KEY"] = api_key
        enrich_module.LLM_PROVIDER = llm_choice

        enriched_rows = []
        fallback_rows = []
        log_lines = []

        st.divider()
        st.subheader("⚡ Running...")

        progress_bar = st.progress(0)
        status_text  = st.empty()
        log_area     = st.empty()

        col_e, col_f, col_r = st.columns(3)
        metric_enriched  = col_e.empty()
        metric_fallback  = col_f.empty()
        metric_rate      = col_r.empty()

        def render_log(lines):
            html = "<div class='log-box'>" + "<br>".join(lines[-60:]) + "</div>"
            log_area.markdown(html, unsafe_allow_html=True)

        def update_metrics():
            total = len(enriched_rows) + len(fallback_rows)
            rate  = (len(enriched_rows) / total * 100) if total > 0 else 0
            metric_enriched.metric("✅ Enriched",  len(enriched_rows))
            metric_fallback.metric("📋 Fallback",  len(fallback_rows))
            metric_rate.metric(    "🎯 Rate",      f"{rate:.0f}%")

        for i, row in enumerate(batch):
            full_name  = row.get("Full Name", "").strip()
            company    = row.get("Company/Brand", "").strip()
            flagship   = row.get("Their Baby", row.get("Flagship Offer", "")).strip()
            first_name = row.get("First Name", "").strip()

            pct = int((i / len(batch)) * 100)
            progress_bar.progress(pct)
            status_text.markdown(f"**[{i+1}/{len(batch)}]** Processing: `{full_name}`")

            # Skip aliases
            if first_name.startswith("(") or full_name.startswith("("):
                log_lines.append(f"<span class='tag-skip'>[{i+1}] ⏭ SKIP</span> {full_name} (alias)")
                row.update({col: "" for col in NEW_COLUMNS})
                fallback_rows.append(row)
                render_log(log_lines)
                update_metrics()
                continue

            log_lines.append(f"<span style='color:#58a6ff'>[{i+1}/{len(batch)}]</span> 🔍 {full_name} @ {company}")
            render_log(log_lines)

            # Search
            query = f'"{full_name}" {company} email website LinkedIn contact'
            search_results = run_search_waterfall(query)

            if search_results:
                log_lines.append(f"&nbsp;&nbsp;→ Search ✓ ({len(search_results.splitlines())} results)")
            else:
                log_lines.append(f"&nbsp;&nbsp;→ <span class='tag-error'>Search failed</span>")

            # Extract
            contact = extract_contact_data(full_name, company, flagship, search_results)

            row["Website"]  = contact.get("website", "")
            row["Email"]    = contact.get("email", "")
            row["Phone"]    = contact.get("phone", "")
            row["Address"]  = contact.get("address", "")
            row["LinkedIn"] = contact.get("linkedin", "")
            row["Other"]    = contact.get("other", "")

            email = contact.get("email", "")
            if is_personal_email(email, full_name):
                log_lines.append(f"&nbsp;&nbsp;<span class='tag-success'>✅ EMAIL: {email}</span>")
                enriched_rows.append(row)
            else:
                reason = f"admin: {email}" if email else "no email"
                log_lines.append(f"&nbsp;&nbsp;<span class='tag-fallback'>📋 FALLBACK ({reason})</span>")
                fallback_rows.append(row)

            render_log(log_lines)
            update_metrics()

            if i < len(batch) - 1:
                time.sleep(search_pause)

        # Done
        progress_bar.progress(100)
        status_text.markdown("✅ **Complete!**")
        update_metrics()

        total   = len(enriched_rows) + len(fallback_rows)
        rate    = (len(enriched_rows) / total * 100) if total > 0 else 0
        log_lines.append("─" * 40)
        log_lines.append(f"<span class='tag-success'>DONE — {len(enriched_rows)}/{total} enriched ({rate:.0f}%)</span>")
        render_log(log_lines)

        # ─── OUTPUT FILES ───
        st.divider()
        st.subheader("⬇️ Download Results")

        out_fields = fieldnames + [c for c in NEW_COLUMNS if c not in fieldnames]
        batch_label = f"rows{start_row+1}-{start_row+len(batch)}"

        def rows_to_csv_bytes(rows):
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=out_fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            return buf.getvalue().encode("utf-8")

        dc1, dc2 = st.columns(2)

        with dc1:
            st.download_button(
                label=f"⬇️ Enriched.csv  ({len(enriched_rows)} rows)",
                data=rows_to_csv_bytes(enriched_rows),
                file_name=f"Enriched_{batch_label}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )
            if enriched_rows:
                st.dataframe(enriched_rows[:5], use_container_width=True)

        with dc2:
            st.download_button(
                label=f"⬇️ Fallback.csv  ({len(fallback_rows)} rows)",
                data=rows_to_csv_bytes(fallback_rows),
                file_name=f"Fallback_EmailNeeded_{batch_label}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            if fallback_rows:
                st.dataframe(fallback_rows[:5], use_container_width=True)

        # Summary
        st.divider()
        st.subheader("📊 Summary")
        st.markdown(f"""
| Metric | Count |
|--------|-------|
| Total processed | {total} |
| ✅ Enriched (personal email) | {len(enriched_rows)} |
| 📋 Fallback (no/admin email) | {len(fallback_rows)} |
| 🎯 Success rate | {rate:.1f}% |
| LLM used | {llm_choice} |
| Search waterfall | Google → DuckDuckGo → Baidu |
        """)

else:
    # Landing state
    st.info("👈 Configure your API key in the sidebar, then upload a CSV above to get started.")

    st.subheader("How it works")
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown("**1️⃣ Upload**\n\nDrop your CSV with coach/contact names")
    col2.markdown("**2️⃣ Search**\n\nFree waterfall:\nGoogle → DDG → Baidu")
    col3.markdown("**3️⃣ Extract**\n\nGemini Flash reads results & pulls email, phone, LinkedIn, address")
    col4.markdown("**4️⃣ Download**\n\nTwo CSVs:\nEnriched + Fallback")

    st.divider()
    st.subheader("Required CSV columns")
    st.markdown("""
    | Column | Required | Notes |
    |--------|----------|-------|
    | `Full Name` | ✅ Yes | Used for search |
    | `Company/Brand` | ✅ Yes | Improves search accuracy |
    | `Their Baby` | Optional | Flagship offer / main product |
    | `First Name` | Optional | Used to detect aliases |
    | Everything else | Optional | All columns preserved in output |
    """)
