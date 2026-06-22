"""
Smart Land Management Copilot — Authentication & Onboarding View
================================================================
Multi-role account selection and broker document validation.
"""
import streamlit as st
from models.user import UserRole

from services.user_service import get_user_service


def render_auth_view():
    """
    Render the role-based account selection and onboarding interface.
    This is the first view a user sees upon entering the application.
    """
    user_svc = get_user_service()
    if 'current_user_id' in st.session_state:
        user = user_svc.get_user(st.session_state['current_user_id'])
        if user:
            _render_logged_in_state(user, user_svc)
            return
    st.markdown('<div style="text-align:center;margin:40px 0 30px;"><h2 style="color:#ecf0f1;margin:0;">Welcome to Smart Land Copilot</h2><p style="color:#8b949e;margin-top:8px;">Select your account persona to continue</p></div>', unsafe_allow_html=True)
    role_cards = [{'role': UserRole.BUYER_INVESTOR, 'title': 'Buyer / Investor', 'arabic': 'مشتري / مستثمر', 'icon': '📈', 'color': '#27ae60', 'desc': 'Track land pricing trends, infrastructure availability, and manage your investment portfolio with multi-use classification analysis.'}, {'role': UserRole.SELLER_OWNER, 'title': 'Seller / Owner', 'arabic': 'بائع / مالك', 'icon': '🏠', 'color': '#2980b9', 'desc': 'Register properties for Sale, Rent, or Portfolio Tracking. View the transparent Financial Cleared Matrix with Egyptian tax deductions.'}, {'role': UserRole.CERTIFIED_BROKER, 'title': 'Certified Broker', 'arabic': 'سمسار معتمد', 'icon': '💼', 'color': '#f39c12', 'desc': 'Manage listings, track delegated properties, and earn commissions. Requires brokerage license verification.'}]
    cols = st.columns(3)
    for i, card in enumerate(role_cards):
        with cols[i]:
            st.markdown(f"""\n                <div style="\n                    background: linear-gradient(135deg, {card['color']}10, {card['color']}05);\n                    border: 1px solid {card['color']}40;\n                    border-radius: 12px;\n                    padding: 24px 16px;\n                    text-align: center;\n                    cursor: pointer;\n                    transition: all 0.2s;\n                    height: 100%;\n                ">\n                    <div style="font-size:48px;margin-bottom:12px;">{card['icon']}</div>\n                    <h4 style="color:{card['color']};margin:0;">{card['title']}</h4>\n                    <div style="color:#888;font-size:14px;margin-top:4px;">{card['arabic']}</div>\n                    <p style="color:#bbb;font-size:13px;margin-top:12px;line-height:1.5;">{card['desc']}</p>\n                </div>\n                """, unsafe_allow_html=True)
    st.markdown('<br>', unsafe_allow_html=True)
    with st.form('login_form'):
        st.markdown('### Quick Login')
        lc1, lc2 = st.columns(2)
        with lc1:
            selected_role = st.selectbox('Account Type', options=[r.value for r in UserRole], index=0, key='login_role')
        with lc2:
            users = user_svc.list_users(role=UserRole(selected_role))
            user_options = {f'{u.full_name} ({u.user_id})': u.user_id for u in users}
            selected_user = st.selectbox('Select Account', options=list(user_options.keys()), key='login_user')
        submitted = st.form_submit_button('Enter Dashboard', type='primary', use_container_width=True)
        if submitted and selected_user in user_options:
            st.session_state['current_user_id'] = user_options[selected_user]
            st.rerun()
    st.divider()
    with st.expander('Create New Account', expanded=False):
        with st.form('create_account_form'):
            cc1, cc2 = st.columns(2)
            with cc1:
                new_name = st.text_input('Full Name', key='new_acc_name')
                new_email = st.text_input('Email', key='new_acc_email')
                new_phone = st.text_input('Phone', key='new_acc_phone')
            with cc2:
                new_role = st.selectbox('Account Type', options=[r.value for r in UserRole], key='new_acc_role')
                new_company = st.text_input('Company Name (optional)', key='new_acc_company')
            create_submitted = st.form_submit_button('Create Account', type='secondary', use_container_width=True)
            if create_submitted:
                if not new_name:
                    st.error('Full name is required.')
                else:
                    user = user_svc.create_account(full_name=new_name, role=UserRole(new_role), email=new_email, phone=new_phone, company_name=new_company)
                    st.success(f'Account created: {user.user_id} — {user.full_name} ({new_role})')
                    st.rerun()

