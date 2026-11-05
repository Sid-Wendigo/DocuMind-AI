import os
import tempfile
from datetime import datetime

import streamlit as st

# Load API credentials from the SAME folder as this app.py file.
# Install python-dotenv with: pip install python-dotenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
try:
    from dotenv import load_dotenv
    # override=True makes the project's .env value take priority over a stale
    # GEMINI_API_KEY left in the terminal's environment.
    load_dotenv(dotenv_path=ENV_PATH, override=True)
except ImportError:
    # Environment variables and Streamlit secrets still work without dotenv.
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError


# -----------------------------------------------------------------------------
# Configuration
# Set GEMINI_API_KEY in a .env file beside app.py, in your environment,
# or in .streamlit/secrets.toml. Example .env entry:
# GEMINI_API_KEY=your_new_key_here
# -----------------------------------------------------------------------------
def get_api_key():
    """Read the key from .env / environment first, then Streamlit secrets."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        try:
            key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        except Exception:
            key = ""

    # Catch common setup mistakes before making a request to Google.
    if key.lower() in {"your_api_key_here", "your_new_key_here", "paste_your_key_here"}:
        return ""
    return key


API_KEY = get_api_key()

CITATION_POLICY = """
SOURCE AND CITATION RULES — FOLLOW THESE FOR EVERY ANSWER:
1. Base document-specific answers only on the uploaded PDF. Do not fill gaps with guesses.
2. Add an inline source citation to every important factual claim drawn from the PDF, in this format:
   [Source: PDF p. 12, section 'Methodology']
   If the section heading is not clear, use [Source: PDF p. 12].
3. Use the page number as it appears in the PDF viewer (counting the first PDF page as page 1). If a printed page number is also visible and differs, show both, e.g. [PDF p. 14; printed p. 10].
4. Never invent page numbers, section names, quotations, statistics, or citations. If you cannot confidently locate a claim, say: 'I couldn't verify the exact page in the PDF.'
5. For important claims, include a short supporting quotation when useful. Keep quotations brief and exact.
6. End substantial answers with a compact 'Sources in the PDF' section listing the cited pages and what each page supports. Avoid repeating the same citation unnecessarily.
7. Distinguish clearly between 'What the PDF says' and your own explanation or interpretation. Label interpretations as 'Explanation' or 'My interpretation'.
8. If the PDF does not contain the answer, say so plainly. Do not present outside knowledge as if it came from the PDF.
9. Write in readable Markdown: descriptive headings, short paragraphs, bullets, numbered steps, and tables only when they genuinely improve clarity.
"""

PERSONAS = {
    "Guided Learning": {
        "icon": "🎓",
        "tagline": "Understand it, one step at a time",
        "description": "A patient tutor who turns difficult ideas into clear explanations and examples.",
        "instruction": """
You are a friendly, patient tutor. Your job is to help the reader genuinely understand the uploaded PDF.
- Start with a one- or two-sentence plain-English answer.
- Explain ideas in small steps, in the order a beginner can follow.
- Use simple examples or everyday comparisons when they help.
- Explain every necessary technical term immediately in ordinary language.
- Use headings such as 'Simple explanation', 'Step by step', and 'Example' when useful.
- Finish longer explanations with a short 'Remember this' recap.
- End with one friendly question to check understanding, but do not force a question when the user asks for a direct fact.
- Keep the tone encouraging, never childish or condescending.
""",
    },
    "Executive Summary": {
        "icon": "📌",
        "tagline": "The important points, without the noise",
        "description": "A concise briefing with key findings, implications, and practical next steps.",
        "instruction": """
You are a practical analyst preparing a clear briefing for a busy decision-maker.
- Lead with the main takeaway in plain language.
- Use the headings 'Overview', 'Key Findings', 'Why It Matters', and 'Recommended Actions' when relevant.
- Prefer concise bullets and short sentences. Avoid jargon, buzzwords, and inflated business language.
- Explain metrics in everyday terms and preserve their units and context.
- Separate facts stated in the PDF from analysis or recommendations.
- Use a compact table only when comparing multiple items makes the answer easier to scan.
- Do not add filler or make recommendations unsupported by the document.
""",
    },
    "Deep Research": {
        "icon": "🔎",
        "tagline": "Follow the evidence all the way through",
        "description": "A careful document investigation with evidence, page references, gaps, and contradictions.",
        "instruction": """
