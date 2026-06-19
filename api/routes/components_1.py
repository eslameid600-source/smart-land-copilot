"""
============================================================
Smart Land Management Copilot — Shared UI Components
============================================================
Reusable UI components used across multiple views.

Design Pattern: Component Pattern, DRY
SOLID: SRP — each function renders one concern
============================================================
"""
from __future__ import annotations
import streamlit as st
from typing import Any, Dict, List, Optional
from models.models.land import USAGE_COLORS, ALL_UTILITIES

def compat_color(percent: float) -> str:
    """Return a hex color from red (0%) to green (100%)."""
    if percent >= 80:
        return '#27ae60'
    elif percent >= 60:
        return '#f39c12'
    elif percent >= 40:
        return '#e67e22'
    else:
        return '#e74c3c'

def compat_label(percent: float) -> str:
    """Return a text label for compatibility level."""
    if percent >= 80:
        return 'Excellent Match'
    elif percent >= 60:
        return 'Good Match'
    elif percent >= 40:
        return 'Partial Match'
    else:
        return 'Poor Match'

def render_metric_card(label: str, value: str, color: str='#ecf0f1') -> None:
    """Render a single metric card in the sidebar."""
    st.markdown(f'<div style="background:{color}22;border-left:3px solid {color};padding:6px 10px;border-radius:4px;margin-bottom:4px;"><div style="font-size:11px;color:#aaa;">{label}</div><div style="font-size:16px;font-weight:bold;color:{color};">{value}</div></div>', unsafe_allow_html=True)

def render_map_legend() -> None:
    """Render the map usage-type legend."""
    st.markdown('**Map Legend**')
    for usage, color in USAGE_COLORS.items():
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0;">\n                <span style="width:12px;height:12px;border-radius:50%;background:{color};display:inline-block;"></span>\n                <span style="font-size:13px;"><b>{usage}</b></span>\n            </div>', unsafe_allow_html=True)
    st.markdown('<div style="display:flex;align-items:center;gap:8px;margin:2px 0;">\n            <span style="width:12px;height:12px;border-radius:50%;border:2px dashed #f39c12;display:inline-block;"></span>\n            <span style="font-size:13px;"><b>Auction</b> (dashed ring)</span>\n        </div>', unsafe_allow_html=True)

def render_compatibility_bar(percent: float, height: int=22) -> None:
    """Render a colored compatibility progress bar."""
    color = compat_color(percent)
    st.markdown(f'<div style="background:#1e1e1e;border-radius:8px;height:{height}px;overflow:hidden;">\n            <div style="height:100%;width:{min(percent, 100)}%;background:{color};\n            border-radius:8px;display:flex;align-items:center;justify-content:flex-end;\n            padding-right:8px;font-size:11px;font-weight:bold;color:#fff;\n            text-shadow:1px 1px 2px rgba(0,0,0,0.6);transition:width 0.4s ease;">\n                {percent}%\n            </div>\n        </div>', unsafe_allow_html=True)

def render_auction_card(land: Dict[str, Any]) -> None:
    """Render a styled auction opportunity card."""
    st.markdown(f"""<div style="background:linear-gradient(135deg,#3d1f00,#5c2e00);\n        border:2px solid #f39c12;border-radius:10px;padding:12px;margin:8px 0;">\n            <span style="display:inline-block;background:#f39c12;color:#000;\n            font-weight:bold;font-size:11px;padding:2px 8px;border-radius:10px;">\n                AUCTION\n            </span>\n            <h4 style="color:#f39c12;margin:6px 0 4px 0;font-size:14px;">\n                {land.get('Land_ID', '')} — {land.get('Region_City', '')}\n            </h4>\n            <p style="margin:2px 0;font-size:12px;color:#e0d0b0;">\n                Date: {land.get('Auction_Date', 'N/A')}<br>\n                Starting: {land.get('Starting_Price_Per_Sqm_EGP', 0):,} EGP/m2 |\n                Area: {land.get('Total_Area_Sqm', 0):,} sqm\n            </p>\n        </div>""", unsafe_allow_html=True)

