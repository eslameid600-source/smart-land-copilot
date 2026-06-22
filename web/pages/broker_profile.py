"""
صفحة ملف الوسيط
================
عرض تفاصيل الوسيط وإحصائياته وأراضيه وأرباحه.
"""

import requests
import streamlit as st

st.set_page_config(page_title="ملف الوسيط", layout="wide")
st.title("📋 ملف الوسيط")

API_BASE = "http://localhost:8000/api"

# ──────────────────────────────────────────
# إدخال معرّف الوسيط
# ──────────────────────────────────────────
with st.sidebar:
    st.header("بحث عن وسيط")
    broker_id_input = st.text_input("معرّف الوسيط (UUID)", placeholder="مثال: abc-123...")
    search_button = st.button("بحث")

if not search_button or not broker_id_input:
    st.info("أدخل معرّف الوسيط في الشريط الجانبي للبحث")
    st.stop()

broker_id = broker_id_input.strip()
if not broker_id:
    st.warning("يرجى إدخال معرّف الوسيط")
    st.stop()

# ──────────────────────────────────────────
# جلب بيانات الوسيط
# ──────────────────────────────────────────
try:
    resp = requests.get(f"{API_BASE}/brokers/{broker_id}", timeout=10)
    if resp.status_code != 200:
        st.error(f"خطأ: {resp.status_code} — {resp.json().get('detail', '')}")
        st.stop()
    
    data = resp.json()
    if not data.get("success"):
        st.error("استجابة غير صالحة من الخادم")
        st.stop()
    
    profile = data.get("profile", {})
    broker = profile.get("broker", {})
    
    if not broker:
        st.error("الوسيط غير موجود")
        st.stop()
    
    # ──────────────────────────────────────────
    #Header: معلومات الوسيط
    # ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader(broker.get("full_name", "بدون اسم"))
        st.write(f"**الكود:** `{broker.get('broker_code', '')}`")
        st.write(f"**البريد:** {broker.get('email', 'غير محدد')}")
        st.write(f"**الهاتف:** {broker.get('phone_number', 'غير محدد')}")
    with col2:
        st.write(f"**الشركة:** {broker.get('company_name', '—')}")
        st.write(f"**رخصة:** {broker.get('license_number', 'غير محدد')}")
        st.write(f"**الحالة:** {broker.get('status', 'غير معروف')}")
        st.write(f"**التحقق:** {'✅ نعم' if broker.get('verified_by_admin') else '❌ لا'}")
    with col3:
        st.metric("نسبة العمولة", f"{broker.get('default_commission_rate', 0)}%")
        st.metric("عدد الصفقات", broker.get("total_deals_closed", 0))
        st.metric("إجمالي العمولات", f"{broker.get('total_commission_earned_egp', 0):,.2f} ج.م")
    
    if broker.get("bio"):
        st.write(f"**نبذة:** {broker['bio']}")
    if broker.get("specialization"):
        st.write(f"**التخصصات:** {', '.join(broker['specialization'])}")
    
    st.divider()
    
    # ──────────────────────────────────────────
    # إحصائيات
    # ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("تعيينات نشطة", profile.get("active_assignments_count", 0))
        st.metric("إجمالي التعيينات", profile.get("total_assignments_count", 0))
    with col2:
        st.metric("أراضي مُدارة", profile.get("lands_managed_count", 0))
    with col3:
        earnings = profile.get("earnings", {})
        st.metric("أرباح معلقة", f"{earnings.get('total_pending_egp', 0):,.2f} ج.م")
        st.metric("أرباح مدفوعة", f"{earnings.get('total_paid_egp', 0):,.2f} ج.م")
    
    st.divider()
    
    # ──────────────────────────────────────────
    # الأراضي التي يديرها
    # ──────────────────────────────────────────
    st.subheader("🏗️ الأراضي التي يديرها هذا الوسيط")
    lands_resp = requests.get(f"{API_BASE}/brokers/{broker_id}/lands", timeout=10)
    if lands_resp.status_code == 200:
        lands_data = lands_resp.json()
        lands = lands_data.get("lands", [])
        if lands:
            for land in lands:
                with st.expander(f"🏠 {land.get('land_name', 'أرض')} — {land.get('governorate', '')}"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"**المساحة:** {land.get('total_area_sqm', 0)} م²")
                        st.write(f"**السعر للمتر:** {land.get('price_per_sqm_egp', 0):,.2f} ج.م")
                        st.write(f"**السعر الإجمالي:** {land.get('total_price_egp', 0):,.2f} ج.م")
                    with col_b:
                        st.write(f"**الحالة:** {land.get('investment_status', 'غير محدد')}")
                        st.write(f"**العمولة:** {land.get('commission_percent', '—')}%")
                        st.write(f"**تاريخ الإدراج:** {land.get('listed_at', '')[:10] if land.get('listed_at') else '—'}")
        else:
            st.info("لا توجد أراضي مُدارة لهذا الوسيط حالياً")
    else:
        st.warning("لا يمكن جلب بيانات الأراضي")
    
    st.divider()
    
    # ──────────────────────────────────────────
    # معاملات العمولات
    # ──────────────────────────────────────────
    st.subheader("💰 معاملات العمولات")
    txs_resp = requests.get(f"{API_BASE}/brokers/{broker_id}/earnings", timeout=10)
    if txs_resp.status_code == 200:
        txs_data = txs_resp.json()
        earnings = txs_data.get("earnings", {})
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("معلقة", f"{earnings.get('total_pending_egp', 0):,.2f} ج.م")
        with col2:
            st.metric("مدفوعة", f"{earnings.get('total_paid_egp', 0):,.2f} ج.م")
        with col3:
            st.metric("ملغاة", f"{earnings.get('total_cancelled_egp', 0):,.2f} ج.م")
        
        st.caption(f"عدد المعاملات: {earnings.get('transactions_count', 0)}")
    else:
        st.warning("لا يمكن جلب بيانات الأرباح")

except Exception as e:
    st.error(f"خطأ في جلب البيانات: {e}")

# ──────────────────────────────────────────
# أزرار إضافية
# ──────────────────────────────────────────
st.divider()
if st.button("🔄 تحديث البيانات"):
    st.rerun()
if st.button("→ العودة لقائمة الوسطاء"):
    st.switch_page("broker_community.py")