You are a meticulous research assistant. Be thorough, but make the result easy to navigate.
- Begin with a direct answer or a short research summary.
- Organize complex answers with headings such as 'Question', 'What the PDF says', 'Evidence', 'Analysis', and 'Limitations'.
- Support each important claim with exact page references and brief quotations where useful.
- Compare relevant passages when the document contains differing claims or contradictions.
- Identify missing evidence, unclear wording, assumptions, and unsupported premises.
- Clearly distinguish direct evidence from your own interpretation.
- Do not use dense academic language unless the user explicitly asks for it; explain specialist terms briefly.
""",
    },
}

QUICK_PROMPTS = {
    "Guided Learning": [
        "Explain the main idea of this PDF in simple words.",
        "Teach me the most important concepts step by step.",
        "Give me a real-life example of the key concept.",
        "Create 5 questions to test my understanding.",
    ],
    "Executive Summary": [
        "Give me a one-page summary of this document.",
        "What are the 5 most important findings?",
        "What actions or decisions does this document recommend?",
        "Show me the key numbers and what they mean.",
    ],
    "Deep Research": [
        "Find the strongest evidence for the document's main argument.",
        "Identify contradictions, limitations, or missing information.",
        "Trace this topic through the PDF and cite every relevant page.",
        "Extract the key claims with supporting quotations and page numbers.",
    ],
}


# -----------------------------------------------------------------------------
# Premium interface styling
# -----------------------------------------------------------------------------
def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&family=Playfair+Display:wght@500;600;700&display=swap');
        :root {
            --ink:#1f2a25; --muted:#68736b; --paper:#f4f2ec; --surface:#fffefa;
            --forest:#193b2d; --forest2:#28513e; --gold:#c29a5b; --line:#deded2;
        }
        html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
        .stApp {
            background: radial-gradient(circle at 85% 3%,rgba(194,154,91,.13),transparent 25%),
                        radial-gradient(circle at 8% 60%,rgba(40,81,62,.08),transparent 28%),
                        linear-gradient(135deg,#f6f4ee 0%,#eeece4 100%);
            color:var(--ink);
        }
        [data-testid="stHeader"] { background:rgba(246,244,238,.72); }
        .block-container { max-width:1280px; padding-top:1.35rem; padding-bottom:4rem; }
        h1,h2,h3 { color:var(--forest)!important; font-family:'Manrope',sans-serif!important; letter-spacing:-.035em; }
        p,li { color:var(--ink); line-height:1.72; }
        .topbar { display:flex; justify-content:space-between; align-items:center; gap:1rem;
                  padding:.35rem 0 1.1rem; border-bottom:1px solid var(--line); margin-bottom:1.8rem; }
        .brand { display:flex; align-items:center; gap:.7rem; font:800 .88rem 'Manrope',sans-serif;
                 letter-spacing:.16em; color:var(--forest); }
        .brand-mark { display:grid; place-items:center; width:34px;height:34px;border-radius:11px;
                      background:linear-gradient(145deg,#244d39,#142f23);color:#f4dfb6;
                      box-shadow:0 5px 14px #193b2d30;font:700 1rem 'Playfair Display',serif; }
        .top-pill { border:1px solid #d8d6ca; border-radius:999px; padding:.42rem .8rem;
                    color:#637067; background:#ffffff8c; font-size:.72rem; letter-spacing:.04em; }
        .hero-kicker { color:#8c7043; font-size:.68rem; font-weight:800; letter-spacing:.2em;
                       text-transform:uppercase; margin-bottom:.55rem; }
        .hero-title { font:600 clamp(2.1rem,5vw,3.55rem)/1.08 'Playfair Display',serif;
                      letter-spacing:-.04em; color:#18382b; margin:0 0 .65rem; }
        .hero-copy { max-width:720px; color:#68736b; font-size:1rem; line-height:1.7; }
        .hero-line { width:58px;height:3px;background:linear-gradient(90deg,#c29a5b,#e4d2ad);margin:1.15rem 0 1.65rem;border-radius:4px; }
        .welcome-card { padding:2rem 2.2rem; border-radius:22px; color:#f6f2e8;
                        background:radial-gradient(circle at 90% 10%,#ffffff20,transparent 25%),
                        linear-gradient(125deg,#17382a,#2d5942); border:1px solid #c29a5b80;
                        box-shadow:0 20px 50px #203d2c18; }
        .welcome-card h2 { color:#fff8e9!important; font:600 1.9rem 'Playfair Display',serif!important; }
        .welcome-card p { color:#e7e9df!important; max-width:680px; }
        .mini-label { color:#d7b77e; text-transform:uppercase; letter-spacing:.18em; font-size:.65rem; font-weight:800; }
        [data-testid="stSidebar"] { background:linear-gradient(165deg,#142c21,#203d2e 70%,#294a38); border-right:1px solid #c29a5b55; }
        [data-testid="stSidebar"] * { color:#f0eee5; }
        [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 { color:#f4e9d4!important; }
        [data-testid="stSidebar"] [data-baseweb="select"] > div { background:#f8f6ef; border-radius:12px; }
        [data-testid="stSidebar"] [data-baseweb="select"] * { color:#24362c!important; }
        [data-testid="stFileUploader"] section { background:#fffdf7; border:1px dashed #c29a5b; border-radius:14px; }
        [data-testid="stFileUploader"] section * { color:#344238!important; }
        [data-testid="stChatMessage"] { background:#fffefa!important; border:1px solid #e4e1d7;
            border-radius:16px; padding:1rem 1.2rem; box-shadow:0 7px 22px #26372b09; margin:.8rem 0; }
        [data-testid="stChatMessage"] p,[data-testid="stChatMessage"] li { color:#26332c!important; line-height:1.75; }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) { border-left:3px solid #c29a5b; }
        [data-testid="stChatInput"] { background:#fffefa!important; border:1px solid #c9cdbf!important;
            border-radius:16px!important; box-shadow:0 10px 30px #26372b12; }
        [data-testid="stChatInput"] textarea,.stChatInput textarea,
        [data-testid="stChatInput"] [contenteditable="true"] {
            color:#17251d!important; -webkit-text-fill-color:#17251d!important;
            caret-color:#b18443!important; font-weight:600!important; opacity:1!important;
        }
        [data-testid="stChatInput"] textarea::placeholder,.stChatInput textarea::placeholder {
            color:#778078!important; -webkit-text-fill-color:#778078!important; opacity:1!important;
        }
        [data-testid="stChatInput"]:focus-within { border-color:#a77e40!important;
            box-shadow:0 0 0 3px #c29a5b25,0 10px 30px #26372b12!important; }
        .stButton>button { border-radius:12px; border:1px solid #244b37; background:#1c402f;
            color:#fff9ed; font-weight:700; transition:all .18s ease; }
        .stButton>button:hover { background:#2d5a42; border-color:#c29a5b; transform:translateY(-1px); color:white; }
        button[kind="secondary"] { background:#fffefa!important; color:#254332!important; border:1px solid #d7d8cc!important; }
        button[kind="secondary"]:hover { background:#f1eadb!important; border-color:#c29a5b!important; }
        [data-testid="stExpander"] { background:#fffefa99; border:1px solid #e2dfd4; border-radius:14px; }
        [data-testid="stMetric"] { background:#fffefa; padding:.8rem 1rem; border:1px solid #e5e2d8; border-radius:14px; }
        hr { border-color:#deded2!important; }
        /* ---------------------------------------------------------------
           Streamlit's native top toolbar: make it calm, opaque and compact.
           Extra content padding prevents the fixed toolbar from overlapping
           the hero heading at the top of the page.
        ---------------------------------------------------------------- */
        header[data-testid="stHeader"] {
            height: 3.6rem !important;
            min-height: 3.6rem !important;
            background: rgba(244,242,236,.98) !important;
            border-bottom: 1px solid #deded2 !important;
            box-shadow: 0 3px 14px rgba(31,42,37,.045) !important;
            z-index: 1000 !important;
        }
        header[data-testid="stHeader"] [data-testid="stToolbar"] {
            height: 3.6rem !important;
            min-height: 3.6rem !important;
            padding-right: 1rem !important;
            align-items: center !important;
        }
        /* Hide the prominent Deploy action; keep the overflow menu available. */
        [data-testid="stDeployButton"] { display: none !important; }
        header[data-testid="stHeader"] button {
            color: #244633 !important;
            border-radius: 10px !important;
        }
        header[data-testid="stHeader"] button:hover {
            background: #e8e7dc !important;
        }
        header[data-testid="stHeader"] svg {
            fill: #244633 !important;
            color: #244633 !important;
            stroke: #244633 !important;
        }
        .block-container {
            padding-top: 5.2rem !important;
        }

        /* Make the sidebar collapse / expand controls visible on both states. */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapsedControl"] {
            background: #1c3c2c !important;
            border: 1px solid #c29a5b !important;
            border-radius: 10px !important;
            box-shadow: 0 3px 12px rgba(0,0,0,.16) !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapsedControl"] button {
            color: #f5e8cd !important;
            background: transparent !important;
            border: 0 !important;
        }
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stSidebarCollapsedControl"] svg {
            color: #f5e8cd !important;
            fill: #f5e8cd !important;
            stroke: #f5e8cd !important;
        }
        [data-testid="stSidebarCollapseButton"]:hover,
        [data-testid="stSidebarCollapsedControl"]:hover {
            background: #315840 !important;
            border-color: #e0bd7d !important;
        }

        /* Dashboard metric cards: prevent long filenames and mode names
           from being clipped or rendered at oversized default font sizes. */
        [data-testid="stMetric"] {
            min-width: 0 !important;
            height: 100% !important;
            padding: .95rem 1rem !important;
            overflow: hidden !important;
        }
        [data-testid="stMetricLabel"] {
            min-width: 0 !important;
            margin-bottom: .45rem !important;
            font-size: .78rem !important;
            line-height: 1.3 !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            color: #68736b !important;
        }
        [data-testid="stMetricValue"] {
            min-width: 0 !important;
            width: 100% !important;
            font-size: clamp(1.05rem, 1.45vw, 1.45rem) !important;
            line-height: 1.28 !important;
            font-weight: 600 !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            word-break: break-word !important;
            color: #193b2d !important;
        }
        [data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] > div > div {
            min-width: 0 !important;
            max-width: 100% !important;
            font-size: inherit !important;
            line-height: inherit !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
            word-break: break-word !important;
        }
        [data-testid="stMetricDelta"] {
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }


        /* ===============================================================
           THEME-AWARE COLOUR SYSTEM
           Streamlit exposes --background-color, --secondary-background-color,
           --text-color and --primary-color. The explicit data-theme rules
           below are fallbacks for versions that expose the theme attribute.
        ================================================================ */
        :root {
            --dm-bg: var(--background-color, #f4f2ec);
            --dm-surface: var(--secondary-background-color, #fffefa);
            --dm-text: var(--text-color, #1f2a25);
            --dm-muted: #68736b;
            --dm-border: #deded2;
            --dm-heading: #193b2d;
            --dm-input-bg: var(--secondary-background-color, #fffefa);
            --dm-input-text: var(--text-color, #1f2a25);
            --dm-sidebar-bg: #193729;
            --dm-sidebar-text: #f0eee5;
            --dm-button-bg: #1c402f;
            --dm-button-text: #fff9ed;
            --dm-chat-bg: var(--secondary-background-color, #fffefa);
            --dm-accent: #c29a5b;
        }

        /* Dark theme: dark surfaces always get light readable text. */
        html[data-theme="dark"],
        body[data-theme="dark"],
        [data-theme="dark"],
        .stApp[data-theme="dark"] {
            --dm-bg: #101713;
            --dm-surface: #1b2520;
            --dm-text: #e8eee9;
            --dm-muted: #b0bdb4;
            --dm-border: #39483f;
            --dm-heading: #e4eee6;
            --dm-input-bg: #202b25;
            --dm-input-text: #f2f5f2;
            --dm-sidebar-bg: #101f18;
            --dm-sidebar-text: #f0eee5;
            --dm-button-bg: #315b43;
            --dm-button-text: #ffffff;
            --dm-chat-bg: #1b2520;
        }

        /* Also cover Streamlit builds that attach data-theme to app view. */
        [data-testid="stAppViewContainer"][data-theme="dark"] {
            --dm-bg: #101713;
            --dm-surface: #1b2520;
            --dm-text: #e8eee9;
            --dm-muted: #b0bdb4;
            --dm-border: #39483f;
            --dm-heading: #e4eee6;
            --dm-input-bg: #202b25;
            --dm-input-text: #f2f5f2;
            --dm-chat-bg: #1b2520;
        }

        /* Light theme explicit values. */
        html[data-theme="light"],
        body[data-theme="light"],
        [data-theme="light"],
        .stApp[data-theme="light"] {
            --dm-bg: #f4f2ec;
            --dm-surface: #fffefa;
            --dm-text: #1f2a25;
            --dm-muted: #68736b;
            --dm-border: #deded2;
            --dm-heading: #193b2d;
            --dm-input-bg: #fffefa;
            --dm-input-text: #17251d;
            --dm-chat-bg: #fffefa;
        }

        /* App canvas and all ordinary text. */
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background-color: var(--dm-bg) !important;
            color: var(--dm-text) !important;
        }
        .stApp p, .stApp li, .stApp label, .stApp small,
        .stApp [data-testid="stMarkdownContainer"] {
            color: var(--dm-text);
        }
        .stApp h1, .stApp h2, .stApp h3, .stApp h4,
        .stApp h5, .stApp h6 {
            color: var(--dm-heading) !important;
        }
        .stApp [data-testid="stCaptionContainer"],
        .stApp .stCaption,
        .stApp [data-testid="stCaptionContainer"] * {
            color: var(--dm-muted) !important;
        }

        /* Main header and hero. */
        .topbar { border-bottom-color: var(--dm-border) !important; }
        .brand, .hero-title { color: var(--dm-heading) !important; }
        .top-pill {
            color: var(--dm-muted) !important;
            background: var(--dm-surface) !important;
            border-color: var(--dm-border) !important;
        }
        .hero-copy { color: var(--dm-muted) !important; }
        .welcome-card { color: #f6f2e8 !important; }
        .welcome-card h2 { color: #fff8e9 !important; }
        .welcome-card p { color: #e7e9df !important; }

        /* Dashboard cards, chat transcript, expanders and input surfaces. */
        [data-testid="stMetric"],
        [data-testid="stChatMessage"],
        [data-testid="stExpander"],
        [data-testid="stChatInput"] {
            background: var(--dm-surface) !important;
            border-color: var(--dm-border) !important;
            color: var(--dm-text) !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] *,
        [data-testid="stMetricDelta"] {
            color: var(--dm-muted) !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] *,
        [data-testid="stChatMessage"] p,
        [data-testid="stChatMessage"] li,
        [data-testid="stChatMessage"] strong,
        [data-testid="stChatMessage"] em,
        [data-testid="stChatMessage"] code,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] [data-testid="stMarkdownContainer"],
        [data-testid="stExpander"] [data-testid="stMarkdownContainer"] * {
            color: var(--dm-text) !important;
        }

        /* Chat prompt: typed text, placeholder, caret and surface all adapt. */
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] textarea,
        .stChatInput textarea,
        [data-testid="stChatInput"] [contenteditable="true"] {
            background: var(--dm-input-bg) !important;
            color: var(--dm-input-text) !important;
            -webkit-text-fill-color: var(--dm-input-text) !important;
            caret-color: var(--dm-accent) !important;
        }
        [data-testid="stChatInput"] textarea::placeholder,
        .stChatInput textarea::placeholder {
            color: var(--dm-muted) !important;
            -webkit-text-fill-color: var(--dm-muted) !important;
            opacity: 1 !important;
        }

        /* Text inputs, text areas, select boxes, radio and checkbox labels. */
        .stApp input, .stApp textarea,
        .stApp [data-baseweb="input"] input,
        .stApp [data-baseweb="textarea"] textarea {
            background-color: var(--dm-input-bg) !important;
            color: var(--dm-input-text) !important;
            -webkit-text-fill-color: var(--dm-input-text) !important;
            caret-color: var(--dm-accent) !important;
        }
        .stApp input::placeholder,
        .stApp textarea::placeholder {
            color: var(--dm-muted) !important;
            -webkit-text-fill-color: var(--dm-muted) !important;
            opacity: 1 !important;
        }
        .stApp [data-baseweb="select"] > div,
        .stApp [data-baseweb="popover"] ul,
        .stApp [role="listbox"],
        .stApp [role="option"] {
            background: var(--dm-surface) !important;
            color: var(--dm-text) !important;
            border-color: var(--dm-border) !important;
        }
        .stApp [data-baseweb="select"] *,
        .stApp [role="option"] *,
        .stApp [role="radiogroup"] label,
        .stApp [role="radiogroup"] label *,
        .stApp [data-testid="stCheckbox"] label,
        .stApp [data-testid="stCheckbox"] label * {
            color: var(--dm-text) !important;
        }

        /* Sidebar intentionally remains deep green in both themes. */
        [data-testid="stSidebar"] {
            background: var(--dm-sidebar-bg) !important;
        }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: var(--dm-sidebar-text) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="select"] * {
            background-color: #f8f6ef !important;
            color: #24362c !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section,
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section * {
            background-color: #fffdf7 !important;
            color: #344238 !important;
        }

        /* Buttons retain contrast in both modes. */
        .stButton > button,
        .stDownloadButton > button {
            background: var(--dm-button-bg) !important;
            color: var(--dm-button-text) !important;
            border-color: var(--dm-button-bg) !important;
        }
        .stButton > button *,
        .stDownloadButton > button * {
            color: var(--dm-button-text) !important;
        }
        .stButton > button[kind="secondary"] {
            background: var(--dm-surface) !important;
            color: var(--dm-text) !important;
            border-color: var(--dm-border) !important;
        }
        .stButton > button[kind="secondary"] * {
            color: var(--dm-text) !important;
        }

        /* Streamlit toolbar and separators. */
        header[data-testid="stHeader"] {
            background: var(--dm-bg) !important;
            border-bottom-color: var(--dm-border) !important;
        }
        header[data-testid="stHeader"] button,
        header[data-testid="stHeader"] svg {
            color: var(--dm-text) !important;
            fill: var(--dm-text) !important;
            stroke: var(--dm-text) !important;
        }
        .stApp hr { border-color: var(--dm-border) !important; }

        /* Fallback for dark mode if the browser/theme exposes only CSS vars. */
        @media (prefers-color-scheme: dark) {
            html:not([data-theme="light"]) {
                color-scheme: dark;
            }
        }

        @media(max-width:760px){
            .block-container{padding:4.7rem .9rem 3rem !important}
            .welcome-card{padding:1.5rem}
            .top-pill{display:none}
            [data-testid="stMetricValue"]{font-size:1.05rem !important}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Session state and Gemini workflow
# -----------------------------------------------------------------------------
def initialize_state():
    defaults = {
        "client": None,
        "chat_session": None,
        "messages": [],
        "active_file": None,
        "active_file_name": None,
        "current_mode": "Guided Learning",
        "available_models": [],
        "selected_model": "gemini-2.5-flash",
        "pending_prompt": None,
        "api_connection_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if st.session_state.client is None and API_KEY:
        try:
            st.session_state.client = genai.Client(api_key=API_KEY)
            st.session_state.api_connection_error = None
        except Exception as exc:
            st.session_state.client = None
            st.session_state.api_connection_error = str(exc)


def fetch_available_models():
    if st.session_state.available_models or not st.session_state.client:
        return
    try:
        models = st.session_state.client.models.list()
        names = [m.name for m in models if "gemini" in m.name.lower()]
        st.session_state.available_models = names or ["gemini-2.5-flash"]
        if st.session_state.selected_model not in names and names:
            # Prefer a current Flash model for speed and cost efficiency.
            flash_models = [name for name in names if "flash" in name.lower()]
            st.session_state.selected_model = flash_models[0] if flash_models else names[0]
    except APIError as exc:
        # Keep the app usable enough to display setup guidance, but preserve the
        # real API error so the user knows the key was rejected.
        st.session_state.api_connection_error = str(exc)
        st.session_state.available_models = ["gemini-2.5-flash"]
    except Exception as exc:
        st.session_state.api_connection_error = str(exc)
        st.session_state.available_models = ["gemini-2.5-flash"]


def cleanup_remote_file():
    if st.session_state.active_file and st.session_state.client:
        try:
            st.session_state.client.files.delete(name=st.session_state.active_file.name)
        except Exception:
            pass
    st.session_state.active_file = None
    st.session_state.active_file_name = None


def init_chat_session():
    if not st.session_state.client or not st.session_state.active_file:
        return
    persona = PERSONAS[st.session_state.current_mode]["instruction"]
    system_instruction = f"""{persona}\n\n{CITATION_POLICY}\n\nGENERAL STYLE: Be helpful, accurate, readable, and well structured. Match the user's requested level of detail. Never claim to have checked a page if you have not."""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2,
    )
    st.session_state.chat_session = st.session_state.client.chats.create(
        model=st.session_state.selected_model,
        config=config,
    )
    st.session_state.messages = []


