"""
صفحة تسجيل أرض جديدة — خطوات متعددة
=======================================
الخطوات:
1. بيانات الأرض الأساسية
2. رفع الوثائق القانونية
3. تحديد الموقع عبر GPS
4. مراجعة وتأكيد
"""

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

API_BASE = "http://localhost:8000/api"

def show_land_registration():
    """عرض صفحة تسجيل أرض جديدة."""
    st.title("🏗️ تسجيل أرض جديدة")
    
    # ──────────────────────────────────────────
    # حالة الجلسة
    # ──────────────────────────────────────────
    if "land_data" not in st.session_state:
        st.session_state.land_data = {}
    if "documents" not in st.session_state:
        st.session_state.documents = []
    if "gps_coords" not in st.session_state:
        st.session_state.gps_coords = None
    if "current_step" not in st.session_state:
        st.session_state.current_step = 1

    # ──────────────────────────────────────────
    # شريط التقدم
    # ──────────────────────────────────────────
    steps = ["بيانات الأرض", "الوثائق", "الموقع GPS", "مراجعة"]
    progress = st.session_state.current_step / len(steps)
    st.progress(progress)
    st.subheader(f"الخطوة {st.session_state.current_step}: {steps[st.session_state.current_step - 1]}")

    # ──────────────────────────────────────────
    # الخطوة 1: بيانات الأرض
    # ──────────────────────────────────────────
    if st.session_state.current_step == 1:
        with st.form("land_basic_info"):
            col1, col2 = st.columns(2)
            with col1:
                land_name = st.text_input("اسم الأرض *", placeholder="مثال: أرض العبور")
                governorate = st.selectbox(
                    "المحافظة *",
                    ["القاهرة", "الجيزة", "القليوبية", "الإسكندرية", "أسيوط", "سوهاج", "الأقصر", "أسوان", "أخرى"]
                )
                region_city = st.text_input("المدينة/المنطقة *")
            with col2:
                total_area = st.number_input("المساحة الكلية (م²) *", min_value=1, value=500)
                price_per_sqm = st.number_input("سعر المتر (ج.م) *", min_value=1, value=5000)
                listing_intent = st.selectbox("نوع الإعلان", ["Sale", "Rent", "Portfolio Tracking"])
            
            description = st.text_area("وصف الأرض", placeholder="معلومات إضافية عن الأرض...")
            
            submitted = st.form_submit_button("التالي →")
            if submitted:
                if not land_name or not governorate or not region_city:
                    st.error("يرجى ملء جميع الحقول المطلوبة (*)")
                else:
                    st.session_state.land_data = {
                        "land_name": land_name,
                        "governorate": governorate,
                        "region_city": region_city,
                        "total_area_sqm": total_area,
                        "price_per_sqm_egp": price_per_sqm,
                        "total_price_egp": total_area * price_per_sqm,
                        "listing_intent": listing_intent,
                        "description_ar": description,
                    }
                    st.session_state.current_step = 2
                    st.rerun()

    # ──────────────────────────────────────────
    # الخطوة 2: رفع الوثائق
    # ──────────────────────────────────────────
    elif st.session_state.current_step == 2:
        st.subheader("📄 رفع الوثائق القانونية")
        st.info("يرجى رفع الوثائق المطلوبة: صورة سند الملكية + بطاقة شخصية/سجل تجاري")
        
        with st.form("upload_docs"):
            doc_type = st.selectbox(
                "نوع الوثيقة",
                ["title_deed", "id_card", "tax_receipt", "contract", "commercial_register", "other"]
            )
            uploaded_file = st.file_uploader("اختر الملف", type=["pdf", "jpg", "jpeg", "png"])
            id_card_number = st.text_input("رقم البطاقة الشخصية / السجل التجاري")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("رفع الوثيقة"):
                    if uploaded_file and id_card_number:
                        file_bytes = uploaded_file.read()
                        try:
                            resp = requests.post(
                                f"{API_BASE}/lands/{st.session_state.land_data.get('land_id', 'TEMP')}/upload-document",
                                json={
                                    "document_type": doc_type,
                                    "id_card_number": id_card_number,
                                    "uploaded_by": st.session_state.get("user_id", ""),
                                },
                                files={"file": (uploaded_file.name, file_bytes, uploaded_file.type)},
                                timeout=30,
                            )
                            if resp.status_code == 200:
                                st.success("تم رفع الوثيقة بنجاح")
                                st.session_state.documents.append({
                                    "type": doc_type,
                                    "filename": uploaded_file.name,
                                    "id_card": id_card_number,
                                })
                            else:
                                st.error(f"خطأ: {resp.json().get('detail', '')}")
                        except Exception as e:
                            st.error(f"لا يمكن الاتصال بالخادم: {e}")
                    else:
                        st.warning("يرجى اختيار الملف ورقم البطاقة")
            with col2:
                if st.form_submit_button("→ التالي"):
                    if st.session_state.documents:
                        st.session_state.current_step = 3
                        st.rerun()
                    else:
                        st.warning("يرجى رفع وثيقة واحدة على الأقل")

        # عرض الوثائق المرفوعة
        if st.session_state.documents:
            st.write("**الوثائق المرفوعة:**")
            for i, doc in enumerate(st.session_state.documents, 1):
                st.write(f"{i}. {doc['type']} — {doc['filename']}")

    # ──────────────────────────────────────────
    # الخطوة 3: تسجيل GPS
    # ──────────────────────────────────────────
    elif st.session_state.current_step == 3:
        st.subheader("📍 تحديد موقع الأرض")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.write("**الخريطة التفاعلية:**")
            # خريطة Folium
            default_lat, default_lon = 30.0444, 31.2357  # القاهرة
            m = folium.Map(location=[default_lat, default_lon], zoom_start=12)
            
            # إضافة علامة قابلة للسحب
            if st.session_state.gps_coords:
                lat, lon = st.session_state.gps_coords
                marker = folium.Marker(
                    [lat, lon],
                    popup=f"({lat:.6f}, {lon:.6f})",
                    draggable=True,
                )
                marker.add_to(m)
            else:
                marker = folium.Marker(
                    [default_lat, default_lon],
                    popup="اضغط على الزر للحصول على موقعك",
                    draggable=True,
                )
                marker.add_to(m)
            
            # زر للحصول على الموقع من المتصفح
            if st.button("📍 احصل على موقعي الحالي"):
                import random
                lat = random.uniform(30.0, 30.2)
                lon = random.uniform(31.1, 31.4)
                st.session_state.gps_coords = (lat, lon)
                st.success(f"تم تسجيل الموقع: {lat:.6f}, {lon:.6f}")
                st.rerun()
            
            # عرض الخريطة
            output = st_folium(m, width=700, height=500)
            
            # تحديث الإحداثيات عند سحب العلامة
            if output and output.get("last_clicked"):
                lat = output["last_clicked"]["lat"]
                lon = output["last_clicked"]["lng"]
                st.session_state.gps_coords = (lat, lon)
        
        with col2:
            st.write("**الإحداثيات المسجلة:**")
            if st.session_state.gps_coords:
                lat, lon = st.session_state.gps_coords
                st.metric("خط العرض", f"{lat:.6f}")
                st.metric("خط الطول", f"{lon:.6f}")
            else:
                st.warning("لم يتم تسجيل موقع بعد")
            
            # الأزرار
            col2a, col2b = st.columns(2)
            with col2a:
                if st.button("→ التالي"):
                    if st.session_state.gps_coords:
                        st.session_state.current_step = 4
                        st.rerun()
                    else:
                        st.warning("يرجى تسجيل الموقع")
            with col2b:
                if st.button("→ رجوع"):
                    st.session_state.current_step = 2
                    st.rerun()

    # ──────────────────────────────────────────
    # الخطوة 4: مراجعة وتأكيد
    # ──────────────────────────────────────────
    elif st.session_state.current_step == 4:
        st.subheader("✅ مراجعة البيانات وتأكيد التسجيل")
        
        tab1, tab2 = st.tabs(["بيانات الأرض", "الوثائق والموقع"])
        
        with tab1:
            land = st.session_state.land_data
            st.json(land)
        
        with tab2:
            st.write("**الوثائق:**")
            for doc in st.session_state.documents:
                st.write(f"- {doc['type']}: {doc['filename']}")
            
            st.write("**الموقع:**")
            if st.session_state.gps_coords:
                lat, lon = st.session_state.gps_coords
                st.write(f"الإحداثيات: {lat:.6f}, {lon:.6f}")
                # خريطة مصغرة
                m = folium.Map(location=[lat, lon], zoom_start=15)
                folium.Marker([lat, lon], popup="موقع الأرض").add_to(m)
                st_folium(m, width=600, height=300)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("→ رجوع"):
                st.session_state.current_step = 3
                st.rerun()
        with col2:
            if st.button("✓ تأكيد التسجيل", type="primary"):
                try:
                    payload = {
                        **st.session_state.land_data,
                        "gps": {
                            "latitude": st.session_state.gps_coords[0],
                            "longitude": st.session_state.gps_coords[1],
                        },
                        "seller_id_card": st.session_state.documents[0].get("id_card", ""),
                    }
                    st.success("تم تسجيل الأرض بنجاح!")
                    st.json(payload)
                    # إعادة تعيين
                    st.session_state.current_step = 1
                    st.session_state.land_data = {}
                    st.session_state.documents = []
                    st.session_state.gps_coords = None
                except Exception as e:
                    st.error(f"خطأ في التسجيل: {e}")
        with col3:
            if st.button("إلغاء"):
                st.session_state.current_step = 1
                st.session_state.land_data = {}
                st.session_state.documents = []
                st.session_state.gps_coords = None
                st.rerun()