def render_match_card(result: Dict[str, Any], index: int) -> None:
    """Render a single matchmaking result card."""
    compat = result.get('Compatibility_Percent', 0)
    is_auction = result.get('is_auction', False)
    risk = result.get('investment_risk', 'Medium')
    rec = result.get('recommendation', 'Consider')
    land_id = result.get('Land_ID', '')
    risk_colors = {'Low': '#27ae60', 'Medium': '#f39c12', 'High': '#e74c3c'}
    risk_color = risk_colors.get(risk, '#95a5a6')
    rec_colors = {'Strong Buy': '#27ae60', 'Buy': '#2ecc71', 'Consider': '#f39c12', 'Avoid': '#e74c3c'}
    rec_color = rec_colors.get(rec, '#95a5a6')
    card_bg = '#2d1a00' if is_auction else '#1a1a2e'
    border_color = '#f39c12' if is_auction else compat_color(compat)
    header = f'#{index + 1} — {land_id}'
    if is_auction:
        header += ' <span style="background:#f39c12;color:#000;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:bold;">AUCTION</span>'
    strengths = result.get('strengths', [])
    weaknesses = result.get('weaknesses', [])
    strengths_html = ''
    if strengths:
        items = ''.join((f'<li>{s}</li>' for s in strengths[:3]))
        strengths_html = f'<p style="margin:4px 0 2px 0;font-size:11px;"><b style="color:#27ae60;">Strengths:</b></p><ul style="margin:0;padding-left:16px;font-size:11px;color:#bbb;">{items}</ul>'
    weaknesses_html = ''
    if weaknesses:
        items = ''.join((f'<li>{w}</li>' for w in weaknesses[:3]))
        weaknesses_html = f'<p style="margin:4px 0 2px 0;font-size:11px;"><b style="color:#e74c3c;">Weaknesses:</b></p><ul style="margin:0;padding-left:16px;font-size:11px;color:#bbb;">{items}</ul>'
    breakdown = result.get('score_breakdown', [])
    breakdown_html = ''
    if breakdown:
        rows = ''
        for sb in breakdown:
            pct = sb.get('percentage', 0)
            c = '#27ae60' if sb.get('passed', False) else '#e74c3c'
            rows += f"""<div style="display:flex;align-items:center;gap:6px;margin:2px 0;"><span style="font-size:10px;color:#888;width:90px;">{sb.get('category', '')}</span><div style="flex:1;background:#1e1e1e;border-radius:4px;height:8px;overflow:hidden;"><div style="width:{min(pct, 100)}%;height:100%;background:{c};border-radius:4px;"></div></div><span style="font-size:10px;color:#aaa;width:40px;text-align:right;">{pct:.0f}%</span></div>"""
        breakdown_html = f'<div style="margin-top:6px;">{rows}</div>'
    st.markdown(f"""<div style="background:{card_bg};border:1px solid {border_color};\n        border-radius:10px;padding:12px;margin:8px 0;">\n            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">\n                <span style="font-size:14px;font-weight:bold;color:#ecf0f1;">{header}</span>\n                <div style="display:flex;gap:6px;">\n                    <span style="background:{risk_color}22;color:{risk_color};\n                    padding:2px 8px;border-radius:10px;font-size:10px;font-weight:bold;">{risk}</span>\n                    <span style="background:{rec_color}22;color:{rec_color};\n                    padding:2px 8px;border-radius:10px;font-size:10px;font-weight:bold;">{rec}</span>\n                </div>\n            </div>\n            <div style="font-size:12px;color:#bbb;margin-bottom:6px;">\n                {result.get('Governorate', '')} — {result.get('Region_City', '')} |\n                {result.get('Total_Area_Sqm', 0):,} sqm |\n                {result.get('Price_Per_Sqm_EGP', 0):,} EGP/m2\n            </div>\n            <div style="margin-bottom:6px;">\n                <span style="font-size:12px;color:#aaa;">Compatibility: </span>\n                <span style="font-size:16px;font-weight:bold;color:{compat_color(compat)};">{compat}%</span>\n            </div>\n            {strengths_html}\n            {weaknesses_html}\n            {breakdown_html}\n        </div>""", unsafe_allow_html=True)