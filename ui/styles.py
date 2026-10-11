import importlib
import streamlit as st
import ui.icons
if not hasattr(ui.icons, "MEMORY_ICON"):
    importlib.reload(ui.icons)
from ui.icons import (
    UPLOAD_ICON,
    ASK_AI_ICON,
    DOWNLOAD_ICON,
    SUN_ICON,
    MOON_ICON,
    BACK_ICON,
    MEMORY_ICON,
    get_svg_data_uri,
    clean_html,
)


def inject_styles():
    theme = st.session_state.get("theme", "dark")
    is_light = theme == "light"

    # Encode SVG icons with theme-appropriate stroke colors
    icon_stroke = "#0F172A" if is_light else "#F8FAFC"
    upload_uri = get_svg_data_uri(UPLOAD_ICON, stroke_color=icon_stroke)
    ask_uri = get_svg_data_uri(ASK_AI_ICON, stroke_color="#FFFFFF")
    download_uri = get_svg_data_uri(DOWNLOAD_ICON, stroke_color=icon_stroke)
    back_uri = get_svg_data_uri(BACK_ICON, stroke_color=icon_stroke)
    memory_uri = get_svg_data_uri(MEMORY_ICON, stroke_color="#2563EB" if is_light else "#38BDF8")

    # Theme toggle icon: show Sun when in dark mode (to switch to light), Moon when in light mode
    toggle_uri = (
        get_svg_data_uri(MOON_ICON, stroke_color="#0F172A")
        if is_light
        else get_svg_data_uri(SUN_ICON, stroke_color="#FBBF24")
    )
    toggle_tooltip = "Switch to Dark Mode" if is_light else "Switch to Light Mode"

    if is_light:
        theme_vars = """
        --bg-app: radial-gradient(circle at 12% 15%, rgba(37, 99, 235, 0.08), transparent 38%), radial-gradient(circle at 88% 82%, rgba(79, 70, 229, 0.08), transparent 42%), linear-gradient(160deg, #F8FAFC 0%, #F1F5F9 55%, #E2E8F0 100%);
        --bg-solid: #F8FAFC;
        --surface-card: rgba(255, 255, 255, 0.90);
        --surface-elevated: #FFFFFF;
        --surface-dock: rgba(255, 255, 255, 0.88);
        --surface-button: #F1F5F9;
        --surface-button-hover: #E2E8F0;
        --border-subtle: rgba(15, 23, 42, 0.10);
        --border-strong: rgba(37, 99, 235, 0.35);
        --text-primary: #0F172A;
        --text-secondary: #334155;
        --text-muted: #64748B;
        --accent-primary: #2563EB;
        --accent-secondary: #4F46E5;
        --accent-gradient: linear-gradient(135deg, #2563EB 0%, #4F46E5 100%);
        --hero-title-gradient: linear-gradient(135deg, #0F172A 0%, #1E3A8A 55%, #4F46E5 100%);
        --shadow-card: 0 10px 30px -5px rgba(15, 23, 42, 0.06), 0 4px 12px -2px rgba(15, 23, 42, 0.04);
        --shadow-dock: 0 20px 45px -10px rgba(15, 23, 42, 0.14), 0 0 0 1px rgba(15, 23, 42, 0.08);
        --shadow-btn: 0 4px 14px rgba(15, 23, 42, 0.08);
        --table-header-bg: rgba(37, 99, 235, 0.08);
        --table-row-bg: rgba(255, 255, 255, 0.75);
        """
    else:
        theme_vars = """
        --bg-app: radial-gradient(circle at 12% 15%, rgba(56, 189, 248, 0.12), transparent 38%), radial-gradient(circle at 88% 82%, rgba(99, 102, 241, 0.14), transparent 42%), linear-gradient(160deg, #060913 0%, #0B1120 50%, #0F172A 100%);
        --bg-solid: #0B1120;
        --surface-card: rgba(15, 23, 42, 0.72);
        --surface-elevated: rgba(30, 41, 59, 0.85);
        --surface-dock: rgba(15, 23, 42, 0.78);
        --surface-button: rgba(30, 41, 59, 0.9);
        --surface-button-hover: rgba(51, 65, 85, 0.95);
        --border-subtle: rgba(148, 163, 184, 0.16);
        --border-strong: rgba(56, 189, 248, 0.42);
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --text-muted: #94A3B8;
        --accent-primary: #38BDF8;
        --accent-secondary: #6366F1;
        --accent-gradient: linear-gradient(135deg, #0284C7 0%, #4F46E5 100%);
        --hero-title-gradient: linear-gradient(135deg, #FFFFFF 0%, #BAE6FD 55%, #A5B4FC 100%);
        --shadow-card: 0 12px 32px -4px rgba(0, 0, 0, 0.42);
        --shadow-dock: 0 24px 50px -12px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.1);
        --shadow-btn: 0 6px 18px rgba(0, 0, 0, 0.35);
        --table-header-bg: rgba(56, 189, 248, 0.14);
        --table-row-bg: rgba(15, 23, 42, 0.55);
        """

    css_html = f"""
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root, .stApp {{
{theme_vars}
}}
.stApp {{
background: var(--bg-app) !important;
background-attachment: fixed !important;
color: var(--text-primary) !important;
font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
transition: background 0.3s ease, color 0.25s ease;
}}
header[data-testid="stHeader"] {{
visibility: hidden !important;
height: 0 !important;
}}
footer {{
visibility: hidden !important;
}}
#MainMenu {{
visibility: hidden !important;
}}
html, body, [class*="css"] {{
font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
color: var(--text-primary);
}}
.block-container {{
max-width: 960px !important;
padding-top: 2.25rem !important;
padding-bottom: 7rem !important;
}}
.st-key-theme_toggle_wrap {{
position: fixed !important;
top: 24px !important;
left: 28px !important;
z-index: 99999 !important;
width: auto !important;
}}
.st-key-memory_toggle_wrap {{
position: fixed !important;
top: 80px !important;
left: 28px !important;
z-index: 99999 !important;
width: auto !important;
}}
.st-key-btn_theme_toggle button,
.st-key-btn_memory_toggle button {{
width: 46px !important;
height: 46px !important;
min-height: 46px !important;
padding: 0 !important;
border-radius: 9999px !important;
background-color: var(--surface-dock) !important;
background-repeat: no-repeat !important;
background-position: center !important;
background-size: 20px 20px !important;
backdrop-filter: blur(16px) !important;
-webkit-backdrop-filter: blur(16px) !important;
border: 1px solid var(--border-subtle) !important;
box-shadow: var(--shadow-btn) !important;
color: transparent !important;
transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
position: relative !important;
}}
.st-key-btn_theme_toggle button {{
background-image: url("{toggle_uri}") !important;
}}
.st-key-btn_memory_toggle button {{
background-image: url("{memory_uri}") !important;
}}
.st-key-btn_theme_toggle button p,
.st-key-btn_memory_toggle button p {{
display: none !important;
}}
.st-key-btn_theme_toggle button:hover,
.st-key-btn_memory_toggle button:hover {{
transform: translateY(-2px) scale(1.04) !important;
border-color: var(--border-strong) !important;
background-color: var(--surface-button-hover) !important;
}}
.st-key-btn_theme_toggle button:focus-visible,
.st-key-btn_memory_toggle button:focus-visible {{
outline: 2px solid var(--accent-primary) !important;
outline-offset: 2px !important;
}}
.st-key-btn_theme_toggle button::after,
.st-key-btn_memory_toggle button::after {{
position: absolute;
left: 56px;
top: 50%;
transform: translateY(-50%) translateX(-4px);
background: var(--surface-elevated);
color: var(--text-primary);
font-size: 0.75rem;
font-weight: 600;
padding: 5px 11px;
border-radius: 9999px;
border: 1px solid var(--border-subtle);
box-shadow: var(--shadow-btn);
white-space: nowrap;
opacity: 0;
pointer-events: none;
transition: all 0.18s ease;
}}
.st-key-btn_theme_toggle button::after {{
content: "{toggle_tooltip}";
}}
.st-key-btn_memory_toggle button::after {{
content: "Persistent Memory";
}}
.st-key-btn_theme_toggle button:hover::after,
.st-key-btn_memory_toggle button:hover::after {{
opacity: 1;
transform: translateY(-50%) translateX(0);
}}
.st-key-bottom_dock {{
position: fixed !important;
bottom: 28px !important;
left: 50% !important;
transform: translateX(-50%) !important;
background: var(--surface-dock) !important;
backdrop-filter: blur(24px) !important;
-webkit-backdrop-filter: blur(24px) !important;
border: 1px solid var(--border-subtle) !important;
border-radius: 9999px !important;
padding: 12px 28px 24px 28px !important;
z-index: 9998 !important;
width: auto !important;
min-width: 290px !important;
box-shadow: var(--shadow-dock) !important;
}}
.st-key-bottom_dock div[data-testid="stHorizontalBlock"] {{
display: flex !important;
flex-direction: row !important;
align-items: center !important;
justify-content: center !important;
gap: 28px !important;
width: auto !important;
}}
.st-key-bottom_dock div[data-testid="stColumn"] {{
flex: 0 0 auto !important;
width: auto !important;
min-width: auto !important;
display: flex !important;
flex-direction: column !important;
align-items: center !important;
justify-content: center !important;
}}
.st-key-btn_upload_dock button,
.st-key-btn_ask_dock button,
.st-key-btn_gen_report button,
.st-key-btn_download_cached button,
.st-key-btn_download_disabled button {{
width: 56px !important;
height: 56px !important;
min-height: 56px !important;
max-width: 56px !important;
padding: 0 !important;
border-radius: 9999px !important;
background-color: var(--surface-button) !important;
background-repeat: no-repeat !important;
background-position: center !important;
background-size: 22px 22px !important;
border: 1px solid var(--border-subtle) !important;
box-shadow: var(--shadow-btn) !important;
color: transparent !important;
transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1) !important;
position: relative !important;
cursor: pointer !important;
}}
.st-key-btn_upload_dock button p,
.st-key-btn_ask_dock button p,
.st-key-btn_gen_report button p,
.st-key-btn_download_cached button p,
.st-key-btn_download_disabled button p {{
display: none !important;
}}
.st-key-btn_upload_dock button {{
background-image: url("{upload_uri}") !important;
}}
.st-key-btn_upload_dock button::after {{
content: "Upload";
position: absolute;
bottom: -20px;
left: 50%;
transform: translateX(-50%);
font-size: 0.7rem;
font-weight: 600;
letter-spacing: 0.02em;
color: var(--text-secondary);
white-space: nowrap;
}}
.st-key-btn_ask_dock button {{
width: 62px !important;
height: 62px !important;
min-height: 62px !important;
max-width: 62px !important;
background: url("{ask_uri}") center / 25px 25px no-repeat, var(--accent-gradient) !important;
border: 1px solid rgba(255, 255, 255, 0.28) !important;
box-shadow: 0 10px 25px -4px rgba(37, 99, 235, 0.5) !important;
}}
.st-key-btn_ask_dock button::after {{
content: "Ask AI";
position: absolute;
bottom: -20px;
left: 50%;
transform: translateX(-50%);
font-size: 0.7rem;
font-weight: 700;
letter-spacing: 0.02em;
color: var(--accent-primary);
white-space: nowrap;
}}
.st-key-btn_gen_report button,
.st-key-btn_download_cached button,
.st-key-btn_download_disabled button {{
background-image: url("{download_uri}") !important;
}}
.st-key-btn_gen_report button::after,
.st-key-btn_download_cached button::after,
.st-key-btn_download_disabled button::after {{
content: "Report";
position: absolute;
bottom: -20px;
left: 50%;
transform: translateX(-50%);
font-size: 0.7rem;
font-weight: 600;
letter-spacing: 0.02em;
color: var(--text-secondary);
white-space: nowrap;
}}
.st-key-btn_download_cached button::before {{
content: "";
position: absolute;
top: 3px;
right: 3px;
width: 10px;
height: 10px;
border-radius: 9999px;
background: #10B981;
border: 2px solid var(--bg-solid);
}}
.st-key-btn_upload_dock button:hover,
.st-key-btn_gen_report button:hover,
.st-key-btn_download_cached button:hover,
.st-key-btn_download_disabled button:hover {{
transform: translateY(-4px) scale(1.05) !important;
background-color: var(--surface-button-hover) !important;
border-color: var(--border-strong) !important;
}}
.st-key-btn_ask_dock button:hover {{
transform: translateY(-4px) scale(1.06) !important;
box-shadow: 0 14px 30px -4px rgba(37, 99, 235, 0.65) !important;
}}
.st-key-btn_back_home button {{
width: 44px !important;
height: 44px !important;
min-height: 44px !important;
padding: 0 !important;
border-radius: 9999px !important;
background-color: var(--surface-button) !important;
background-image: url("{back_uri}") !important;
background-repeat: no-repeat !important;
background-position: center !important;
background-size: 18px 18px !important;
border: 1px solid var(--border-subtle) !important;
box-shadow: var(--shadow-btn) !important;
color: transparent !important;
transition: all 0.2s ease !important;
}}
.st-key-btn_back_home button p {{
display: none !important;
}}
.st-key-btn_back_home button:hover {{
transform: translateY(-2px) !important;
background-color: var(--surface-button-hover) !important;
border-color: var(--border-strong) !important;
}}
div[data-testid="stButton"] button {{
border-radius: 12px;
font-weight: 500;
border: 1px solid var(--border-subtle);
background: var(--surface-card);
color: var(--text-primary);
transition: all 0.18s ease;
}}
div[data-testid="stButton"] button:hover {{
border-color: var(--border-strong);
transform: translateY(-1px);
}}
div[data-testid="stChatMessage"] {{
background: var(--surface-card) !important;
backdrop-filter: blur(16px) !important;
-webkit-backdrop-filter: blur(16px) !important;
border: 1px solid var(--border-subtle) !important;
border-radius: 16px !important;
padding: 1.1rem 1.35rem !important;
margin-bottom: 1rem !important;
box-shadow: var(--shadow-card) !important;
}}
div[data-testid="stChatMessage"] p,
div[data-testid="stChatMessage"] li {{
font-size: 0.95rem !important;
line-height: 1.68 !important;
color: var(--text-secondary) !important;
}}
div[data-testid="stChatMessage"] strong,
div[data-testid="stChatMessage"] b {{
color: var(--text-primary) !important;
font-weight: 600 !important;
}}
div[data-testid="stChatMessage"] h3 {{
font-size: 1.08rem !important;
font-weight: 700 !important;
color: var(--accent-primary) !important;
margin-top: 0.9rem !important;
margin-bottom: 0.45rem !important;
}}
div[data-testid="stPlotlyChart"] {{
max-width: 520px !important;
background: var(--surface-card) !important;
backdrop-filter: blur(14px) !important;
-webkit-backdrop-filter: blur(14px) !important;
border: 1px solid var(--border-subtle) !important;
border-radius: 14px !important;
padding: 8px !important;
margin: 0.65rem 0 !important;
box-shadow: var(--shadow-card) !important;
overflow: hidden !important;
}}
div[data-testid="stChatMessage"] table {{
width: 100%;
border-collapse: collapse;
margin: 0.75rem 0;
font-size: 0.87rem;
background: var(--table-row-bg);
border-radius: 10px;
overflow: hidden;
border: 1px solid var(--border-subtle);
}}
div[data-testid="stChatMessage"] th {{
background: var(--table-header-bg);
color: var(--text-primary);
font-weight: 600;
text-align: left;
padding: 9px 13px;
border-bottom: 1px solid var(--border-subtle);
}}
div[data-testid="stChatMessage"] td {{
padding: 8px 13px;
border-bottom: 1px solid var(--border-subtle);
color: var(--text-secondary);
}}
div[role="dialog"] {{
background: var(--surface-elevated) !important;
color: var(--text-primary) !important;
border: 1px solid var(--border-subtle) !important;
border-radius: 20px !important;
box-shadow: var(--shadow-dock) !important;
}}
@media (prefers-reduced-motion: reduce) {{
*, *::before, *::after {{
animation-duration: 0.01ms !important;
transition-duration: 0.01ms !important;
}}
}}
@media (max-width: 640px) {{
.block-container {{
padding-left: 1rem !important;
padding-right: 1rem !important;
}}
.st-key-theme_toggle_wrap {{
top: 14px !important;
left: 14px !important;
}}
div[data-testid="stPlotlyChart"] {{
max-width: 100% !important;
}}
}}
</style>
"""
    st.markdown(clean_html(css_html), unsafe_allow_html=True)
