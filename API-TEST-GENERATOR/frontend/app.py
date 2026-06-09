"""
AI-Powered API Test Generator — Streamlit Frontend
Provides a modern UI for uploading OpenAPI specs, viewing parsed endpoints,
generating Pytest tests via AI, and downloading individual files or ZIP bundles.
"""

import io
import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="API Test Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# Custom CSS — dark developer aesthetic
# Terminal-inspired with syntax-highlight accents
# ─────────────────────────────────────────────

st.markdown("""
<style>
  /* ── Global ── */
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap');

  :root {
    --bg-base:     #0d1b2a;
    --bg-surface:  #1b2838;
    --bg-raised:   #233142;
    --border:      #2d3e50;
    --accent:      #4cc9f0;
    --accent-dim:  #1a4a5e;
    --green:       #4ade80;
    --orange:      #f59e0b;
    --red:         #f87171;
    --text-primary:#e2e8f0;
    --text-muted:  #94a3b8;
    --mono:        'JetBrains Mono', monospace;
    --sans:        'Inter', sans-serif;
  }

  html, body, [data-testid="stApp"] {
    background: var(--bg-base) !important;
    color: var(--text-primary) !important;
    font-family: var(--sans) !important;
  }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
  }
  [data-testid="stSidebar"] * { color: var(--text-primary) !important; }

  /* ── Main header ── */
  .hero-banner {
    background: linear-gradient(135deg, #0d1b2a 0%, #1b2838 50%, #0d1b2a 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 36px 40px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
  }
  .hero-banner::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--green), var(--accent));
  }
  .hero-title {
    font-family: var(--mono) !important;
    font-size: 2rem !important;
    font-weight: 600 !important;
    color: var(--accent) !important;
    letter-spacing: -0.5px;
    margin: 0 0 8px 0;
  }
  .hero-sub {
    font-size: 1rem;
    color: var(--text-muted);
    margin: 0;
    font-family: var(--sans);
  }
  .hero-badge {
    display: inline-block;
    background: var(--accent-dim);
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 20px;
    padding: 2px 12px;
    font-family: var(--mono);
    font-size: 0.72rem;
    margin-top: 12px;
    letter-spacing: 0.5px;
  }

  /* ── Step cards ── */
  .step-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }
  .step-label {
    font-family: var(--mono);
    font-size: 0.7rem;
    color: var(--accent);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  .step-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0;
  }

  /* ── Metric tiles ── */
  .metric-row {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .metric-tile {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 20px;
    flex: 1;
    min-width: 120px;
  }
  .metric-value {
    font-family: var(--mono);
    font-size: 1.8rem;
    font-weight: 600;
    color: var(--accent);
    line-height: 1;
  }
  .metric-label {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-top: 4px;
  }

  /* ── Status badges ── */
  .badge {
    display: inline-block;
    border-radius: 4px;
    padding: 2px 8px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 600;
  }
  .badge-get    { background: #0d3a2e; color: var(--green); border: 1px solid var(--green); }
  .badge-post   { background: #1a2e0d; color: #7ee787; border: 1px solid #7ee787; }
  .badge-put    { background: #2e1f0d; color: var(--orange); border: 1px solid var(--orange); }
  .badge-patch  { background: #2a1a0d; color: #f0883e; border: 1px solid #f0883e; }
  .badge-delete { background: #2e0d0d; color: var(--red); border: 1px solid var(--red); }

  /* ── File pills ── */
  .file-pill {
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 14px;
    margin: 4px 0;
    font-family: var(--mono);
    font-size: 0.82rem;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  /* ── Streamlit overrides ── */
  .stButton > button {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    border-radius: 6px !important;
    font-family: var(--mono) !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 20px !important;
    transition: all 0.15s !important;
  }
  .stButton > button:hover {
    background: var(--accent) !important;
    color: #0d1117 !important;
    transform: translateY(-1px);
  }
  .stDownloadButton > button {
    background: #0d3a2e !important;
    color: var(--green) !important;
    border: 1px solid var(--green) !important;
    border-radius: 6px !important;
    font-family: var(--mono) !important;
    font-size: 0.82rem !important;
  }
  .stDownloadButton > button:hover {
    background: var(--green) !important;
    color: #0d1117 !important;
  }
  .stFileUploader {
    border: 1px dashed var(--border) !important;
    border-radius: 8px !important;
    background: var(--bg-surface) !important;
  }
  [data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
  }
  .stAlert {
    border-radius: 8px !important;
    font-family: var(--mono) !important;
    font-size: 0.85rem !important;
  }
  div[data-testid="stExpander"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
  }
  .stTabs [data-baseweb="tab"] {
    font-family: var(--mono) !important;
    font-size: 0.82rem !important;
    color: var(--text-muted) !important;
  }
  .stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom-color: var(--accent) !important;
  }

  /* ── Code blocks ── */
  pre, code {
    font-family: var(--mono) !important;
    background: var(--bg-base) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg-base); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────

defaults = {
    "spec_id": None,
    "endpoints": [],
    "generated_files": [],
    "total_tests": 0,
    "upload_done": False,
    "generate_done": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────

def backend_healthy() -> bool:
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def method_badge(method: str) -> str:
    m = method.upper()
    cls = {
        "GET": "badge-get", "POST": "badge-post",
        "PUT": "badge-put", "PATCH": "badge-patch",
        "DELETE": "badge-delete"
    }.get(m, "badge-get")
    return f'<span class="badge {cls}">{m}</span>'


def endpoints_to_dataframe(endpoints: list[dict]) -> pd.DataFrame:
    """Convert endpoint list to a display-friendly DataFrame."""
    rows = []
    for ep in endpoints:
        params = ep.get("parameters", [])
        path_params  = [p["name"] for p in params if p["location"] == "path"]
        query_params = [p["name"] for p in params if p["location"] == "query"]
        has_body = "✓" if ep.get("request_body") else "—"
        success_codes = [
            r["status_code"] for r in ep.get("responses", [])
            if str(r["status_code"]).startswith("2")
        ]
        rows.append({
            "Method":       ep.get("method", ""),
            "Path":         ep.get("path", ""),
            "Summary":      ep.get("summary") or ep.get("operation_id") or "—",
            "Path Params":  ", ".join(path_params) if path_params else "—",
            "Query Params": ", ".join(query_params) if query_params else "—",
            "Request Body": has_body,
            "Success Codes": ", ".join(success_codes) if success_codes else "—",
            "Tags":         ", ".join(ep.get("tags", [])) or "—",
        })
    return pd.DataFrame(rows)

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🧪 API Test Generator")
    st.markdown("---")

    # Backend health indicator
    is_healthy = backend_healthy()
    status_color = "#3fb950" if is_healthy else "#f85149"
    status_text  = "Backend Online" if is_healthy else "Backend Offline"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:{status_color};'
        f'box-shadow:0 0 6px {status_color};"></div>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
        f'color:{status_color};">{status_text}</span></div>',
        unsafe_allow_html=True
    )

    if not is_healthy:
        st.warning("Start the backend:\n```\nuvicorn backend.main:app --reload\n```")

    st.markdown("---")

    # Workflow guide
    st.markdown("**Workflow**")
    steps = [
        ("1", "Upload OpenAPI spec"),
        ("2", "Review parsed endpoints"),
        ("3", "Generate AI tests"),
        ("4", "Download test files"),
    ]
    for num, label in steps:
        st.markdown(
            f'<div style="display:flex;gap:10px;align-items:center;padding:6px 0;">'
            f'<div style="background:#1f4a8a;color:#58a6ff;border-radius:4px;'
            f'width:20px;height:20px;display:flex;align-items:center;justify-content:center;'
            f'font-size:0.7rem;font-family:\'JetBrains Mono\',monospace;flex-shrink:0;">{num}</div>'
            f'<span style="font-size:0.85rem;color:#8b949e;">{label}</span></div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Current state summary
    if st.session_state.spec_id:
        st.markdown("**Current Spec**")
        st.code(st.session_state.spec_id, language=None)
    if st.session_state.endpoints:
        st.metric("Endpoints Found", len(st.session_state.endpoints))
    if st.session_state.generate_done:
        st.metric("Tests Generated", st.session_state.total_tests)

    st.markdown("---")
    if st.button("🔄 Reset Session", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

    st.markdown(
        '<p style="font-size:0.7rem;color:#484f58;margin-top:16px;font-family:'
        '\'JetBrains Mono\',monospace;">Powered by Gemini 1.5 Flash</p>',
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
# Main content
# ─────────────────────────────────────────────

# Hero banner
st.markdown("""
<div class="hero-banner">
  <div class="hero-title">⚡ AI-Powered API Test Generator</div>
  <p class="hero-sub">
    Upload an OpenAPI specification → AI generates production-ready Pytest test suites in seconds.
  </p>
  <span class="hero-badge">GEMINI 1.5 FLASH · PYTEST · OPENAPI 3.x</span>
</div>
""", unsafe_allow_html=True)

# Main tabs
tab_upload, tab_endpoints, tab_generate, tab_download = st.tabs([
    "📁  Upload Spec",
    "🗂  Endpoints",
    "⚙️  Generate Tests",
    "💾  Download",
])

# ══════════════════════════════════════════════
# TAB 1 — Upload
# ══════════════════════════════════════════════

with tab_upload:
    st.markdown('<div class="step-card"><div class="step-label">Step 01</div>'
                '<div class="step-title">Upload your OpenAPI Specification</div></div>',
                unsafe_allow_html=True)

    col_upload, col_info = st.columns([3, 2], gap="large")

    with col_upload:
        uploaded_file = st.file_uploader(
            "Drop a `.yaml`, `.yml`, or `.json` OpenAPI file",
            type=["yaml", "yml", "json"],
            help="Supports OpenAPI 3.x specifications in YAML or JSON format.",
            label_visibility="collapsed"
        )

        if uploaded_file is not None:
            file_size_kb = len(uploaded_file.getvalue()) / 1024
            st.markdown(
                f'<div class="file-pill">📄 <strong>{uploaded_file.name}</strong>'
                f' &nbsp;·&nbsp; {file_size_kb:.1f} KB'
                f' &nbsp;·&nbsp; {uploaded_file.type or "text/plain"}</div>',
                unsafe_allow_html=True
            )

            if st.button("🚀 Parse Specification", use_container_width=True):
                if not is_healthy:
                    st.error("Backend is offline. Please start the FastAPI server first.")
                else:
                    with st.spinner("Sending to backend and parsing spec..."):
                        try:
                            files = {"file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type or "application/octet-stream"
                            )}
                            response = requests.post(
                                f"{BACKEND_URL}/upload-spec",
                                files=files,
                                timeout=30
                            )

                            if response.status_code == 200:
                                data = response.json()
                                st.session_state.spec_id = data["spec_id"]
                                st.session_state.endpoints = data["endpoints"]
                                st.session_state.upload_done = True
                                st.session_state.generate_done = False
                                st.session_state.generated_files = []
                                st.success(
                                    f"✅ Parsed **{data['total_endpoints']}** endpoints "
                                    f"from `{data['spec_id']}`"
                                )
                                st.info("→ Switch to the **Endpoints** tab to review parsed data.")
                            else:
                                detail = response.json().get("detail", response.text)
                                st.error(f"Parse failed ({response.status_code}): {detail}")

                        except requests.exceptions.ConnectionError:
                            st.error("Cannot connect to backend. Is FastAPI running on port 8000?")
                        except Exception as e:
                            st.error(f"Unexpected error: {e}")

    with col_info:
        st.markdown("**What gets extracted:**")
        items = [
            ("🔗", "Paths & HTTP methods"),
            ("📋", "Parameters (path, query, header)"),
            ("📦", "Request body schemas"),
            ("✅", "Response schemas & status codes"),
            ("🏷", "Tags & operation IDs"),
            ("🔒", "Security requirements"),
        ]
        for icon, text in items:
            st.markdown(
                f'<div style="display:flex;gap:10px;align-items:center;padding:5px 0;">'
                f'<span>{icon}</span>'
                f'<span style="font-size:0.88rem;color:#8b949e;">{text}</span></div>',
                unsafe_allow_html=True
            )

        st.markdown("---")
        st.markdown("**Supported formats:**")
        for fmt in ["OpenAPI 3.0.x (YAML)", "OpenAPI 3.1.x (YAML)", "Swagger JSON (3.x)"]:
            st.markdown(f"- {fmt}")

# ══════════════════════════════════════════════
# TAB 2 — Endpoints
# ══════════════════════════════════════════════

with tab_endpoints:
    st.markdown('<div class="step-card"><div class="step-label">Step 02</div>'
                '<div class="step-title">Review Parsed Endpoints</div></div>',
                unsafe_allow_html=True)

    if not st.session_state.upload_done or not st.session_state.endpoints:
        st.info("Upload and parse a specification first to see endpoints here.")
    else:
        eps = st.session_state.endpoints

        # Summary metrics
        methods = [ep.get("method", "") for ep in eps]
        method_counts = {m: methods.count(m) for m in set(methods)}

        cols = st.columns(min(len(method_counts) + 1, 6))
        with cols[0]:
            st.metric("Total Endpoints", len(eps))
        for i, (method, count) in enumerate(sorted(method_counts.items()), 1):
            if i < len(cols):
                with cols[i]:
                    st.metric(f"{method}", count)

        st.markdown("---")

        # Endpoint table
        df = endpoints_to_dataframe(eps)
        st.dataframe(
            df,
            use_container_width=True,
            height=min(len(eps) * 38 + 50, 500),
            hide_index=True,
            column_config={
                "Method": st.column_config.TextColumn("Method", width=80),
                "Path": st.column_config.TextColumn("Path", width=200),
                "Summary": st.column_config.TextColumn("Summary", width=200),
                "Path Params": st.column_config.TextColumn("Path Params", width=120),
                "Query Params": st.column_config.TextColumn("Query Params", width=120),
                "Request Body": st.column_config.TextColumn("Body", width=60),
                "Success Codes": st.column_config.TextColumn("2xx Codes", width=100),
            }
        )

        # Detailed endpoint inspector
        st.markdown("#### 🔍 Endpoint Inspector")
        ep_options = [
            f"{ep['method']} {ep['path']}" for ep in eps
        ]
        selected = st.selectbox("Select endpoint to inspect:", ep_options)
        if selected:
            idx = ep_options.index(selected)
            ep_detail = eps[idx]
            with st.expander("Full endpoint details", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.json({
                        "path": ep_detail.get("path"),
                        "method": ep_detail.get("method"),
                        "operation_id": ep_detail.get("operation_id"),
                        "summary": ep_detail.get("summary"),
                        "tags": ep_detail.get("tags"),
                        "security": ep_detail.get("security"),
                    })
                with c2:
                    st.json({
                        "parameters": ep_detail.get("parameters"),
                        "request_body": ep_detail.get("request_body"),
                        "responses": ep_detail.get("responses"),
                    })

# ══════════════════════════════════════════════
# TAB 3 — Generate Tests
# ══════════════════════════════════════════════

with tab_generate:
    st.markdown('<div class="step-card"><div class="step-label">Step 03</div>'
                '<div class="step-title">Generate AI-Powered Pytest Tests</div></div>',
                unsafe_allow_html=True)

    if not st.session_state.upload_done:
        st.info("Complete Step 01 (upload a spec) before generating tests.")
    else:
        col_gen, col_what = st.columns([3, 2], gap="large")

        with col_gen:
            n_endpoints = len(st.session_state.endpoints)
            st.markdown(
                f'<div class="metric-tile" style="margin-bottom:16px;">'
                f'<div class="metric-value">{n_endpoints}</div>'
                f'<div class="metric-label">endpoints ready to test</div></div>',
                unsafe_allow_html=True
            )

            st.markdown(
                "Gemini 1.5 Flash will analyze each endpoint and generate comprehensive "
                "test cases covering all key scenarios."
            )

            if st.button("⚡ Generate All Tests", use_container_width=True, type="primary"):
                if not is_healthy:
                    st.error("Backend is offline.")
                else:
                    progress_bar = st.progress(0, text="Initializing generation...")
                    status_area = st.empty()

                    try:
                        status_area.info(
                            f"🤖 Generating tests for {n_endpoints} endpoints via Gemini... "
                            "This may take a minute."
                        )
                        progress_bar.progress(20, text="Sending request to backend...")

                        response = requests.post(
                            f"{BACKEND_URL}/generate-tests",
                            json={"spec_id": st.session_state.spec_id},
                            timeout=300  # Allow up to 5 minutes for large specs
                        )

                        progress_bar.progress(90, text="Finalizing test files...")

                        if response.status_code == 200:
                            data = response.json()
                            st.session_state.generated_files = data["test_files"]
                            st.session_state.total_tests = data["total_tests_generated"]
                            st.session_state.generate_done = True

                            progress_bar.progress(100, text="Done!")
                            status_area.success(
                                f"✅ {data['message']}"
                            )
                            st.info("→ Switch to the **Download** tab to get your test files.")
                        else:
                            detail = response.json().get("detail", response.text)
                            progress_bar.empty()
                            status_area.error(f"Generation failed ({response.status_code}): {detail}")

                    except requests.exceptions.Timeout:
                        progress_bar.empty()
                        status_area.error(
                            "Request timed out. The spec may be very large. "
                            "Try with a smaller spec."
                        )
                    except Exception as e:
                        progress_bar.empty()
                        status_area.error(f"Unexpected error: {e}")

            if st.session_state.generate_done:
                st.markdown("---")
                st.markdown("**Generated files:**")
                for fname in st.session_state.generated_files:
                    st.markdown(
                        f'<div class="file-pill">🐍 {fname}</div>',
                        unsafe_allow_html=True
                    )

        with col_what:
            st.markdown("**What Gemini generates:**")
            test_types = [
                ("✅", "Positive tests", "Happy path with valid data"),
                ("❌", "Negative tests", "Missing fields, wrong method"),
                ("⚠️", "Boundary tests", "Edge values, empty strings"),
                ("🔢", "Type tests", "Wrong data types per field"),
                ("📊", "Status code tests", "Exact HTTP code validation"),
                ("📋", "Schema tests", "Response field presence"),
            ]
            for icon, name, desc in test_types:
                st.markdown(
                    f'<div style="padding:8px 0;border-bottom:1px solid #30363d;">'
                    f'<div style="display:flex;gap:8px;align-items:center;">'
                    f'<span>{icon}</span>'
                    f'<span style="font-size:0.9rem;font-weight:600;color:#e6edf3;">{name}</span>'
                    f'</div>'
                    f'<div style="font-size:0.78rem;color:#8b949e;margin-left:24px;">{desc}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

# ══════════════════════════════════════════════
# TAB 4 — Download
# ══════════════════════════════════════════════

with tab_download:
    st.markdown('<div class="step-card"><div class="step-label">Step 04</div>'
                '<div class="step-title">Download Generated Test Files</div></div>',
                unsafe_allow_html=True)

    if not st.session_state.generate_done:
        st.info("Complete Step 03 (generate tests) before downloading.")
    else:
        files = st.session_state.generated_files
        spec_id = st.session_state.spec_id

        # Stats row
        st.markdown(
            f'<div class="metric-row">'
            f'<div class="metric-tile">'
            f'<div class="metric-value">{st.session_state.total_tests}</div>'
            f'<div class="metric-label">total tests</div></div>'
            f'<div class="metric-tile">'
            f'<div class="metric-value">{len(files)}</div>'
            f'<div class="metric-label">test files</div></div>'
            f'<div class="metric-tile">'
            f'<div class="metric-value">{spec_id}</div>'
            f'<div class="metric-label">spec id</div></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ZIP download (primary CTA)
        col_zip, col_space = st.columns([2, 3])
        with col_zip:
            if st.button("📦 Download Complete Test Suite (ZIP)", use_container_width=True):
                with st.spinner("Building ZIP archive..."):
                    try:
                        zip_response = requests.get(
                            f"{BACKEND_URL}/download-zip/{spec_id}",
                            timeout=30
                        )
                        if zip_response.status_code == 200:
                            st.download_button(
                                label="⬇️ Save ZIP File",
                                data=zip_response.content,
                                file_name=f"{spec_id}_tests.zip",
                                mime="application/zip",
                                use_container_width=True
                            )
                        else:
                            detail = zip_response.json().get("detail", zip_response.text)
                            st.error(f"ZIP creation failed: {detail}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.markdown("---")
        st.markdown("#### 📄 Individual Files")
        st.markdown("Preview and download each test file separately:")

        # Individual file download section
        for filename in files:
            with st.expander(f"🐍 {filename}"):
                # Fetch file content for preview
                try:
                    file_response = requests.get(
                        f"{BACKEND_URL}/download/{filename}",
                        timeout=15
                    )
                    if file_response.status_code == 200:
                        code_content = file_response.text

                        # Show first 80 lines as preview
                        lines = code_content.split("\n")
                        preview_lines = min(80, len(lines))
                        preview = "\n".join(lines[:preview_lines])
                        if len(lines) > preview_lines:
                            preview += f"\n\n# ... ({len(lines) - preview_lines} more lines)"

                        st.code(preview, language="python")

                        st.download_button(
                            label=f"⬇️ Download {filename}",
                            data=code_content,
                            file_name=filename,
                            mime="text/x-python",
                            key=f"dl_{filename}"
                        )
                    else:
                        st.error(f"Could not load file: {file_response.status_code}")
                except Exception as e:
                    st.warning(f"Preview unavailable: {e}")
                    # Offer a download link without preview
                    st.markdown(
                        f"[Download via backend]({BACKEND_URL}/download/{filename})"
                    )

        st.markdown("---")
        st.markdown("#### 🚀 Run Your Tests")
        st.markdown("After downloading, run your tests with:")
        st.code("""# Install test dependencies
pip install pytest requests

# Run all tests
pytest tests/ -v

# Run with HTML report
pip install pytest-html
pytest tests/ -v --html=report.html

# Run only GET endpoint tests (example)
pytest tests/ -k "get" -v
""", language="bash")
