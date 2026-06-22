"""
Smart Land Management Copilot — Advertising Engine View
========================================================
AI-Driven Cross-Channel Advertising Engine UI.

Option A: AI Copilot Ad Generation (Free/Self-Service)
  View and manage AI-generated marketing copy for social media
  and SEO metatags.

Option B: Platform-Managed Funded Campaigns (Paid Promotion)
  Deploy and track paid advertising campaigns across channels.
"""

import pandas as pd
import streamlit as st
from data.land_database import get_all_lands

from services.advertising_service import AdChannel, get_advertising_service
from services.user_service import get_user_service
from ui.components import render_metric_card, render_section_header


def render_advertising_view():
    """Render the full AI-Driven Cross-Channel Advertising Engine view."""
    ad_svc = get_advertising_service()
    user_svc = get_user_service()

    render_section_header(
        "AI-Driven Cross-Channel Advertising Engine",
        subtitle="Generate optimized marketing copy and deploy targeted campaigns",
    )

    # ── Campaign Metrics ──
    stats = ad_svc.get_campaign_stats()

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        render_metric_card("Total Campaigns", str(stats["total_campaigns"]), color="#2980b9")
    with m2:
        render_metric_card("Active", str(stats["active"]), color="#27ae60")
    with m3:
        render_metric_card("Total Impressions", f"{stats['total_impressions']:,}", color="#f39c12")
    with m4:
        render_metric_card("Total Clicks", f"{stats['total_clicks']:,}", color="#9b59b6")
    with m5:
        render_metric_card("Leads Generated", str(stats["total_leads"]), color="#e74c3c")

    st.markdown("---")

    sub_tabs = st.tabs([
        "Campaigns Overview",
        "Create Campaign",
        "View Generated Ads",
        "Campaign Performance",
    ])

    # ── TAB 1: CAMPAIGNS OVERVIEW ──
    with sub_tabs[0]:
        campaigns = ad_svc.list_campaigns()

        if not campaigns:
            st.info("No advertising campaigns created yet.")
        else:
            for camp in campaigns:
                _render_campaign_card(camp)

    # ── TAB 2: CREATE CAMPAIGN ──
    with sub_tabs[1]:
        lands = get_all_lands()
        land_options = {
            f"{land['Land_ID']} — {land['Region_City']} ({land['Allowed_Usage']})": land
            for land in lands
        }

        st.markdown(
            '<div style="background:#1a1a2e;border:1px solid #2980b9;padding:12px;'
            'border-radius:8px;margin-bottom:16px;">'
            '<span style="color:#2980b9;font-weight:600;">Two Promotion Paths:</span><br>'
            '<b>Option A:</b> AI Copilot Ad Generation (Free/Self-Service) — '
            'Instantly generate optimized marketing copy for Social Media and SEO.<br>'
            '<b>Option B:</b> Platform-Managed Funded Campaigns (Paid) — '
            'Deploy targeted ads across search engines and social networks.</div>',
            unsafe_allow_html=True,
        )

        with st.form("create_campaign_form"):
            cc1, cc2 = st.columns(2)
            with cc1:
                sel_land_key = st.selectbox(
                    "Select Land",
                    list(land_options.keys()),
                    key="ad_land_sel",
                )
                campaign_type = st.radio(
                    "Campaign Type",
                    options=["ai_copilot", "platform_managed"],
                    format_func=lambda x: (
                        "Option A: AI Copilot Ad Generation (Free)" if x == "ai_copilot"
                        else "Option B: Platform-Managed Funded Campaigns (Paid)"
                    ),
                    key="ad_type_sel",
                )
            with cc2:
                target_audience = st.text_input(
                    "Target Audience Description",
                    value="Investors and developers in Egyptian real estate",
                    key="ad_audience",
                )
                selected_channels = st.multiselect(
                    "Target Channels",
                    options=[c.value for c in AdChannel],
                    default=[AdChannel.FACEBOOK.value, AdChannel.LINKEDIN.value, AdChannel.SEO_META.value],
                    key="ad_channels",
                )

            # Budget field only for paid campaigns
            budget = 0.0
            if campaign_type == "platform_managed":
                budget = st.number_input(
                    "Campaign Budget (EGP)",
                    min_value=1000,
                    max_value=10_000_000,
                    value=50000,
                    step=5000,
                    format="%d",
                    key="ad_budget",
                )
                # Broker delegation option
                current_user = _get_seller_or_broker(user_svc)
                if current_user:
                    verified_brokers = [
                        u for u in user_svc.list_users()
                        if u.role.value == "Certified Broker" and u.is_broker_verified
                    ]
                    if verified_brokers:
                        delegate_to_broker = st.checkbox(
                            "Delegate budget to a verified broker",
                            value=False,
                            key="ad_delegate_cb",
                        )
                        if delegate_to_broker:
                            broker_opts = {f"{b.full_name} ({b.user_id})": b.user_id for b in verified_brokers}
                            delegated_broker = st.selectbox(
                                "Select Broker",
                                list(broker_opts.keys()),
                                key="ad_broker_sel",
                            )
                        else:
                            delegated_broker = None
                    else:
                        delegated_broker = None

            if st.form_submit_button("Create & Generate", type="primary"):
                land = land_options[sel_land_key]
                broker_id = broker_opts.get(delegated_broker) if campaign_type == "platform_managed" and delegate_to_broker else None

                channels = [AdChannel(ch) for ch in selected_channels]
                camp = ad_svc.create_campaign(
                    land_id=land["Land_ID"],
                    seller_id=st.session_state.get("current_user_id", ""),
                    campaign_type=campaign_type,
                    target_channels=channels,
                    target_audience=target_audience,
                    total_budget_egp=budget,
                    delegated_to_broker_id=broker_id,
                )

                if campaign_type == "ai_copilot":
                    ad_svc.generate_ai_copilot_ads(camp.campaign_id, land)
                    ad_svc.activate_campaign(camp.campaign_id)

                st.success(f"Campaign {camp.campaign_id} created successfully!")
                st.rerun()

    # ── TAB 3: VIEW GENERATED ADS ──
    with sub_tabs[2]:
        ai_campaigns = ad_svc.list_campaigns(campaign_type="ai_copilot")
        if not ai_campaigns:
            st.info("No AI-generated campaigns yet.")
        else:
            for camp in ai_campaigns:
                st.markdown(
                    f"""
                    <div style="background:#1a1a2e;border-left:4px solid #2980b9;
                                padding:16px;border-radius:8px;margin-bottom:16px;">
                        <div style="display:flex;justify-content:space-between;">
                            <b style="color:#2980b9;">{camp.campaign_id}</b>
                            <span style="color:#888;">{camp.land_id} | {camp.status.value}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Social Media Copy
                if camp.generated_social_copy:
                    st.markdown("**Generated Social Media Copy:**")
                    for channel, copy in camp.generated_social_copy.items():
                        with st.expander(f"{channel}", expanded=False):
                            st.code(copy, language=None)

                # SEO Meta Tags
                if camp.generated_seo_meta:
                    st.markdown("**Generated SEO Meta Tags:**")
                    seo_rows = []
                    for key, value in camp.generated_seo_meta.items():
                        seo_rows.append({"Tag": key, "Content": value})
                    st.dataframe(pd.DataFrame(seo_rows), use_container_width=True, hide_index=True)

    # ── TAB 4: CAMPAIGN PERFORMANCE ──
    with sub_tabs[3]:
        paid_campaigns = ad_svc.list_campaigns(campaign_type="platform_managed")
        if not paid_campaigns:
            st.info("No paid campaigns to analyze.")
        else:
            for camp in paid_campaigns:
                ctr = (camp.clicks / max(camp.impressions, 1)) * 100
                lead_rate = (camp.leads_generated / max(camp.clicks, 1)) * 100
                budget_used_pct = (camp.spent_egp / max(camp.total_budget_egp, 1)) * 100

                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                with mc1:
                    render_metric_card("Impressions", f"{camp.impressions:,}", color="#2980b9")
                with mc2:
                    render_metric_card("Clicks", f"{camp.clicks:,}", color="#f39c12", delta=f"CTR: {ctr:.2f}%")
                with mc3:
                    render_metric_card("Leads", str(camp.leads_generated), color="#27ae60", delta=f"Rate: {lead_rate:.1f}%")
                with mc4:
                    render_metric_card("Spent", f"{camp.spent_egp:,.0f} EGP", color="#e74c3c")
                with mc5:
                    render_metric_card("Budget Used", f"{budget_used_pct:.1f}%", color="#9b59b6")


def _render_campaign_card(camp) -> None:
    """Render an advertising campaign as a styled card."""
    type_colors = {
        "ai_copilot": "#2980b9",
        "platform_managed": "#f39c12",
    }
    status_colors = {
        "Draft": "#888", "Active": "#27ae60", "Paused": "#f39c12",
        "Completed": "#2980b9", "Cancelled": "#e74c3c",
    }
    color = type_colors.get(camp.campaign_type, "#888")
    sc = status_colors.get(camp.status.value, "#888")

    channels_str = ", ".join(c.value for c in camp.target_channels) if camp.target_channels else "None"
    delegated = ""
    if camp.delegated_to_broker_id:
        delegated = f'<div style="color:#f39c12;font-size:12px;margin-top:4px;">Budget delegated to broker: {camp.delegated_to_broker_id}</div>'

    st.markdown(
        f"""
        <div style="background:#1a1a2e;border-left:4px solid {color};
                    padding:14px;border-radius:8px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <b style="color:{color};">{camp.campaign_id}</b>
                    <span style="background:{sc}22;color:{sc};padding:2px 10px;
                                 border-radius:12px;font-size:12px;margin-left:8px;">
                        {camp.status.value}
                    </span>
                </div>
                <small style="color:#888;">{camp.created_at[:10]}</small>
            </div>
            <div style="color:#bbb;margin-top:6px;">
                Land: {camp.land_id} | Type: {camp.campaign_type.replace('_', ' ').title()}
                {f" | Budget: {camp.total_budget_egp:,.0f} EGP" if camp.total_budget_egp > 0 else ""}
            </div>
            <div style="color:#999;font-size:12px;margin-top:4px;">
                Channels: {channels_str}
            </div>
            {delegated}
            {"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:8px;'>"
             f"<div><small style='color:#888;'>Impressions</small><br><b>{camp.impressions:,}</b></div>"
             f"<div><small style='color:#888;'>Clicks</small><br><b>{camp.clicks:,}</b></div>"
             f"<div><small style='color:#888;'>Leads</small><br><b>{camp.leads_generated}</b></div>"
             "</div>" if (camp.impressions > 0 or camp.clicks > 0) else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_seller_or_broker(user_svc):
    uid = st.session_state.get("current_user_id")
    if not uid:
        return None
    user = user_svc.get_user(uid)
    if user and user.role.value in ("Seller/Owner", "Certified Broker"):
        return user
    return None