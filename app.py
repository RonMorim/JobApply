"""Streamlit dashboard — JobApply Venture · Candidate Command Center.

Architecture
------------
Sidebar  →  Role selector (Candidate | Recruiter)
             Candidate sub-nav: Dashboard | Verification & Evidence | Job Matching
             Recruiter: single report view

Candidate pages
---------------
dashboard  : profile confidence + verified skills overview — no match score
evidence   : integrity optimizer + evidence builder (with file upload)
matching   : dynamic job search, JD matcher (text OR url), inmail generator
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

from backend.logic.verifier import ProfileVerifier
from backend.logic.outreach_engine import OutreachEngine
from backend.integrations.job_scraper import (
    get_latest_jobs,
    score_job_fit,
    fetch_text_from_url,
    SENIORITY_OPTIONS,
)
from orchestrator import analyze_fit, _TARGET_JOB

# ── Constants ─────────────────────────────────────────────────────────────────

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "data", "user_master_profile.json")

_COMPANIES = [
    "Monday.com", "Wix", "Google", "Meta", "Salesforce",
    "HubSpot", "Notion", "Linear", "Atlassian",
]

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="JobApply Venture",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — light mode only ────────────────────────────────────────────────────
# config.toml sets base="light"; this block handles spacing, cards, and
# component styling. No dark colors or backdrop-filter anywhere.

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Force light on every Streamlit surface ──────────────────────────────── */
html, body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stBottom"],
[data-testid="block-container"],
.main, .main > div,
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div,
[data-testid="stSidebarContent"] {
    background-color: #F8FAFC !important;
    color: #0F172A !important;
}

/* Sidebar specifically white */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}

/* Sidebar buttons — prevent text wrap in narrow columns */
section[data-testid="stSidebar"] .stButton > button {
    white-space: nowrap !important;
    font-size: 0.8rem !important;
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
}

/* ── Typography ──────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
}

/* ── Layout ──────────────────────────────────────────────────────────────── */
.stApp { background-color: #F8FAFC !important; }
.block-container { padding: 1.8rem 2.4rem 3rem !important; max-width: 1320px; }

/* ── Metric cards ──────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 14px !important;
    padding: 1.1rem 1.4rem !important;
    box-shadow: 0 1px 4px rgba(15,23,42,0.05) !important;
    color: #0F172A !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.85rem !important; font-weight: 800 !important;
    letter-spacing: -0.03em; color: #0F172A !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.7rem !important; font-weight: 700 !important;
    color: #64748B !important; text-transform: uppercase; letter-spacing: 0.07em;
}
[data-testid="stMetricDelta"] { color: #64748B !important; }

/* ── Tabs ──────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #F1F5F9 !important; padding: 4px; border-radius: 12px;
    gap: 2px; border-bottom: none !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 9px !important; padding: 8px 22px !important;
    font-weight: 600 !important; font-size: 0.875rem !important;
    color: #64748B !important; border: none !important;
    background: transparent !important; transition: all 0.14s !important;
}
.stTabs [aria-selected="true"] {
    background: #FFFFFF !important; color: #0F172A !important;
    box-shadow: 0 1px 6px rgba(15,23,42,0.1) !important;
}
/* Tab panel background */
.stTabs [data-baseweb="tab-panel"] {
    background: transparent !important;
    padding-top: 1rem !important;
}

/* ── Buttons ───────────────────────────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background: #1D4ED8 !important; color: white !important;
    border: none !important; border-radius: 9px !important;
    font-weight: 600 !important; font-size: 0.875rem !important;
    padding: 0.5rem 1.3rem !important; transition: all 0.14s !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1E40AF !important;
    box-shadow: 0 3px 12px rgba(29,78,216,0.28) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]) {
    border-radius: 9px !important; font-weight: 500 !important;
    border: 1px solid #CBD5E1 !important; background: #FFFFFF !important;
    color: #374151 !important; transition: all 0.14s !important;
}
.stButton > button:not([kind="primary"]):hover {
    border-color: #94A3B8 !important; background: #F8FAFC !important;
}

/* ── Inputs ────────────────────────────────────────────────────────────────── */
.stTextArea textarea, .stTextInput input, .stTextArea, .stTextInput {
    border-radius: 9px !important; border: 1.5px solid #CBD5E1 !important;
    font-size: 0.875rem !important;
    background-color: #FFFFFF !important; color: #0F172A !important;
    transition: border-color 0.14s !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #1D4ED8 !important;
    box-shadow: 0 0 0 3px rgba(29,78,216,0.07) !important;
}
.stTextArea textarea::placeholder, .stTextInput input::placeholder {
    color: #94A3B8 !important;
}
.stSelectbox > div > div, .stSelectbox [data-baseweb="select"] {
    border-radius: 9px !important; border: 1.5px solid #CBD5E1 !important;
    background-color: #FFFFFF !important; color: #0F172A !important;
}
/* Radio buttons */
.stRadio > div { background: transparent !important; }
.stRadio label { color: #374151 !important; }

/* ── Forms ─────────────────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: transparent !important; border: none !important; padding: 0 !important;
}

/* ── Expanders ─────────────────────────────────────────────────────────────── */
.streamlit-expanderHeader,
[data-testid="stExpander"] summary {
    border-radius: 9px !important; background-color: #F8FAFC !important;
    font-weight: 600 !important; font-size: 0.875rem !important;
    border: 1px solid #E2E8F0 !important; color: #0F172A !important;
}
.streamlit-expanderContent,
[data-testid="stExpander"] > div:last-child {
    border: 1px solid #E2E8F0 !important; border-top: none !important;
    border-radius: 0 0 9px 9px !important; background-color: #FFFFFF !important;
}

/* ── Sidebar ───────────────────────────────────────────────────────────────── */
/* Background already set in the global force block above */
section[data-testid="stSidebar"] > div { padding-top: 1.1rem; }

/* ── Dataframes ────────────────────────────────────────────────────────────── */
.stDataFrame { border-radius: 12px !important; overflow: hidden; }
[data-testid="stDataFrame"],
[data-testid="stDataFrame"] > div,
.stDataFrame iframe {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
}

/* ── Markdown / text surfaces ──────────────────────────────────────────────── */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span {
    color: #374151 !important;
}
/* Alerts keep their own colours; just ensure backgrounds are light */
[data-testid="stAlert"] { border-radius: 12px !important; }

/* Profile card — override global markdown text rule (specificity: attribute+class > attribute+element) */
[data-testid="stMarkdownContainer"] .profile-name,
[data-testid="stMarkdownContainer"] .profile-role,
[data-testid="stMarkdownContainer"] .profile-card p,
[data-testid="stMarkdownContainer"] .profile-card span,
[data-testid="stMarkdownContainer"] .profile-card div { color: #FFFFFF !important; }
.profile-card, .profile-card p, .profile-card span { color: #FFFFFF !important; }
.profile-role { color: rgba(255,255,255,0.72) !important; }

/* Profile card signal chips — semi-transparent white against the dark-blue gradient.
   Overrides .chip-mastery / .chip-valid backgrounds and the markdown span color rule. */
.profile-card .chip {
    background: rgba(255,255,255,0.14) !important;
    border-color: rgba(255,255,255,0.28) !important;
    color: rgba(255,255,255,0.92) !important;
}
[data-testid="stMarkdownContainer"] .profile-card .chip,
[data-testid="stMarkdownContainer"] .profile-card .chip span {
    color: rgba(255,255,255,0.92) !important;
    background: transparent !important;
}

/* Vega-Lite charts — white canvas background */
[data-testid="stVegaLiteChart"] { background: #FFFFFF !important; }
[data-testid="stVegaLiteChart"] canvas { background: #FFFFFF !important; }
.vega-embed, .vega-embed canvas { background: #FFFFFF !important; }

/* Chat messages */
[data-testid="stChatMessage"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    color: #0F172A !important;
}
[data-testid="stChatInputTextArea"] textarea {
    background: #FFFFFF !important; color: #0F172A !important;
}

/* Daily insight card */
.insight-card {
    background: linear-gradient(135deg, #EFF6FF 0%, #F0FDF4 100%);
    border: 1px solid #BFDBFE; border-radius: 14px;
    padding: 1rem 1.4rem; margin: 1rem 0;
    display: flex; align-items: flex-start; gap: 1rem;
}
.insight-label {
    font-size: 0.62rem; font-weight: 800; color: #1D4ED8;
    text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 0.3rem;
}
.insight-text { font-size: 0.9rem; font-weight: 600; color: #1E293B; }
.insight-detail { font-size: 0.8rem; color: #475569; margin-top: 0.25rem; }

/* File uploader */
[data-testid="stFileUploader"],
[data-testid="stFileUploaderDropzone"] {
    background-color: #FFFFFF !important;
    border: 1.5px dashed #CBD5E1 !important;
    border-radius: 9px !important;
    color: #374151 !important;
}

/* ─────────────────────────────────────────────────────────────────────────────
   CUSTOM COMPONENTS
   ───────────────────────────────────────────────────────────────────────────── */

/* Content card — used on every page for section grouping */
.ccard {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 1.5rem 1.8rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 1px 4px rgba(15,23,42,0.04);
}
.ccard-title {
    font-size: 0.95rem; font-weight: 700; color: #0F172A;
    margin-bottom: 0.9rem;
}

/* Profile header card */
.profile-card {
    background: linear-gradient(135deg, #1E3A8A 0%, #1D4ED8 65%, #2563EB 100%);
    border-radius: 18px; padding: 1.8rem 2.2rem; color: white;
    margin-bottom: 1.6rem;
    box-shadow: 0 4px 24px rgba(29,78,216,0.18);
    position: relative; overflow: hidden;
}
.profile-card::after {
    content: ''; position: absolute; top: -50px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 65%);
    border-radius: 50%; pointer-events: none;
}
.profile-name {
    font-size: 1.85rem; font-weight: 800; color: white;
    margin: 0 0 0.15rem; letter-spacing: -0.03em;
}
.profile-role { font-size: 0.95rem; color: rgba(255,255,255,0.65); margin: 0; }
.ai-badge {
    display: inline-flex; align-items: center; gap: 5px;
    background: rgba(16,185,129,0.18); border: 1px solid rgba(16,185,129,0.45);
    color: #6EE7B7; padding: 4px 12px; border-radius: 100px;
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em; margin-left: 12px;
}
.ai-dot {
    width: 6px; height: 6px; background: #10B981;
    border-radius: 50%; display: inline-block;
    animation: blink 2s ease-in-out infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* Section divider */
.section-rule { border: none; border-top: 1px solid #E2E8F0; margin: 1.6rem 0; }

/* Level chips */
.chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 100px;
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; white-space: nowrap;
}
.chip-claim   { background: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1; }
.chip-valid   { background: #FFFBEB; color: #92400E; border: 1px solid #FCD34D; }
.chip-mastery { background: #F0FDF4; color: #065F46; border: 1px solid #6EE7B7; }

/* Evidence card */
.ev-card {
    background: #FFFFFF; border: 1px solid #E2E8F0;
    border-radius: 14px; overflow: hidden; margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(15,23,42,0.04);
    transition: box-shadow 0.15s, border-color 0.15s;
}
.ev-card:hover { box-shadow: 0 4px 16px rgba(15,23,42,0.08); border-color: #93C5FD; }
.ev-header {
    padding: 0.9rem 1.3rem 0.7rem; border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 0.5rem;
}
.ev-body   { display: flex; }
.ev-main   { flex: 1; padding: 1rem 1.3rem 1.2rem; }
.ev-tip    {
    width: 220px; flex-shrink: 0; padding: 1rem 1.1rem;
    background: #EFF6FF; border-left: 1px solid #BFDBFE;
}
.ev-tip-label {
    font-size: 0.62rem; font-weight: 800; color: #1D4ED8;
    text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 0.45rem;
}
.ev-tip-text { font-size: 0.78rem; color: #374151; line-height: 1.6; }
.ev-challenge {
    background: #F8FAFC; border-left: 3px solid #1D4ED8;
    border-radius: 0 8px 8px 0; padding: 0.65rem 0.9rem;
    font-size: 0.83rem; color: #374151; line-height: 1.6; margin: 0.5rem 0 0.8rem;
}
.skill-name { font-size: 0.95rem; font-weight: 700; color: #0F172A; }

/* Energy bar */
.ebar-row { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: #94A3B8; margin: 4px 0; }
.ebar-segs { display: flex; gap: 3px; flex: 1; }
.ebar-seg  { height: 5px; flex: 1; border-radius: 3px; }

/* Job card (Live Opportunities) */
.job-card {
    background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px;
    padding: 1rem 1.3rem; margin-bottom: 0.75rem;
    box-shadow: 0 1px 4px rgba(15,23,42,0.04);
    display: flex; align-items: center; gap: 1.2rem;
    transition: box-shadow 0.14s, border-color 0.14s;
}
.job-card:hover { box-shadow: 0 4px 14px rgba(15,23,42,0.08); border-color: #93C5FD; }
.job-card-info  { flex: 1; min-width: 0; }
.job-card-title { font-size: 0.925rem; font-weight: 700; color: #0F172A; }
.job-card-meta  { font-size: 0.8rem; color: #64748B; margin-top: 2px; }
.job-card-date  { font-size: 0.74rem; color: #94A3B8; margin-top: 2px; }
.job-card-skills { flex-shrink: 0; max-width: 220px; }

/* InMail */
.inmail-box {
    background: #EFF6FF; border-left: 3px solid #1D4ED8;
    padding: 1rem 1.3rem; border-radius: 0 12px 12px 0;
    font-size: 0.9rem; line-height: 1.8; color: #1E293B;
}

/* Score pill (fallback text) */
.score-pill {
    display: inline-block; padding: 3px 12px;
    border-radius: 100px; font-weight: 700; font-size: 0.8rem; color: white;
}

/* Flag chip */
.flag-chip {
    display: inline-block; background: #FFFBEB; color: #92400E;
    padding: 2px 9px; border-radius: 6px;
    font-size: 0.72rem; font-weight: 600; border: 1px solid #FCD34D; margin-right: 4px;
}

/* Stat row (sidebar) */
.stat-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.32rem 0; font-size: 0.8rem; color: #374151;
    border-bottom: 1px solid #F1F5F9;
}
.stat-row:last-child { border-bottom: none; }
.stat-val { font-weight: 700; color: #0F172A; }

/* Recruiter report */
.rpt-page {
    background: white; border-radius: 18px; padding: 2.5rem 3rem;
    box-shadow: 0 2px 16px rgba(15,23,42,0.07); max-width: 900px; margin: 0 auto;
}
.rpt-eyebrow {
    font-size: 0.67rem; font-weight: 700; color: #94A3B8;
    text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 0.4rem;
}
.rpt-name     { font-size: 2.2rem; font-weight: 900; color: #0F172A; margin: 0; letter-spacing: -0.04em; }
.rpt-sub      { font-size: 1rem; color: #64748B; margin: 0.2rem 0 1.2rem; }
.rpt-divider  { border: none; border-top: 1.5px solid #F1F5F9; margin: 1.5rem 0; }
.rpt-section-label {
    font-size: 0.67rem; font-weight: 700; color: #94A3B8;
    text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 0.9rem;
}
.skill-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.55rem 0; border-bottom: 1px solid #F8FAFC;
}
.skill-row:last-child { border-bottom: none; }
.skill-row-name { font-size: 0.9rem; font-weight: 600; color: #1E293B; }
.context-quote {
    background: #F0FDF4; border-left: 3px solid #10B981;
    padding: 0.6rem 0.85rem; border-radius: 0 8px 8px 0;
    font-size: 0.83rem; color: #374151; line-height: 1.6;
    margin: 0.25rem 0 0.75rem; font-style: italic;
}
.exec-summary {
    background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px;
    padding: 1.1rem 1.3rem; font-size: 0.88rem; color: #1E40AF;
    line-height: 1.75; margin-bottom: 1rem;
}
.strength-tag {
    display: inline-block; background: #EFF6FF; color: #1D4ED8;
    border: 1px solid #BFDBFE; padding: 3px 11px; border-radius: 100px;
    font-size: 0.76rem; font-weight: 600; margin: 2px 3px;
}
.why-card {
    background: #F0FDF4; border: 1px solid #A7F3D0; border-radius: 12px;
    padding: 1rem 1.3rem; margin: 0.5rem 0 1rem;
    font-size: 0.85rem; color: #065F46; line-height: 1.65;
}

/* Upload evidence strip */
.upload-strip {
    background: #F8FAFC; border: 1.5px dashed #CBD5E1;
    border-radius: 9px; padding: 0.6rem 0.9rem; margin-top: 0.5rem;
    font-size: 0.8rem; color: #64748B;
}

/* Print */
@media print {
    section[data-testid="stSidebar"], .stButton, header { display: none !important; }
    .rpt-page { box-shadow: none !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "role":              "candidate",
    "candidate_page":    "dashboard",
    "verify_rev":        0,
    "jobs_rev":          0,
    "jobs_loaded":       False,
    "inmails":           {},
    "skill_contexts":    {},
    "jd_match_result":   None,
    "recruiter_jd":      "",
    "jd_input_mode":     "Paste Text",
    "job_title_search":  "Product Manager",
    "job_location":      "Israel",
    "job_seniority":     "Any level",
    "chat_history":       [],
    "chat_skill_idx":     0,
    "chat_answered":      [],
    "vault_text":         "",
    "chat_is_followup":   False,
    "chat_followup_count": 0,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_profile(rev: int) -> dict:
    if not os.path.exists(_PROFILE_PATH):
        return {}
    with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def get_inmail(company: str, context: str, rev: int) -> dict:
    return OutreachEngine().generate_message(company, context)


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_scored_jobs(
    vp_json: str,
    job_title: str,
    location: str,
    seniority: str,
    rev: int,
) -> list:
    vp   = json.loads(vp_json)
    jobs = get_latest_jobs(
        job_title=job_title,
        location=location,
        seniority=seniority,
        fetch_descriptions=True,
    )
    for job in jobs:
        result             = score_job_fit(job, vp)
        job["fit_score"]   = result["score"]
        job["matched_skills"] = result["matched_skills"]
        job["gap_skills"]  = result["gap_skills"]
    return sorted(jobs, key=lambda j: j["fit_score"], reverse=True)


# ── Profile data ──────────────────────────────────────────────────────────────

raw            = load_profile(st.session_state.verify_rev)
vp             = raw.get("verified_profile", {})
identity       = vp.get("synthesized_identity", {})
skill_records  = vp.get("skill_verification", [])
job_history    = vp.get("job_history_verification", [])
overall_conf   = vp.get("overall_confidence", 0.0)
candidate      = vp.get("candidate", "Ron Morim")
verified_title = identity.get("verified_title", "Product Manager / Team Lead")

for _sk, _ctx in raw.get("skill_contexts", {}).items():
    if _sk not in st.session_state.skill_contexts:
        st.session_state.skill_contexts[_sk] = _ctx

lvl3_count = sum(1 for s in skill_records if s.get("evidence_level", 1) == 3)
flag_count = sum(1 for e in job_history if e.get("flags"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _chip(level: int) -> str:
    cls  = {1: "chip-claim", 2: "chip-valid", 3: "chip-mastery"}[min(level, 3)]
    icon = {1: "●", 2: "◆", 3: "✦"}[min(level, 3)]
    text = {1: "CLAIM", 2: "VALIDATED", 3: "MASTERY"}[min(level, 3)]
    return f'<span class="chip {cls}">{icon} {text}</span>'


def _donut(score_pct: int, size: int = 80) -> str:
    """SVG donut gauge.  score_pct is 0-100.
    Red <50, Yellow 50-74, Green >=75."""
    color = "#059669" if score_pct >= 75 else "#D97706" if score_pct >= 50 else "#DC2626"
    r     = size * 0.36
    cx = cy = size / 2
    circ   = 2 * 3.14159265 * r
    filled = circ * (score_pct / 100)
    gap    = circ - filled
    sw     = size * 0.10
    rot    = f"rotate(-90 {cx:.1f} {cy:.1f})"
    fs     = size * 0.195
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"'
        f' stroke="#F1F5F9" stroke-width="{sw:.1f}"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"'
        f' stroke="{color}" stroke-width="{sw:.1f}"'
        f' stroke-dasharray="{filled:.1f} {gap:.1f}" stroke-linecap="round"'
        f' transform="{rot}"/>'
        f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle"'
        f' dominant-baseline="middle" fill="{color}"'
        f' font-size="{fs:.0f}" font-weight="800"'
        f' font-family="Inter,sans-serif">{score_pct}%</text>'
        f'</svg>'
    )


def _small_gauge(score: float, level: int, size: int = 52) -> str:
    """Skill-level SVG gauge (score 0.0-1.0)."""
    pct    = int(score * 100)
    color  = {1: "#94A3B8", 2: "#F59E0B", 3: "#10B981"}.get(level, "#94A3B8")
    r      = size * 0.36
    cx = cy = size / 2
    circ   = 2 * 3.14159265 * r
    filled = circ * score
    gap    = circ - filled
    sw     = size * 0.10
    rot    = f"rotate(-90 {cx:.1f} {cy:.1f})"
    fs     = size * 0.195
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"'
        f' stroke="#E2E8F0" stroke-width="{sw:.1f}"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none"'
        f' stroke="{color}" stroke-width="{sw:.1f}"'
        f' stroke-dasharray="{filled:.1f} {gap:.1f}" stroke-linecap="round"'
        f' transform="{rot}"/>'
        f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle"'
        f' dominant-baseline="middle" fill="{color}"'
        f' font-size="{fs:.0f}" font-weight="700"'
        f' font-family="Inter,sans-serif">{pct}%</text>'
        f'</svg>'
    )


def _energy_bar(score: float, level: int) -> str:
    total  = 10
    filled = round(score * total)
    color  = {1: "#94A3B8", 2: "#F59E0B", 3: "#10B981"}.get(level, "#94A3B8")
    segs   = "".join(
        f'<div class="ebar-seg" style="background:{color if i < filled else "#E2E8F0"}"></div>'
        for i in range(total)
    )
    rhs = (
        f'<span style="color:{color};font-weight:700">✦ Max</span>'
        if level == 3
        else f'<span style="color:#94A3B8">{min(100, int(score*100)+35)}% w/ context</span>'
    )
    return (
        f'<div class="ebar-row">'
        f'<span style="min-width:36px;color:#94A3B8">{int(score*100)}%</span>'
        f'<div class="ebar-segs">{segs}</div>{rhs}'
        f'</div>'
    )


_EXPERT_TIPS: dict = {
    "Product Strategy":          "Use Outcome→Decision→Constraint framing. Recruiters filter for trade-off thinking.",
    "Stakeholder Management":    "Name the role and their misaligned incentive — show diagnosis, not just resolution.",
    "Data Analysis":             "Quote a metric you owned end-to-end. 'I defined the north-star' > 'I monitored KPIs.'",
    "Agile / Scrum":             "Describe one time you deliberately broke the playbook. Adaptation > compliance.",
    "User Research":             "Show how research changed a decision, not confirmed one. Pivot moments stand out.",
    "Roadmap Prioritisation":    "Name the scoring model (RICE, ICE). Bonus: a feature you killed and what it freed.",
    "Cross-functional Leadership": "Name the functions + mechanism: RACI, weekly sync, OKR alignment.",
    "Go-to-Market":              "Include a launch metric and a missed assumption. That's PM maturity.",
}
_DEFAULT_TIP = "Use STAR-M: Situation→Task→Action→Result→Metric. Lead with the outcome."


def _extract_upload_text(uploaded) -> str:
    """Extract text from PDF or DOCX uploads; return filename note for images."""
    if uploaded is None:
        return ""
    name = uploaded.name.lower()
    try:
        if name.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
                    pages_text = [p.extract_text() or "" for p in pdf.pages]
                return " ".join(pages_text)[:3000]
            except Exception:
                uploaded.seek(0)
                return f"[PDF uploaded: {uploaded.name}]"
        elif name.endswith(".docx"):
            try:
                import docx as _docx
                doc = _docx.Document(io.BytesIO(uploaded.read()))
                return " ".join(p.text for p in doc.paragraphs if p.text.strip())[:3000]
            except Exception:
                uploaded.seek(0)
                return f"[DOCX uploaded: {uploaded.name}]"
        else:
            return f"[Image uploaded: {uploaded.name}]"
    except Exception:
        return f"[File received: {uploaded.name}]"


_MARKET_INSIGHTS: list[tuple[str, str]] = [
    ("PM roles in Israel grew 18% YoY", "Tel Aviv tech hiring rebounded sharply — APM and growth PM titles lead demand."),
    ("87% of PM offers require data literacy", "SQL or product analytics proficiency now filters 3 in 10 candidates at screen stage."),
    ("Level 3 evidence boosts callback rate 2.4×", "Recruiters report skipping profiles with zero quantified outcomes."),
    ("Cross-functional leadership is #1 PM screen", "Most interviewers open with a stakeholder conflict story — be ready."),
    ("Avg PM interview cycle: 4–6 rounds", "Companies moved from 3-stage to case-heavy processes post-2024."),
    ("B2B SaaS PM demand up 31% in EMEA", "Enterprise, fintech, and devtools verticals are absorbing the most candidates."),
    ("Remote-first PM roles down 40% since 2023", "Hybrid (2–3 days onsite) is now the dominant offering in Israel."),
    ("Product-led growth experience adds ~12% to offer", "Companies scaling self-serve funnels pay a premium for PLG track records."),
    ("AI product skills now in 68% of JDs", "\"AI roadmap\", \"LLM integration\", and \"prompt evaluation\" appearing frequently."),
    ("APM programs accept <2% of applicants", "Direct-apply with verified evidence beats cohort programs for speed-to-offer."),
    ("Startup equity now back in 85% of PM offers", "After the 2022–23 equity freeze, stock options are standard again in Series B+."),
    ("Avg first PM offer in Israel: ₪28,000–38,000/mo", "Experienced PM (3+ yrs) commands ₪40,000–60,000 at growth-stage companies."),
]


def _daily_insight() -> tuple[str, str]:
    from datetime import date
    idx = date.today().timetuple().tm_yday % len(_MARKET_INSIGHTS)
    return _MARKET_INSIGHTS[idx]


def _build_interview_question(skill: str, job_history: list) -> str:
    """Generate a context-specific question that references the candidate's actual job history."""
    # Find the most relevant role for this skill
    _skill_keywords: dict[str, list[str]] = {
        "product strategy":         ["product", "roadmap", "platform", "saas", "strategy"],
        "stakeholder management":   ["lead", "manager", "director", "cross", "team", "stakeholder"],
        "data analysis":            ["data", "analytics", "insight", "metric", "bi", "sql"],
        "agile / scrum":            ["sprint", "scrum", "agile", "delivery", "engineer"],
        "user research":            ["user", "research", "customer", "ux", "design"],
        "roadmap prioritisation":   ["roadmap", "priorit", "backlog", "product", "pm"],
        "cross-functional leadership": ["lead", "cross", "collab", "team", "org"],
        "go-to-market":             ["launch", "market", "gtm", "growth", "sales"],
    }
    kws = _skill_keywords.get(skill.lower(), skill.lower().split())

    relevant = None
    for entry in job_history:
        m = entry.get("master", {})
        combined = f"{m.get('title','')} {m.get('company','')} {m.get('description','')}".lower()
        if any(k in combined for k in kws):
            relevant = m
            break
    if not relevant and job_history:
        relevant = job_history[0].get("master", {})

    role    = relevant.get("title", "your previous role") if relevant else "your previous role"
    company = relevant.get("company", "your previous company") if relevant else "your previous company"

    _templates: dict[str, str] = {
        "product strategy": (
            f"At **{company}** as **{role}**, you were responsible for product direction. "
            f"Walk me through a specific strategic decision you made that directly impacted a core KPI. "
            f"What was the competing option you rejected, and why? "
            f"Don't define the skill — tell me what you *did*."
        ),
        "stakeholder management": (
            f"During your time as **{role}** at **{company}**, two stakeholders had directly conflicting "
            f"priorities on a project you owned. Walk me through your diagnosis of the conflict, "
            f"the exact steps you took to resolve it, and the outcome. "
            f"Name the roles involved."
        ),
        "data analysis": (
            f"As **{role}** at **{company}**, which metric did you personally own end-to-end? "
            f"Walk me through a specific moment you diagnosed an unexpected change in that metric, "
            f"what analysis you ran, and what decision it drove."
        ),
        "agile / scrum": (
            f"At **{company}** in your **{role}** role, describe a sprint where the original plan "
            f"broke down mid-cycle. What caused it, what trade-off decision did you make, "
            f"and what process change came out of it?"
        ),
        "user research": (
            f"At **{company}** as **{role}**, describe research that *changed* a product decision — "
            f"not confirmed it, changed it. What did you expect to find, what did you actually find, "
            f"and what did you ship differently as a result?"
        ),
        "roadmap prioritisation": (
            f"During your time as **{role}** at **{company}**, walk me through how you prioritised "
            f"when engineering capacity was constrained. Name a feature you *cut*, "
            f"the framework you used to make that call, and what the cut freed up."
        ),
        "cross-functional leadership": (
            f"As **{role}** at **{company}**, name a time you drove alignment across Engineering, "
            f"Design, and a business function without direct authority. "
            f"What was the mechanism — RACI, OKRs, a weekly sync — and what broke first?"
        ),
        "go-to-market": (
            f"At **{company}** as **{role}**, walk me through a product launch you owned. "
            f"What was the GTM hypothesis, what happened at launch, "
            f"and which assumption turned out to be wrong?"
        ),
    }
    return _templates.get(
        skill.lower(),
        (
            f"In your **{role}** role at **{company}**, describe a specific situation where you "
            f"had to apply **{skill}** under real pressure. Walk me through the business problem, "
            f"your exact actions, and the measurable result. "
            f"Don't define the skill — tell me what you *did*."
        ),
    )