def _render_logged_in_state(user, user_svc):
    """Render the logged-in user state with account info and switch/logout."""
    role_colors = {UserRole.BUYER_INVESTOR: '#27ae60', UserRole.SELLER_OWNER: '#2980b9', UserRole.CERTIFIED_BROKER: '#f39c12'}
    color = role_colors.get(user.role, '#888')
    st.markdown(f"""\n        <div style="\n            background: linear-gradient(135deg, {color}15, {color}08);\n            border: 1px solid {color}40;\n            border-radius: 12px;\n            padding: 20px 24px;\n            display: flex;\n            justify-content: space-between;\n            align-items: center;\n        ">\n            <div>\n                <div style="font-size:13px;color:#888;text-transform:uppercase;letter-spacing:0.5px;">\n                    Current Session\n                </div>\n                <div style="font-size:20px;font-weight:700;color:{color};margin-top:4px;">\n                    {user.full_name}\n                </div>\n                <div style="color:#bbb;font-size:13px;margin-top:2px;">\n                    {user.role.value} {(f'| {user.company_name}' if user.company_name else '')}\n                    {(f'| {user.email}' if user.email else '')}\n                </div>\n                {("<div style='color:#e74c3c;font-size:12px;margin-top:6px;font-weight:600;'>Broker Status: " + user.broker_verification_status.value + '</div>' if user.role == UserRole.CERTIFIED_BROKER and (not user.is_broker_verified) else '')}\n            </div>\n            <div style="display:flex;gap:8px;">\n                <button onclick="document.querySelector('[data-testid=&quot;stFormSubmitButton&quot;]')?.click()"\n                    style="background:#e74c3c;color:white;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;">\n                    Switch Account\n                </button>\n            </div>\n        </div>\n        """, unsafe_allow_html=True)
    if user.role == UserRole.CERTIFIED_BROKER and (not user.is_broker_verified):
        st.markdown('<br>', unsafe_allow_html=True)
        status = user_svc.get_broker_verification_status(user.user_id)
        if status:
            missing = status['missing']
            pending = status['pending_verification']
            if missing:
                st.warning(f"Missing required documents: {', '.join(missing)}")
            if pending:
                st.info(f"Pending verification: {', '.join(pending)}")
            if status['documents']:
                for doc in status['documents']:
                    doc_color = '#27ae60' if doc['verified'] else '#f39c12' if not doc['rejection_reason'] else '#e74c3c'
                    doc_status = 'Verified' if doc['verified'] else 'Rejected' if doc['rejection_reason'] else 'Pending Review'
                    st.markdown(f"""\n                        <div style="background:#1a1a2e;border-left:3px solid {doc_color};\n                                    padding:10px 14px;border-radius:4px;margin-bottom:6px;">\n                            <b>{doc['type']}</b> — {doc['name'] or 'No filename'}\n                            <span style="float:right;color:{doc_color};font-weight:600;">{doc_status}</span><br>\n                            <small>Uploaded: {doc['uploaded']} | ID: {doc['document_id']}</small>\n                            {("<br><small style='color:#e74c3c;'>Rejection: " + doc['rejection_reason'] + '</small>' if doc['rejection_reason'] else '')}\n                        </div>\n                        """, unsafe_allow_html=True)
            st.markdown('<br>', unsafe_allow_html=True)
            st.markdown('**Admin Verification Controls (Demo)**')
            for doc in status['documents']:
                if not doc['verified'] and (not doc['rejection_reason']):
                    vc1, vc2 = st.columns(2)
                    with vc1:
                        if st.button(f"Approve {doc['document_id']}", key=f"approve_{doc['document_id']}"):
                            user_svc.verify_broker_document(user.user_id, doc['document_id'], approved=True)
                            st.success(f"Document {doc['document_id']} approved")
                            st.rerun()
                    with vc2:
                        if st.button(f"Reject {doc['document_id']}", key=f"reject_{doc['document_id']}"):
                            user_svc.verify_broker_document(user.user_id, doc['document_id'], approved=False, rejection_reason='Document unclear or incomplete')
                            st.error(f"Document {doc['document_id']} rejected")
                            st.rerun()
    if st.button('Switch Account / Logout', key='logout_btn'):
        if 'current_user_id' in st.session_state:
            del st.session_state['current_user_id']
        st.rerun()