def show_gemini_error(exc, action="complete this request"):
    """Show actionable guidance for common Gemini API key errors."""
    error_text = str(exc)
    normalized = error_text.lower()
    if "api_key_invalid" in normalized or "api key not valid" in normalized or "invalid api key" in normalized:
        st.error("Gemini rejected the API key. This is an authentication issue, not a problem with your PDF.")
        st.markdown(
            """
            **Fix the API key:**
            1. Open [Google AI Studio – API keys](https://aistudio.google.com/app/apikey).
            2. Create a new key for a project with the Gemini Developer API enabled.
            3. Put it in the `.env` file beside `app.py`, using exactly this format:

            ```env
            GEMINI_API_KEY=your_new_key_here
            ```

            4. Save `.env`, stop Streamlit with `Ctrl + C`, then restart with `streamlit run app.py`.

            Do not share your API key or commit `.env` to GitHub.
            """
        )
    elif "permission_denied" in normalized or "permission denied" in normalized:
        st.error("Google denied access to this API request. Check that the Gemini Developer API is enabled for the Google Cloud project associated with this key.")
        st.caption(error_text)
    elif "resource_exhausted" in normalized or "quota" in normalized:
        st.error("The Gemini API quota or rate limit has been reached. Check your project quota and billing settings, then try again later.")
        st.caption(error_text)
    else:
        st.error(f"Gemini could not {action}: {error_text}")


