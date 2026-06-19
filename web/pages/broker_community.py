"""
صفحة مجتمع الوسطاء
======================
عرض قائمة الوسطاء النشطين مع إمكانية البحث.
"""

import streamlit as st
import requests

API_BASE = "http://localhost:8000/api"

def show_broker_community():
    """عرض صفحة مجتمع الوسطاء."""
    st.title("🏢 مجتمع الوسطاء")
    
    # ──────────────────────────────────────────
    # البحث
    # ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        search_query = st.text_input("🔍 بحث بالاسم أو الكود", placeholder="أحمد محمد...")
    with col2:
        specialization = st.selectbox(
            "التخصص",
            ["", "سكني", "تجاري", "صناعي", "زراعي", "سياحي"]
        )
    with col3:
        limit = st.number_input("عدد النتائج", min_value=5, max_value=100, value=20)

    if st.button("بحث") or search_query:
        try:
            params = {"limit": limit}
            if search_query:
                params["query"] = search_query
            if specialization:
                params["specialization"] = specialization
            
            resp = requests.get(f"{API_BASE}/brokers/community", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                brokers = data.get("brokers", [])
                st.write(f"**عدد النتائج:** {len(brokers)}")
                
                for broker in brokers:
                    with st.expander(f"👤 {broker['full_name']} — {broker['broker_code']}"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**البريد:** {broker.get('email', 'غير محدد')}")
                            st.write(f"**الهاتف:** {broker.get('phone_number', 'غير محدد')}")
                            st.write(f"**الشركة:** {broker.get('company_name', '—')}")
                        with col_b:
                            st.write(f"**نسبة العمولة:** {broker['default_commission_rate']}%")
                            st.write(f"**عدد الصفقات:** {broker['total_deals_closed']}")
                            st.write(f"**إجمالي العمولات:** {broker['total_commission_earned_egp']:,.2f} ج.م")
                        
                        if broker.get('specialization'):
                            st.write(f"**التخصصات:** {', '.join(broker['specialization'])}")
                        if broker.get('bio'):
                            st.write(f"**نبذة:** {broker['bio']}")
                        
                        # زر لعرض الملف الكامل
                        if st.button(f"عرض الملف الكامل", key=f"profile_{broker['id']}"):
                            st.session_state['view_broker_id'] = broker['id']
                            st.rerun()
            else:
                st.error(f"خطأ في جلب البيانات: {resp.status_code}")
        except Exception as e:
            st.error(f"لا يمكن الاتصال بالخادم: {e}")

    # ──────────────────────────────────────────
    # ملف الوسيط الكامل
    # ──────────────────────────────────────────
    if 'view_broker_id' in st.session_state and st.session_state.get('view_broker_id'):
        broker_id = st.session_state['view_broker_id']
        st.divider()
        st.subheader(f"📋 ملف الوسيط: {broker_id}")
        
        try:
            resp = requests.get(f"{API_BASE}/brokers/{broker_id}", timeout=10)
            if resp.status_code == 200:
                profile = resp.json().get("profile", {})
                broker = profile.get("broker", {})
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("عدد التعيينات النشطة", profile.get("active_assignments_count", 0))
                    st.metric("إجمالي التعيينات", profile.get("total_assignments_count", 0))
                with col2:
                    st.metric("الأراضي المُدارة", profile.get("lands_managed_count", 0))
                    st.metric("إجمالي الصفقات", broker.get("total_deals_closed", 0))
                with col3:
                    earnings = profile.get("earnings", {})
                    st.metric("الأرباح المعلقة", f"{earnings.get('total_pending_egp', 0):,.2f} ج.م")
                    st.metric("الأرباح المدفوعة", f"{earnings.get('total_paid_egp', 0):,.2f} ج.م")
                
                if st.button("إغلاق الملف"):
                    del st.session_state['view_broker_id']
                    st.rerun()
            else:
                st.error("الوسيط غير موجود")
        except Exception as e:
            st.error(f"خطأ: {e}")