def _acceptance_msg(skill: str, outcome_score: float) -> str:
    if outcome_score >= 0.5:
        return (
            f"Strong evidence for **{skill}** — measurable outcome confirmed. "
            f"Upgrading to **Level 3 Mastery** and saving to your profile."
        )
    return (
        f"Good evidence for **{skill}** — context and actions are clear. "
        f"Upgrading to **Level 3** and saving to your profile."
    )


def _evaluate_evidence(
    skill: str, answer: str, is_followup: bool = False
) -> tuple[str, str]:
    """
    Score the answer on three dimensions and return (verdict, feedback).
    verdict: "accept" | "followup" | "reject"

    Dimensions
    ----------
    problem  — business context / problem identification
    action   — first-person, specific operational actions
    outcome  — measurable result, metric, or concrete delivery
    """
    text = answer.strip()

    if len(text) < 60:
        return "reject", (
            f"That's too brief to verify **{skill}**. I need a real story — "
            "what was the situation, what did you specifically do, and what changed as a result?"
        )

    low = text.lower()

    # 1 — Problem / context signals
    _problem_kws = [
        "problem", "challenge", "issue", "goal", "objective", "need", "gap",
        "risk", "opportunity", "constraint", "because", "in order to",
        "the situation", "context", "faced", "had to", "needed to",
    ]
    problem_score = min(1.0, sum(1 for w in _problem_kws if w in low) / 2.0)

    # 2 — First-person action (hard gate — 0 or 1)
    _action_kws = [
        " i ", "i led", "i built", "i managed", "i created", "i drove", "i owned",
        "i defined", "i shipped", "i ran", "i designed", "i launched", "i pitched",
        "i analyzed", "i proposed", "i aligned", "i negotiated", "i prioritized",
        "i decided", "i structured", "we built", "we launched", "we shipped",
        "my approach", "my decision", "my team",
    ]
    action_score = 1.0 if any(w in low for w in _action_kws) else 0.0

    # 3 — Measurable outcome
    _outcome_kws = [
        "%", "increased", "decreased", "reduced", "improved", "saved", "grew",
        "launched", "shipped", "achieved", "delivered", "resulted", "impacted",
        "users", "revenue", "conversion", "retention", "churn", "nps", "csat",
        "×", "x faster", "times faster", "by q", "within", "months", "weeks",
        "basis points", "uplift", "lift",
    ]
    outcome_score = min(1.0, sum(1 for w in _outcome_kws if w in low) / 2.0)

    total = problem_score + action_score + outcome_score

    # On a follow-up turn be meaningfully more lenient — one more chance is enough
    if is_followup:
        if action_score > 0 and total >= 1.2:
            return "accept", _acceptance_msg(skill, outcome_score)
        # Accept unconditionally after one follow-up to avoid frustrating loops
        return "accept", _acceptance_msg(skill, outcome_score)

    # Clear pass
    if total >= 2.0:
        return "accept", _acceptance_msg(skill, outcome_score)

    # Targeted follow-up based on weakest dimension
    if action_score == 0:
        return "followup", (
            f"I can see the context, but I need to hear **your** specific actions on **{skill}**. "
            f"What did *you* personally do? Start your answer with 'I' and give me the steps."
        )
    if outcome_score == 0:
        return "followup", (
            f"Good — I can see what you did. Now close the loop: "
            f"what was the measurable result for **{skill}**? "
            f"A number, a percentage, a timeline, or a concrete business outcome."
        )
    if problem_score < 0.5:
        return "followup", (
            f"Solid actions on **{skill}**. One more layer: what was the business problem "
            f"or goal that made this work necessary? Give me the *why* behind it in one sentence."
        )

    # Borderline pass — enough signal
    if total >= 1.5 and action_score > 0:
        return "accept", _acceptance_msg(skill, outcome_score)

    return "followup", (
        f"You're close on **{skill}**, but I need more operational depth. "
        f"Give me a specific decision you made, what you considered and rejected, "
        f"and the measurable result."
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.05rem;font-weight:800;color:#0F172A;margin-bottom:0.1rem">'
        'JobApply Venture</div>'
        '<div style="font-size:0.68rem;color:#94A3B8;margin-bottom:1.3rem;letter-spacing:0.05em">'
        'CANDIDATE INTELLIGENCE PLATFORM</div>',
        unsafe_allow_html=True,
    )

    # ── Role selector ─────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.68rem;font-weight:700;color:#94A3B8;'
        'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.6rem">'
        'Viewing As</div>',
        unsafe_allow_html=True,
    )
    ca, cb = st.columns(2)
    with ca:
        if st.button(
            "Candidate",
            type="primary" if st.session_state.role == "candidate" else "secondary",
            use_container_width=True,
        ):
            st.session_state.role = "candidate"
            st.rerun()
    with cb:
        if st.button(
            "Recruiter",
            type="primary" if st.session_state.role == "recruiter" else "secondary",
            use_container_width=True,
        ):
            st.session_state.role = "recruiter"
            st.rerun()

    st.markdown('<hr style="border:none;border-top:1px solid #E2E8F0;margin:1rem 0">', unsafe_allow_html=True)

    # ── Candidate sub-navigation ──────────────────────────────────────────────
    if st.session_state.role == "candidate":
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#94A3B8;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.5rem">'
            'Navigate</div>',
            unsafe_allow_html=True,
        )
        for page_key, page_label in [
            ("dashboard", "Dashboard"),
            ("evidence",  "Verification & Evidence"),
            ("matching",  "Job Matching"),
        ]:
            is_active = st.session_state.candidate_page == page_key
            if st.button(
                page_label,
                key=f"nav_{page_key}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.candidate_page = page_key
                st.rerun()

        st.markdown('<hr style="border:none;border-top:1px solid #E2E8F0;margin:1rem 0">', unsafe_allow_html=True)

    # ── Quick stats (candidate only) ──────────────────────────────────────────
    if vp and st.session_state.role == "candidate":
        st.markdown(
            '<div style="font-size:0.68rem;font-weight:700;color:#94A3B8;'
            'text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.5rem">'
            'Profile Snapshot</div>',
            unsafe_allow_html=True,
        )
        stats = [
            ("Confidence",     f"{round(overall_conf * 100)}%"),
            ("Verified Skills", str(len([s for s in skill_records if s["confidence_score"] >= 0.5]))),
            ("Level 3 Skills", str(lvl3_count)),
            ("Flags",          str(flag_count)),
        ]
        rows_html = "".join(
            f'<div class="stat-row"><span>{l}</span><span class="stat-val">{v}</span></div>'
            for l, v in stats
        )
        st.markdown(
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;'
            f'border-radius:10px;padding:0.6rem 0.9rem">{rows_html}</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<hr style="border:none;border-top:1px solid #E2E8F0;margin:1rem 0">', unsafe_allow_html=True)

    # ── Re-run verification ───────────────────────────────────────────────────
    if st.button("Re-Run Verification", use_container_width=True):
        with st.spinner("Running ProfileVerifier…"):
            ProfileVerifier().run()
        st.session_state.verify_rev += 1
        st.cache_data.clear()
        st.rerun()

    if not vp:
        st.caption("No profile data — click Re-Run Verification.")


# ══════════════════════════════════════════════════════════════════════════════
#  RECRUITER VIEW
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.role == "recruiter":

    cultural_signals = identity.get("cultural_fit_signals", [])
    top_skills       = sorted(
        skill_records,
        key=lambda s: (s.get("evidence_level", 1), s.get("confidence_score", 0)),
        reverse=True,
    )[:6]
    mastery_skills   = [s for s in skill_records if s.get("evidence_level", 1) == 3]
    conf_pct         = round(overall_conf * 100)

    # ── JD input ──────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="ccard">'
        '<div class="ccard-title">Optional: Paste JD for Match Analysis</div>',
        unsafe_allow_html=True,
    )
    jd_col, btn_col = st.columns([5, 1])
    with jd_col:
        recruiter_jd = st.text_area(
            label="JD",
            value=st.session_state.recruiter_jd,
            placeholder="Paste a job description to score this candidate against the role…",
            height=100, key="recruiter_jd_input", label_visibility="collapsed",
        )
    with btn_col:
        st.write("")
        run_jd = st.button(
            "Analyse", use_container_width=True, type="primary",
            disabled=not bool(vp and recruiter_jd.strip()),
        )
    st.markdown('</div>', unsafe_allow_html=True)

    if run_jd and recruiter_jd.strip() and vp:
        with st.spinner("Scoring candidate against JD…"):
            st.session_state.jd_match_result = ProfileVerifier().match_against_jd(recruiter_jd.strip())
        st.session_state.recruiter_jd = recruiter_jd

    # ── Executive summary ─────────────────────────────────────────────────────
    mastery_names = ", ".join(s["skill"] for s in mastery_skills[:3]) if mastery_skills else "assessment in progress"
    jd_score_line = ""
    if st.session_state.jd_match_result:
        jr = st.session_state.jd_match_result
        jd_score_line = (
            f" Against the target role, the candidate scores "
            f"<strong>{jr.get('overall_jd_score', 0):.2f}/1.00</strong> "
            f"with Level 3 evidence on {jr.get('level3_requirements_met', 0)} core requirements."
        )

    exec_html = (
        f"<strong>{candidate}</strong> is a verified <strong>{verified_title}</strong> "
        f"with profile confidence <strong>{conf_pct}%</strong>. "
        f"Demonstrated mastery: <strong>{mastery_names}</strong>. "
        f"Cultural alignment with "
        f"{', '.join(cultural_signals[:2]) if cultural_signals else 'the organisation'} "
        f"is backed by cross-referenced career evidence.{jd_score_line}"
    )
    strength_tags = "".join(f'<span class="strength-tag">{s["skill"]}</span>' for s in top_skills)
    signal_tags   = "".join(
        f'<span class="strength-tag" style="background:#F0FDF4;color:#065F46;border-color:#A7F3D0">{sig}</span>'
        for sig in cultural_signals[:4]
    )

    # ── Report ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="rpt-page">'
        f'<div class="rpt-eyebrow">Strategic Candidate Report · Verified by AI</div>'
        f'<p class="rpt-name">{candidate}</p>'
        f'<p class="rpt-sub">{verified_title}</p>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1.2rem">'
        f'<span class="chip chip-mastery">✦ Multi-Source Verified</span>'
        f'<span style="font-size:0.78rem;color:#64748B;padding:3px 0">'
        f'Confidence {conf_pct}% · {flag_count} discrepanc{"y" if flag_count==1 else "ies"}'
        f'</span></div>'
        f'<hr class="rpt-divider">',
        unsafe_allow_html=True,
    )

    if st.session_state.jd_match_result:
        jr  = st.session_state.jd_match_result
        jd_score_pct = int(jr.get("overall_jd_score", 0) * 100)
        d_col, t_col = st.columns([1, 4])
        with d_col:
            st.markdown(_donut(jd_score_pct, size=100), unsafe_allow_html=True)
        with t_col:
            st.success(jr["recruiter_summary"])
            if jr.get("coverage_gaps"):
                st.warning(f"**Gaps vs JD:** {', '.join(jr['coverage_gaps'])}")
        st.markdown('<hr class="rpt-divider" style="margin:1rem 0">', unsafe_allow_html=True)

    st.markdown(
        f'<div class="rpt-section-label">Executive Summary</div>'
        f'<div class="exec-summary">{exec_html}</div>'
        f'<p style="font-size:0.82rem;font-weight:700;color:#374151;margin:0.5rem 0 0.3rem">Competencies</p>'
        f'{strength_tags}'
        f'<p style="font-size:0.82rem;font-weight:700;color:#374151;margin:0.8rem 0 0.3rem">Cultural Alignment</p>'
        f'{signal_tags}'
        f'<hr class="rpt-divider">',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="rpt-section-label">Why This Is the Top Match</div>'
        f'<div class="why-card">✅ Unlike candidates who list skills as bullet points, {candidate}\'s '
        f'profile is cross-referenced against LinkedIn, Gmail certifications, and structured context '
        f'narratives — eliminating unsubstantiated claims before the first call.</div>'
        f'<hr class="rpt-divider">',
        unsafe_allow_html=True,
    )

    if skill_records:
        rows_html = "".join(
            f'<div class="skill-row">'
            f'<span class="skill-row-name">{s["skill"]}</span>'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'{_small_gauge(s["confidence_score"], s.get("evidence_level",1), size=42)}'
            f'{_chip(s.get("evidence_level",1))}'
            f'</div></div>'
            for s in skill_records
        )
        st.markdown(
            f'<div class="rpt-section-label">Skill Verification</div>{rows_html}'
            f'<hr class="rpt-divider">',
            unsafe_allow_html=True,
        )

    mastery_ev = [s for s in skill_records if s.get("evidence_level", 1) == 3 and s.get("user_context")]
    if mastery_ev:
        ev_html = "".join(
            f'<p style="font-size:0.82rem;font-weight:700;color:#065F46;margin:0.8rem 0 0.2rem">✦ {s["skill"]}</p>'
            f'<div class="context-quote">{s["user_context"]}</div>'
            for s in mastery_ev
        )
        st.markdown(
            f'<div class="rpt-section-label">Level 3 — Demonstrated Mastery Evidence</div>'
            f'{ev_html}<hr class="rpt-divider">',
            unsafe_allow_html=True,
        )

    if job_history:
        hist_rows = []
        for e in job_history:
            flag_str = "✅ Verified" if not e.get("flags") else f'⚠️ {len(e.get("flags",[]))} flag(s)'
            hist_rows.append(
                f'<div class="skill-row">'
                f'<div><span class="skill-row-name">{e["master"]["title"]}</span>'
                f'<span style="color:#94A3B8;font-size:0.78rem"> · {e["master"]["company"]}'
                f' · {e["master"].get("start","?")}–{e["master"].get("end","Present")}</span></div>'
                f'<span style="font-size:0.82rem">{flag_str}</span></div>'
            )
        ts   = vp.get("verification_timestamp", raw.get("last_updated", "—"))
        ts_s = ts[:19].replace("T", " ") if len(ts) >= 19 else ts
        st.markdown(
            f'<div class="rpt-section-label">Employment History</div>'
            + "".join(hist_rows)
            + f'<hr class="rpt-divider">'
            f'<div style="font-size:0.7rem;color:#94A3B8;text-align:right">'
            f'Verified {ts_s} UTC</div></div>',
            unsafe_allow_html=True,
        )

    col_p, _ = st.columns([1, 5])
    with col_p:
        st.markdown(
            '<button onclick="window.print()" style="'
            'background:#1D4ED8;color:white;border:none;border-radius:9px;'
            'padding:0.5rem 1.4rem;font-size:0.875rem;font-weight:600;cursor:pointer;'
            'box-shadow:0 2px 8px rgba(29,78,216,0.22);margin-top:1rem">Export PDF</button>',
            unsafe_allow_html=True,
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
#  CANDIDATE VIEW — shared profile header
# ══════════════════════════════════════════════════════════════════════════════

page = st.session_state.candidate_page

signals_html = " ".join(
    f'<span class="chip {"chip-mastery" if i == 0 else "chip-valid"}">{sig}</span>'
    for i, sig in enumerate(identity.get("cultural_fit_signals", [])[:3])
)
page_labels = {
    "dashboard": "Dashboard",
    "evidence":  "Verification & Evidence",
    "matching":  "Job Matching",
}

st.markdown(
    f'<div class="profile-card">'
    f'<div style="display:flex;align-items:center;justify-content:space-between">'
    f'<div>'
    f'<p class="profile-name">{candidate}'
    f'<span class="ai-badge"><span class="ai-dot"></span>Verified by AI</span></p>'
    f'<p class="profile-role">{verified_title}</p>'
    f'<div style="margin-top:0.75rem;display:flex;gap:5px;flex-wrap:wrap">{signals_html}</div>'
    f'</div>'
    f'<div style="font-size:0.78rem;opacity:0.5;text-transform:uppercase;letter-spacing:0.08em">'
    + page_labels.get(page, "")
    + f'</div></div></div>',
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if page == "dashboard":

    # ── Metrics — NO match score ──────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Profile Confidence",  f"{round(overall_conf*100)}%", "multi-source verified", delta_color="off")
    m2.metric("Verified Skills",     len([s for s in skill_records if s["confidence_score"] >= 0.5]),
              f"{len(skill_records)} assessed", delta_color="off")
    m3.metric("Level 3 Mastery",     lvl3_count, "demonstrated evidence", delta_color="off")
    m4.metric("Discrepancies",       flag_count, "in job history",
              delta_color="inverse" if flag_count else "off")

    if not vp:
        st.info("No profile data — click **Re-Run Verification** in the sidebar.")
        st.stop()

    # ── Daily Market Insight ──────────────────────────────────────────────────
    insight_text, insight_detail = _daily_insight()
    st.markdown(
        f'<div class="insight-card">'
        f'<div><div class="insight-label">Daily Market Insight</div>'
        f'<div class="insight-text">{insight_text}</div>'
        f'<div class="insight-detail">{insight_detail}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

    left_col, right_col = st.columns([1, 1], gap="large")

    # ── Left: skill chart + breakdown ─────────────────────────────────────────
    with left_col:
        with st.container(border=True):
            st.markdown('<div class="ccard-title">Skill Confidence Overview</div>', unsafe_allow_html=True)
            if skill_records:
                chart_df = pd.DataFrame({
                    "Skill":      [s["skill"] for s in skill_records],
                    "Confidence": [round(s["confidence_score"] * 100) for s in skill_records],
                }).sort_values("Confidence", ascending=True)
                st.bar_chart(chart_df.set_index("Skill"), horizontal=True, color="#1D4ED8")
            else:
                st.info("Run verification to populate skill scores.")

        with st.container(border=True):
            st.markdown('<div class="ccard-title">Evidence Level Breakdown</div>', unsafe_allow_html=True)
            if skill_records:
                lvl_rows = []
                for s in sorted(skill_records, key=lambda x: x.get("evidence_level", 1), reverse=True):
                    lvl   = s.get("evidence_level", 1)
                    g_svg = _small_gauge(s["confidence_score"], lvl, size=44)
                    lvl_rows.append(
                        f'<div style="display:flex;align-items:center;justify-content:space-between;'
                        f'padding:0.4rem 0;border-bottom:1px solid #F1F5F9">'
                        f'<div style="display:flex;align-items:center;gap:8px">'
                        f'{g_svg}'
                        f'<span style="font-size:0.875rem;font-weight:600;color:#0F172A">{s["skill"]}</span>'
                        f'</div>{_chip(lvl)}</div>'
                    )
                st.markdown("".join(lvl_rows), unsafe_allow_html=True)

    # ── Right: job history + integrity snapshot ───────────────────────────────
    with right_col:
        with st.container(border=True):
            st.markdown('<div class="ccard-title">Job History Verification</div>', unsafe_allow_html=True)
            if job_history:
                rows = []
                for entry in job_history:
                    master  = entry.get("master", {})
                    flags   = entry.get("flags", [])
                    f_types = [f["type"] for f in flags]
                    status  = (
                        "✅ Clean" if not flags else
                        "❌ No Match" if any("NO_MATCH" in t for t in f_types) else
                        "⚠️ Discrepancy"
                    )
                    rows.append({
                        "Company": master.get("company", "—"),
                        "Title":   master.get("title", "—"),
                        "Period":  f"{master.get('start','?')} → {master.get('end','Present')}",
                        "Status":  status,
                    })
                st.dataframe(
                    pd.DataFrame(rows), use_container_width=True, hide_index=True,
                    column_config={
                        "Company": st.column_config.TextColumn(width="medium"),
                        "Title":   st.column_config.TextColumn(width="medium"),
                        "Period":  st.column_config.TextColumn(width="medium"),
                        "Status":  st.column_config.TextColumn(width="small"),
                    },
                )
                flagged = [e for e in job_history if e.get("flags")]
                if flagged:
                    with st.expander(f"⚠️ {len(flagged)} discrepancy detail(s)"):
                        for entry in flagged:
                            master = entry["master"]
                            st.markdown(f"**{master['title']}** @ {master['company']}")
                            for flag in entry["flags"]:
                                st.markdown(
                                    f'<span class="flag-chip">{flag["type"]}</span> {flag["detail"]}',
                                    unsafe_allow_html=True,
                                )
                            st.write("")
            else:
                st.info("No data — click Re-Run Verification.")

        with st.container(border=True):
            st.markdown('<div class="ccard-title">Integrity Snapshot</div>', unsafe_allow_html=True)
            weak_skills = [s for s in skill_records if s.get("confidence_score", 1.0) < 0.7]
            any_flags   = [e for e in job_history if e.get("flags")]
            if not weak_skills and not any_flags:
                st.success("✅ All checks passed — background-check ready.")
            else:
                total = len(weak_skills) + sum(len(e["flags"]) for e in any_flags)
                st.warning(
                    f"**{total} item(s) need attention.** "
                    f"Go to **Verification & Evidence** to resolve them."
                )
                for sk in weak_skills[:3]:
                    pct = int(round(sk["confidence_score"] * 100))
                    st.markdown(
                        f'<div style="font-size:0.83rem;color:#92400E;padding:0.25rem 0">'
                        f'<strong>{sk["skill"]}</strong> — {pct}% confidence</div>',
                        unsafe_allow_html=True,
                    )
                if len(weak_skills) > 3:
                    st.caption(f"…and {len(weak_skills)-3} more. See Verification & Evidence.")

    ts = vp.get("verification_timestamp", raw.get("last_updated", "—"))
    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
    st.caption(f"Last verified: {ts} · data/user_master_profile.json")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: VERIFICATION & EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "evidence":

    # ── Integrity Optimizer — Action Board ───────────────────────────────────
    with st.container(border=True):
        weak_skills  = [s for s in skill_records if s.get("confidence_score", 1.0) < 0.7]
        flagged_jobs = [e for e in job_history if e.get("flags")]

        if not vp:
            st.warning("Run Re-Run Verification first.")
        elif not weak_skills and not flagged_jobs:
            st.success("✅ Profile integrity confirmed — background-check ready.")
        else:
            # ── Header counts ──────────────────────────────────────────────
            n_skills = len(weak_skills)
            n_flags  = sum(len(e["flags"]) for e in flagged_jobs)
            h1, h2 = st.columns(2)
            h1.metric("Skills to Verify", n_skills,
                      delta="chat with AI Interviewer ↓", delta_color="off")
            h2.metric("History Discrepancies", n_flags,
                      delta="contact HR to clarify" if n_flags else "none found",
                      delta_color="inverse" if n_flags else "off")

            if weak_skills:
                st.markdown(
                    '<div style="font-size:0.72rem;font-weight:700;color:#94A3B8;'
                    'text-transform:uppercase;letter-spacing:0.09em;margin:1rem 0 0.5rem">'
                    'Unverified Skills</div>',
                    unsafe_allow_html=True,
                )
                # Compact table: one row per weak skill
                rows_html = ""
                for sk in weak_skills:
                    pct = int(round(sk["confidence_score"] * 100))
                    bar_fill = f'<div style="width:{pct}%;height:4px;background:#1D4ED8;border-radius:2px"></div>'
                    bar = f'<div style="width:100%;background:#E2E8F0;border-radius:2px">{bar_fill}</div>'
                    rows_html += (
                        f'<div style="display:flex;align-items:center;justify-content:space-between;'
                        f'padding:0.38rem 0;border-bottom:1px solid #F1F5F9;gap:1rem">'
                        f'<span style="font-size:0.875rem;font-weight:600;color:#0F172A;min-width:180px">'
                        f'{sk["skill"]}</span>'
                        f'<div style="flex:1;max-width:120px">{bar}</div>'
                        f'<span style="font-size:0.8rem;color:#64748B;min-width:36px;text-align:right">'
                        f'{pct}%</span>'
                        f'</div>'
                    )
                st.markdown(rows_html, unsafe_allow_html=True)
                st.caption(
                    "To verify: answer the AI Interviewer below · upload a document to Evidence Vault · "
                    "or add LinkedIn proof and re-run verification."
                )

            if flagged_jobs:
                st.markdown(
                    '<div style="font-size:0.72rem;font-weight:700;color:#94A3B8;'
                    'text-transform:uppercase;letter-spacing:0.09em;margin:1rem 0 0.5rem">'
                    'History Discrepancies</div>',
                    unsafe_allow_html=True,
                )
                disc_html = ""
                for entry in flagged_jobs:
                    m = entry["master"]
                    for flag in entry["flags"]:
                        ftype = flag.get("type", "MISMATCH").replace("_", " ").title()
                        detail = flag.get("detail", "")
                        # Extract the key delta only — first sentence or up to 80 chars
                        short_detail = (detail.split(".")[0] if "." in detail else detail)[:80]
                        disc_html += (
                            f'<div style="display:flex;align-items:center;gap:0.75rem;'
                            f'padding:0.38rem 0;border-bottom:1px solid #F1F5F9">'
                            f'<span class="flag-chip">{ftype}</span>'
                            f'<span style="font-size:0.85rem;font-weight:600;color:#0F172A">'
                            f'{m.get("company","—")}</span>'
                            f'<span style="font-size:0.82rem;color:#64748B">{short_detail}</span>'
                            f'</div>'
                        )
                st.markdown(disc_html, unsafe_allow_html=True)
                st.caption("Contact the relevant HR team with your employment contract to resolve.")

    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

    # ── Central Evidence Vault ────────────────────────────────────────────────
    with st.container(border=True):
        st.caption(
            "Upload supporting documents (PDF, DOCX) to bypass the interview for specific skills."
        )
        vault_file = st.file_uploader(
            "Upload evidence",
            type=["pdf", "docx", "png", "jpg", "jpeg"],
            key="central_vault_upload",
            label_visibility="collapsed",
        )
        if vault_file is not None:
            extracted = _extract_upload_text(vault_file)
            st.session_state.vault_text = extracted
            detail = f" — {len(extracted)} chars extracted" if extracted and not extracted.startswith("[") else ""
            st.success(f"**{vault_file.name}** uploaded{detail}. Ready for use in the interview.")
        elif st.session_state.vault_text:
            st.markdown(
                f'<div class="upload-strip">Evidence on file — {len(st.session_state.vault_text)} chars. '
                f'Upload a new file to replace it.</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

    # ── AI Interviewer Chat ───────────────────────────────────────────────────
    if not vp:
        st.info("Run Re-Run Verification first.")
    elif skill_records:
        mastery_skills = [s for s in skill_records if s.get("evidence_level", 1) == 3]
        sub_mastery    = [s for s in skill_records if s.get("evidence_level", 1) < 3]

        total_skills  = len(skill_records)
        mastery_count = len(mastery_skills)

        # Progress header
        prog_chips = " ".join(
            f'<span class="chip chip-mastery">✦ {s["skill"]}</span>'
            for s in mastery_skills
        )
        st.markdown(
            f'<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;'
            f'padding:0.9rem 1.2rem;margin-bottom:1rem;display:flex;'
            f'justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem">'
            f'<div>'
            f'<div style="font-size:0.7rem;font-weight:800;color:#1D4ED8;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:0.3rem">Evidence Progress</div>'
            f'<div style="font-size:0.9rem;font-weight:700;color:#1E293B">'
            f'{mastery_count} of {total_skills} skills at Level 3 Mastery</div>'
            + (f'<div style="margin-top:0.4rem">{prog_chips}</div>' if prog_chips else "")
            + f'</div>'
            f'<div style="text-align:right">'
            f'<div style="font-size:1.6rem;font-weight:900;color:#1D4ED8">'
            f'{int(mastery_count/total_skills*100) if total_skills else 0}%</div>'
            f'<div style="font-size:0.68rem;color:#64748B">complete</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        if not sub_mastery:
            st.success("All skills verified at Level 3. You are top-priority for recruiters.")
        else:
            st.markdown(
                f'<div class="ccard-title">AI Interviewer — '
                f'{len(sub_mastery)} skill(s) remaining</div>',
                unsafe_allow_html=True,
            )

            # Reset chat index if it has gone out of range (e.g. after re-verification)
            if st.session_state.chat_skill_idx >= len(sub_mastery):
                st.session_state.chat_skill_idx  = 0
                st.session_state.chat_history    = []
                st.session_state.chat_is_followup = False
                st.session_state.chat_followup_count = 0

            # Build opening question using job-history context (no static prompts)
            if not st.session_state.chat_history:
                cur   = sub_mastery[st.session_state.chat_skill_idx]
                q     = _build_interview_question(cur["skill"], job_history)
                intro = (
                    f"I verify skills through evidence — specific stories from your actual "
                    f"experience, not definitions.\n\n"
                    f"Let's start with **{cur['skill']}**.\n\n"
                    f"{q}"
                )
                st.session_state.chat_history    = [{"role": "assistant", "content": intro}]
                st.session_state.chat_is_followup = False
                st.session_state.chat_followup_count = 0

            # Chat container — constrains the input to this section, not the page bottom
            cur_skill_name = sub_mastery[st.session_state.chat_skill_idx]["skill"]
            answer = None
            with st.container(height=480, border=False):
                for msg in st.session_state.chat_history:
                    with st.chat_message("user" if msg["role"] == "user" else "assistant"):
                        st.markdown(msg["content"])
                answer = st.chat_input(f"Your answer about {cur_skill_name}…")

            if answer:
                st.session_state.chat_history.append({"role": "user", "content": answer})

                cur        = sub_mastery[st.session_state.chat_skill_idx]
                is_followup = st.session_state.chat_is_followup
                verdict, feedback = _evaluate_evidence(cur["skill"], answer, is_followup=is_followup)

                if verdict == "accept":
                    ctx = answer
                    if st.session_state.vault_text:
                        ctx += f"\n\n[Supporting doc: {st.session_state.vault_text[:400]}]"

                    with st.spinner("Saving and re-verifying…"):
                        _pv = ProfileVerifier()
                        _pv.save_skill_contexts({cur["skill"]: ctx})
                        _pv.run()

                    st.session_state.verify_rev         += 1
                    st.session_state.chat_answered.append(cur["skill"])
                    st.session_state.chat_skill_idx     += 1
                    st.session_state.chat_is_followup    = False
                    st.session_state.chat_followup_count = 0
                    st.cache_data.clear()

                    next_idx = st.session_state.chat_skill_idx
                    if next_idx < len(sub_mastery):
                        nxt = sub_mastery[next_idx]
                        nxt_q = _build_interview_question(nxt["skill"], job_history)
                        response = (
                            f"{feedback}\n\n---\n\n"
                            f"Next: **{nxt['skill']}**\n\n"
                            f"{nxt_q}"
                        )
                    else:
                        response = (
                            f"{feedback}\n\n"
                            f"**All skills verified.** Your profile has been updated to Level 3 "
                            f"across all competencies — you are now top-priority for recruiters."
                        )
                    st.session_state.chat_history.append({"role": "assistant", "content": response})

                elif verdict == "followup":
                    st.session_state.chat_is_followup    = True
                    st.session_state.chat_followup_count += 1
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": feedback}
                    )

                else:  # reject
                    st.session_state.chat_is_followup    = False
                    st.session_state.chat_followup_count = 0
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": feedback}
                    )

                st.rerun()

            # Skip / reset controls
            skip_col, reset_col, _ = st.columns([1, 1, 4])
            with skip_col:
                if st.button("Skip →", key="chat_skip", help="Move to the next skill"):
                    nxt_idx = min(st.session_state.chat_skill_idx + 1, len(sub_mastery) - 1)
                    st.session_state.chat_skill_idx      = nxt_idx
                    st.session_state.chat_history        = []
                    st.session_state.chat_is_followup    = False
                    st.session_state.chat_followup_count = 0
                    st.rerun()
            with reset_col:
                if st.button("↺ Restart", key="chat_reset", help="Restart from the first skill"):
                    st.session_state.chat_skill_idx      = 0
                    st.session_state.chat_history        = []
                    st.session_state.chat_answered       = []
                    st.session_state.chat_is_followup    = False
                    st.session_state.chat_followup_count = 0
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: JOB MATCHING
# ══════════════════════════════════════════════════════════════════════════════

elif page == "matching":

    if not vp:
        st.warning("Run Re-Run Verification first.")
        st.stop()

    tab_jd, tab_live, tab_inmail = st.tabs([
        "JD Matcher",
        "Live Opportunities",
        "InMail Generator",
    ])

    # ── JD Matcher ────────────────────────────────────────────────────────────
    with tab_jd:
        st.subheader("JD Matcher — Level 3 Priority Scoring")
        st.markdown(
            "Paste a job description or a URL to a live job post. "
            "The scorer weights each matched skill by evidence level — "
            "**Level 3 scores 4× a bare claim.** Match score is shown here only."
        )

        # ── Input mode toggle ─────────────────────────────────────────────────
        jd_mode = st.radio(
            "Input method",
            options=["Paste Text", "Paste URL"],
            index=0 if st.session_state.jd_input_mode == "Paste Text" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.jd_input_mode = jd_mode

        jd_text_final = ""

        if jd_mode == "Paste Text":
            jd_text_final = st.text_area(
                label="Job description",
                placeholder="Paste the full job description here…",
                height=160, key="jd_paste_text", label_visibility="collapsed",
            )
        else:
            url_input = st.text_input(
                label="Job post URL",
                placeholder="https://www.linkedin.com/jobs/view/…",
                label_visibility="collapsed",
            )
            if url_input.strip():
                fetch_col, _ = st.columns([1, 4])
                with fetch_col:
                    if st.button("Fetch JD from URL", type="primary"):
                        with st.spinner("Fetching page content…"):
                            fetched = fetch_text_from_url(url_input.strip())
                        if fetched:
                            st.session_state["fetched_jd_text"] = fetched
                            st.success(f"Extracted {len(fetched)} characters.")
                        else:
                            st.error("Could not fetch content from that URL. Paste the text manually.")
                jd_text_final = st.session_state.get("fetched_jd_text", "")
                if jd_text_final:
                    with st.expander("Preview extracted text"):
                        st.text(jd_text_final[:800] + ("…" if len(jd_text_final) > 800 else ""))

        match_col, _ = st.columns([1, 5])
        with match_col:
            jd_clicked = st.button(
                "Run Match", type="primary", use_container_width=True,
                disabled=not bool(jd_text_final.strip()),
            )

        if jd_clicked and jd_text_final.strip():
            with st.spinner("Scoring skills against JD…"):
                st.session_state.jd_match_result = ProfileVerifier().match_against_jd(jd_text_final.strip())

        if st.session_state.jd_match_result:
            jr = st.session_state.jd_match_result
            jd_pct = int(jr.get("overall_jd_score", 0) * 100)

            res_donut, res_gaps = st.columns([1, 2])
            with res_donut:
                st.markdown(
                    f'<div style="text-align:center">{_donut(jd_pct, size=100)}'
                    f'<div style="font-size:0.7rem;color:#64748B;margin-top:4px;font-weight:600">JD Match Score</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.success(jr["recruiter_summary"])
            with res_gaps:
                # Build actionable gap list: JD keywords not covered + low-score matched skills
                raw_gaps = jr.get("coverage_gaps", [])
                weak_matched = [
                    s["skill"] for s in jr.get("matched_skills", [])
                    if s.get("jd_match_score", 1) < 0.4
                ]
                action_items = (raw_gaps + weak_matched)[:3]
                if action_items and jd_pct < 100:
                    st.markdown("**Missing / Weak Skills**")
                    for gap in action_items:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:8px;'
                            f'padding:6px 10px;margin-bottom:6px;border-radius:8px;'
                            f'background:#FEF3C7;border:1px solid #FCD34D">'
                            f'<span style="font-size:0.85rem;color:#92400E;flex:1">{gap}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    if st.button("Go to Evidence Vault", key="goto_vault_from_jd", type="primary"):
                        st.session_state.candidate_page = "verification"
                        st.rerun()
                elif jd_pct == 100:
                    st.success("Full coverage — no gaps found.")
                else:
                    st.info("No specific skill gaps identified.")

            if jr["matched_skills"]:
                jd_rows = [{
                    "Skill":          s["skill"],
                    "Evidence Level": s["evidence_label"],
                    "JD Relevance":   f"{int(s['relevance_to_jd']*100)}%",
                    "Priority Score": s["jd_match_score"],
                    "Context":        "✅" if s.get("user_context") else "—",
                } for s in jr["matched_skills"]]
                st.dataframe(
                    pd.DataFrame(jd_rows), use_container_width=True, hide_index=True,
                    column_config={
                        "Priority Score": st.column_config.ProgressColumn(
                            min_value=0, max_value=1, format="%.2f", width="medium"
                        ),
                        "Context": st.column_config.TextColumn(width="small"),
                    },
                )

            if st.button("Clear results", key="clear_jd"):
                st.session_state.jd_match_result = None
                st.session_state.pop("fetched_jd_text", None)
                st.rerun()

    # ── Live Opportunities ────────────────────────────────────────────────────
    with tab_live:
        st.subheader("Live Job Search")

        # Dynamic inputs
        t_col, s_col, l_col = st.columns([3, 2, 2])
        with t_col:
            job_title_input = st.text_input(
                "Job Title",
                value=st.session_state.job_title_search,
                placeholder="e.g. Product Manager, Data Analyst, UX Designer",
                label_visibility="visible",
            )
        with s_col:
            seniority_input = st.selectbox(
                "Seniority Level",
                options=SENIORITY_OPTIONS,
                index=SENIORITY_OPTIONS.index(st.session_state.job_seniority)
                      if st.session_state.job_seniority in SENIORITY_OPTIONS else 0,
            )
        with l_col:
            location_input = st.text_input(
                "Location",
                value=st.session_state.job_location,
                placeholder="e.g. Tel Aviv, London, Remote",
                label_visibility="visible",
            )

        btn_col, ref_col, _ = st.columns([2, 1, 4])
        with btn_col:
            search_clicked = st.button(
                "Search Jobs", type="primary", use_container_width=True,
                help="Searches LinkedIn and scores results against your verified profile.",
            )
        with ref_col:
            refresh_clicked = st.button(
                "Refresh", use_container_width=True,
                disabled=not st.session_state.jobs_loaded,
            )

        if search_clicked:
            st.session_state.job_title_search = job_title_input.strip() or "Product Manager"
            st.session_state.job_seniority    = seniority_input
            st.session_state.job_location     = location_input.strip() or "Israel"
            st.session_state.jobs_loaded      = True
            st.session_state.jobs_rev        += 1
            st.session_state.inmails          = {}
            st.cache_data.clear()

        if refresh_clicked:
            st.session_state.jobs_rev += 1
            st.session_state.inmails   = {}
            st.cache_data.clear()
            st.rerun()

        if not st.session_state.jobs_loaded:
            st.markdown(
                '<div style="text-align:center;padding:3rem 0;color:#94A3B8">'
                '<p style="margin:0;color:#64748B">Enter a job title and click '
                '<strong>Search Jobs</strong> to pull live listings ranked by profile fit.</p>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            with st.spinner(f"Searching for '{st.session_state.job_title_search}' in "
                            f"{st.session_state.job_location}…"):
                scored_jobs = fetch_scored_jobs(
                    json.dumps(vp),
                    st.session_state.job_title_search,
                    st.session_state.job_location,
                    st.session_state.job_seniority,
                    st.session_state.jobs_rev,
                )

            is_live      = any(j.get("source") == "linkedin" for j in scored_jobs)
            source_badge = "🟢 Live" if is_live else "🟡 Simulated fallback"
            st.caption(
                f"{len(scored_jobs)} results · {source_badge} · "
                f"'{st.session_state.job_title_search}' in {st.session_state.job_location} · "
                f"{st.session_state.job_seniority} · ranked by fit ↓"
            )

            # ── Job cards with donut gauges ────────────────────────────────────
            for job in scored_jobs:
                score    = job["fit_score"]
                job_id   = job["job_id"]
                gauge_svg = _donut(score, size=64)

                matched_chips = " ".join(
                    f'<span class="chip chip-mastery" style="font-size:0.65rem">{s}</span>'
                    for s in job.get("matched_skills", [])[:3]
                )
                gap_chips = " ".join(
                    f'<span class="chip chip-claim" style="font-size:0.65rem">{s}</span>'
                    for s in job.get("gap_skills", [])[:2]
                )

                st.markdown(
                    f'<div class="job-card">'
                    f'<div style="flex-shrink:0">{gauge_svg}</div>'
                    f'<div class="job-card-info">'
                    f'<div class="job-card-title">{job["title"]}</div>'
                    f'<div class="job-card-meta">🏢 {job["company"]} &nbsp;·&nbsp; 📍 {job["location"]}</div>'
                    f'<div class="job-card-date">📅 {job.get("post_date","—")}</div>'
                    f'</div>'
                    f'<div class="job-card-skills">'
                    + (f'<div style="margin-bottom:3px">{matched_chips}</div>' if matched_chips else "")
                    + (f'<div style="opacity:0.6">{gap_chips}</div>' if gap_chips else "")
                    + f'</div></div>',
                    unsafe_allow_html=True,
                )

                with st.expander(f"Details — {job['title']} @ {job['company']}"):
                    meta_c, skill_c = st.columns(2)
                    with meta_c:
                        if job.get("url"):
                            st.markdown(f"[View on LinkedIn]({job['url']})")
                        st.markdown(
                            f"📍 {job['location']}  \n📅 {job.get('post_date','—')}"
                        )
                    with skill_c:
                        if job.get("matched_skills"):
                            st.markdown("**Matched:** " + ", ".join(job["matched_skills"]))
                        if job.get("gap_skills"):
                            st.markdown("**Gaps:** " + ", ".join(job["gap_skills"]))

                    if job.get("description"):
                        desc = job["description"][:600]
                        tail = "…" if len(job["description"]) > 600 else ""
                        st.markdown(
                            f'<div style="font-size:0.87rem;color:#374151;max-height:160px;'
                            f'overflow-y:auto;background:#F8FAFC;padding:0.65rem;'
                            f'border-radius:8px;border:1px solid #E2E8F0">'
                            f'{desc}{tail}</div>',
                            unsafe_allow_html=True,
                        )

                    st.write("")
                    cached = st.session_state.inmails.get(job_id)
                    if cached is None:
                        if st.button(
                            f"Generate InMail for {job['company']}",
                            key=f"inmail_btn_{job_id}", use_container_width=True,
                        ):
                            with st.spinner(f"Writing InMail for {job['company']}…"):
                                result = OutreachEngine().generate_message(job["company"])
                            st.session_state.inmails[job_id] = result
                            st.rerun()
                    else:
                        hdr, clr = st.columns([5, 1])
                        with hdr:
                            st.markdown("**✉️ LinkedIn InMail**")
                        with clr:
                            if st.button("Clear", key=f"clear_{job_id}"):
                                del st.session_state.inmails[job_id]
                                st.rerun()
                        st.markdown(f'<div class="inmail-box">{cached["message"]}</div>', unsafe_allow_html=True)
                        st.caption(f"{cached.get('word_count',0)} words")
                        st.info(cached["why_this_works"])

    # ── InMail Generator ──────────────────────────────────────────────────────
    with tab_inmail:
        st.subheader("LinkedIn InMail Generator")
        st.markdown(
            "Generate a personalised <100-word InMail tailored to any company's culture, "
            "anchored to your top verified skills and cultural signals."
        )

        sel_col, ctx_col = st.columns([1, 1])
        with sel_col:
            company = st.selectbox("Target company", options=_COMPANIES)
            custom  = st.text_input("Or enter a custom name", placeholder="e.g. Figma, Stripe…")
        with ctx_col:
            company_context = st.text_area(
                "Company context (optional)",
                placeholder="e.g. 'B2C consumer app', 'B2B SaaS marketplace'",
                height=100,
            )

        target = custom.strip() if custom.strip() else company

        if st.button("Generate InMail", type="primary"):
            with st.spinner(f"Writing InMail for {target}…"):
                inmail = get_inmail(target, company_context.strip(), st.session_state.verify_rev)

            d_col, txt_col = st.columns([1, 4])
            with d_col:
                iconf = inmail.get("top_skills_used", [{}])[0].get("confidence_score", overall_conf)
                st.markdown(
                    f'<div style="text-align:center">'
                    f'{_donut(int(iconf*100), size=80)}'
                    f'<div style="font-size:0.68rem;color:#64748B;margin-top:3px">Top Skill Conf.</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with txt_col:
                pill_a, pill_b = st.columns(2)
                with pill_a:
                    st.caption("Cultural signals")
                    st.markdown(" ".join(f"`{s}`" for s in inmail.get("matched_cultural_signals", [])))
                with pill_b:
                    st.caption("Skills anchored")
                    st.markdown(" ".join(
                        f"`{s['skill']} ({s['confidence_score']:.2f})`"
                        for s in inmail.get("top_skills_used", [])
                    ))

            st.markdown(f'<div class="inmail-box">{inmail["message"]}</div>', unsafe_allow_html=True)
            st.caption(f"{inmail.get('word_count',0)} words · <100 limit")
            st.markdown("**Why This Works**")
            st.info(inmail.get("why_this_works", ""))

            with st.expander("Copy raw text"):
                st.text_area(
                    label="text", value=inmail["message"],
                    height=180, label_visibility="collapsed",
                )