def upload_pdf(uploaded_file):
    if not st.session_state.client:
        st.error("Gemini is not connected. Add a valid GEMINI_API_KEY to continue.")
        return
    cleanup_remote_file()
    tmp_path = None
    try:
        with st.spinner("Preparing your PDF and opening your reading room…"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            remote_file = st.session_state.client.files.upload(
                file=tmp_path,
                config={"display_name": uploaded_file.name},
            )
            st.session_state.active_file = remote_file
            st.session_state.active_file_name = uploaded_file.name
            init_chat_session()
        st.toast("Your document is ready to explore.", icon="📚")
    except APIError as exc:
        show_gemini_error(exc, action="process this PDF")
    except Exception as exc:
        st.error(f"Something went wrong while opening the PDF: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def render_transcript_download():
    if not st.session_state.messages:
        return
    lines = [f"# DocuMind conversation\n\nDocument: {st.session_state.active_file_name or 'PDF'}\nMode: {st.session_state.current_mode}\nExported: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for msg in st.session_state.messages:
        label = "You" if msg["role"] == "user" else "DocuMind"
        lines.append(f"\n## {label}\n\n{msg['content']}\n")
    st.download_button(
        "↓  Export conversation",
        data="\n".join(lines),
        file_name="documind_conversation.md",
        mime="text/markdown",
        use_container_width=True,
    )


def send_prompt(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🙂"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar="✨"):
        try:
            payload = [st.session_state.active_file, prompt] if len(st.session_state.messages) == 1 else prompt
            stream = st.session_state.chat_session.send_message_stream(payload)
            response = st.write_stream(chunk.text for chunk in stream if getattr(chunk, "text", None))
            st.session_state.messages.append({"role": "assistant", "content": response})
        except APIError as exc:
            show_gemini_error(exc, action="answer your question")
        except Exception as exc:
            st.error(f"I couldn't complete that response: {exc}")


# -----------------------------------------------------------------------------
# App layout
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="DocuMind | Your PDF Research Studio",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    initialize_state()
    fetch_available_models()

    with st.sidebar:
        st.markdown(
            """
            <div style="padding:.25rem 0 1.1rem">
                <div style="font:800 1.18rem Manrope,sans-serif;letter-spacing:.12em;color:#f7ecd8">DOCUMIND</div>
                <div style="font-size:.65rem;letter-spacing:.18em;text-transform:uppercase;color:#d2b77e;margin-top:.28rem">Your document, understood</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("### 01 · Your document")
        uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"], help="Choose the PDF you want to ask questions about.")
        if uploaded_file and uploaded_file.name != st.session_state.active_file_name:
            upload_pdf(uploaded_file)

        if st.session_state.active_file:
            st.success(f"Ready · {st.session_state.active_file_name}")
        else:
            st.caption("Your PDF stays the centre of every answer. Add one to begin.")

        st.divider()
        st.markdown("### 02 · Choose your experience")
        mode_names = list(PERSONAS.keys())
        selected_mode = st.radio(
            "How should DocuMind help?",
            mode_names,
            index=mode_names.index(st.session_state.current_mode),
            format_func=lambda name: f"{PERSONAS[name]['icon']}  {name}",
            label_visibility="collapsed",
        )
        st.caption(PERSONAS[selected_mode]["description"])
        if selected_mode != st.session_state.current_mode:
            st.session_state.current_mode = selected_mode
            if st.session_state.active_file:
                init_chat_session()
                st.toast(f"Switched to {selected_mode}.", icon="✨")
                st.rerun()

        st.divider()
        st.markdown("### 03 · Model settings")
        models = st.session_state.available_models or [st.session_state.selected_model]
        chosen_model = st.selectbox(
            "Gemini model",
            options=models,
            index=models.index(st.session_state.selected_model) if st.session_state.selected_model in models else 0,
        )
        if chosen_model != st.session_state.selected_model:
            st.session_state.selected_model = chosen_model
            if st.session_state.active_file:
                init_chat_session()
                st.toast("Model updated. Start a new question.", icon="⚙️")
                st.rerun()

        with st.expander("How PDF citations work"):
            st.markdown(
                "Answers are asked to cite the **PDF page number** for document-based claims, and to include a section name or short quote where possible. If a page cannot be located confidently, DocuMind should say so instead of guessing."
            )
            st.caption("Always verify important page references against the original PDF.")

        if not API_KEY:
            st.warning(
                "Gemini API key not found. Create a `.env` file in the same folder as `app.py` and add `GEMINI_API_KEY=your_actual_key`."
            )
            st.caption(f"Expected .env location: {ENV_PATH}")
        elif st.session_state.api_connection_error:
            st.warning("Gemini could not validate the API connection. Check the key and restart the app.")
            with st.expander("Show connection details"):
                st.code(st.session_state.api_connection_error)

    # Main header
    st.markdown(
        """
        <div class="topbar">
            <div class="brand"><span class="brand-mark">D</span> DOCUMIND <span style="font-weight:500;color:#879087;letter-spacing:.05em">/ RESEARCH STUDIO</span></div>
            <div class="top-pill">✦ &nbsp; Read smarter. Find the source.</div>
        </div>
        <div class="hero-kicker">A clearer way to work with documents</div>
        <div class="hero-title">Ask better questions.<br>Find answers you can trace.</div>
        <div class="hero-copy">Explore your PDF with an assistant that adapts to your goal, explains ideas in plain language, and points you back to the pages that support its answers.</div>
        <div class="hero-line"></div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.active_file:
        st.markdown(
            """
            <div class="welcome-card">
                <div class="mini-label">Your personal document workspace</div>
                <h2>One PDF. Three ways to understand it.</h2>
                <p>Upload a document from the sidebar. Learn it step by step, get the executive view, or investigate the evidence in depth — with page references wherever they can be identified.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🎓 Guided Learning**")
            st.caption("Make complex ideas feel simple.")
        with c2:
            st.markdown("**📌 Executive Summary**")
            st.caption("See the key points and actions fast.")
        with c3:
            st.markdown("**🔎 Deep Research**")
            st.caption("Follow claims back to their evidence.")
        return

    # Document dashboard
    metric1, metric2, metric3 = st.columns([1.5, 1, 1])
    with metric1:
        st.metric("Document", st.session_state.active_file_name or "PDF uploaded")
    with metric2:
        st.metric("Reading mode", st.session_state.current_mode)
    with metric3:
        st.metric("Questions asked", sum(1 for m in st.session_state.messages if m["role"] == "user"))

    with st.expander("✦  Start with a suggested question", expanded=not st.session_state.messages):
        st.caption(PERSONAS[st.session_state.current_mode]["tagline"])
        prompt_cols = st.columns(2)
        for index, suggestion in enumerate(QUICK_PROMPTS[st.session_state.current_mode]):
            with prompt_cols[index % 2]:
                if st.button(suggestion, key=f"suggestion_{st.session_state.current_mode}_{index}", use_container_width=True):
                    st.session_state.pending_prompt = suggestion
                    st.rerun()

    # Conversation history
    for msg in st.session_state.messages:
        avatar = "🙂" if msg["role"] == "user" else "✨"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # Conversation actions
    action_col1, action_col2, action_col3 = st.columns([1, 1, 2])
    with action_col1:
        if st.button("＋ New conversation", use_container_width=True, disabled=not st.session_state.messages):
            init_chat_session()
            st.rerun()
    with action_col2:
        if st.button("Clear chat", use_container_width=True, disabled=not st.session_state.messages):
            init_chat_session()
            st.rerun()
    with action_col3:
        render_transcript_download()

    typed_prompt = st.chat_input(
        "Ask about this PDF… (answers include page references where identifiable)",
        disabled=not st.session_state.chat_session,
    )
    prompt = st.session_state.pending_prompt or typed_prompt
    if prompt:
        st.session_state.pending_prompt = None
        send_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
