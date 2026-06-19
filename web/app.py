"""
Smart Land Copilot — تطبيق Streamlit الرئيسي
==============================================
يضم جميع الصفحات والتنقل بينها.
"""

import streamlit as st

# إعداد الصفحة الرئيسية
st.set_page_config(
    page_title="Smart Land Copilot",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ──────────────────────────────────────────
# الشريط الجانبي
# ──────────────────────────────────────────
with st.sidebar:
    st.title("🏠 Smart Land Copilot")
    st.caption("المنصة الذكية لإدارة الأراضي")
    
    page = st.radio(
        "التنقل",
        options=[
            "الرئيسية",
            "تسجيل أرض جديدة",
            "مجتمع الوسطاء",
            "ملف الوسيط",
        ],
        label_visibility="collapsed"
    )
    
    st.divider()
    st.write("**معلومات المستخدم**")
    st.write(f"👤 {st.session_state.get('user_name', 'زائر')}")
    st.write(f"🎭 {st.session_state.get('user_role', 'غير محدد')}")

# ──────────────────────────────────────────
# توجيه الصفحات
# ──────────────────────────────────────────
if page == "الرئيسية":
    st.title("🏠 الصفحة الرئيسية")
    st.write("مرحباً بك في منصة Smart Land Copilot")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("إجمالي الأراضي", "1,234", "+12")
    with col2:
        st.metric("الوسطاء النشطين", "56", "+3")
    with col3:
        st.metric("المبيعات هذا الشهر", "₵ 2.5M", "+15%")
    
    st.divider()
    st.subheader("آخر الأراضي المُعلنة")
    # يمكن جلب البيانات من API
    st.info("قم بتسجيل أرض جديدة للبدء")

elif page == "تسجيل أرض جديدة":
    # استيراد صفحة تسجيل الأرض
    from web.pages.land_registration import show_land_registration
    show_land_registration()

elif page == "مجتمع الوسطاء":
    # استيراد صفحة مجتمع الوسطاء
    from web.pages.broker_community import show_broker_community
    show_broker_community()

elif page == "ملف الوسيط":
    # استيراد صفحة ملف الوسيط
    from web.pages.broker_profile import show_broker_profile
    show_broker_profile()

# ──────────────────────────────────────────
# الذيل
# ──────────────────────────────────────────
st.divider()
st.caption("© 2026 Smart Land Copilot — جميع الحقوق محفوظة")