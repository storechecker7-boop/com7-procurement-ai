import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re

# ==========================================
# 1. ตั้งค่าระบบและจัดการ Cache
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

@st.cache_data(ttl=3600)
def get_ai_response(prompt, model_name):
    model = genai.GenerativeModel(model_name)
    return model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )

@st.cache_resource
def get_available_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in available_models:
            if '1.5-flash' in m: return m
        for target in ['1.5', '2.0', '2.5', 'pro']:
            for m in available_models:
                if target in m: return m
        return available_models[0]
    except:
        return "models/gemini-1.5-flash"

SELECTED_MODEL = get_available_model()

# ==========================================
# 2. ระบบ Global Quota Tracker (นับรวมทุกคน)
# ==========================================
@st.cache_resource
def get_global_quota():
    return {"used": 0, "limit": 1500}

app_quota = get_global_quota()

# ==========================================
# 3. UI Layout & CSS
# ==========================================
st.set_page_config(page_title="SPECIFICATION COM7", layout="centered", page_icon="🏢")

st.markdown("""
    <style>
    /* ตั้งค่าฟอนต์และการแสดงผลให้ดูมินิมอลและเรียบหรูขึ้น */
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Kanit', sans-serif;
    }
    
    .main-title { text-align: center; color: #7CB342; font-size: 2.8rem; font-weight: 600; margin-bottom: 0; letter-spacing: 1px;}
    .sub-title { text-align: center; color: #888; font-size: 0.95rem; margin-bottom: 25px; font-weight: 300; }
    .quota-box { text-align: center; background-color: #f1f8e9; color: #558b2f; padding: 6px 15px; border-radius: 20px; font-weight: 400; font-size: 0.85rem; margin-bottom: 30px; border: 1px solid #dcedc8; display: inline-block; width: 100%;}
    .history-box { background-color: #f9f9f9; border: 1px dashed #ccc; border-radius: 8px; padding: 15px; margin-bottom: 20px; text-align: center; color: #999; font-size: 0.9rem;}
    
    /* ปุ่มค้นหา */
    .stButton>button { background-color: #7CB342 !important; color: white !important; border-radius: 8px; border: none; font-weight: 500; padding: 10px 24px; transition: all 0.3s ease;}
    .stButton>button:hover { background-color: #689f38 !important; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    
    /* หัวข้อผลลัพธ์แบบเรียบหรู */
    .result-header {
        font-size: 1.25rem;
        font-weight: 500;
        color: #2e7d32;
        padding-bottom: 10px;
        border-bottom: 1px solid #e0e0e0;
        margin-top: 30px;
        margin-bottom: 15px;
    }
    .result-count {
        font-size: 0.9rem;
        font-weight: 300;
        color: #777;
        margin-left: 8px;
    }
    
    /* สถานะโหลดแบบคลีนๆ */
    .clean-loading {
        text-align: center;
        color: #7CB342;
        font-size: 0.95rem;
        font-weight: 400;
        padding: 20px;
        background-color: #f1f8e9;
        border-radius: 8px;
        margin-top: 15px;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 1; }
        100% { opacity: 0.6; }
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. จัดการ Session State
# ==========================================
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'trigger_search' not in st.session_state:
    st.session_state.trigger_search = False

def click_history(term):
    st.session_state.search_query = term
    st.session_state.trigger_search = True

# Header & Quota Display
st.markdown("<div class='main-title'>COIII7</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>SPECIFICATION COM7 | B2B PROCUREMENT AGENT</div>", unsafe_allow_html=True)
st.markdown(f"<div class='quota-box'>📊 โควต้าการค้นหารวมของระบบวันนี้: {app_quota['used']} / {app_quota['limit']} ครั้ง</div>", unsafe_allow_html=True)

st.markdown("**ประวัติการค้นหาล่าสุด**")
with st.container():
    if st.session_state.search_history:
        history_list = list(reversed(st.session_state.search_history[-10:]))
        for i in range(0, len(history_list), 5):
            cols = st.columns(5)
            for j in range(5):
                if i + j < len(history_list):
                    btn_label = history_list[i+j]
                    cols[j].button(btn_label, key=f"hist_{i}_{j}", on_click=click_history, args=(btn_label,), use_container_width=True)
    else:
        st.markdown("<div class='history-box'>ยังไม่มีประวัติการค้นหา</div>", unsafe_allow_html=True)

product_name = st.text_input("ระบุชื่อสินค้าที่ต้องการค้นหา", value=st.session_state.search_query, placeholder="เช่น ปลั๊กไฟ 3 ตา, จอมอนิเตอร์, สาย HDMI ราคาถูก")
search_btn = st.button("ค้นหาซัพพลายเออร์", use_container_width=True)

# ==========================================
# 5. ส่วนประมวลผล (Processing)
# ==========================================
if search_btn or st.session_state.trigger_search:
    if app_quota['used'] >= app_quota['limit']:
        st.error("🚫 ขออภัยครับ โควต้าการค้นหาของระบบเต็มแล้วสำหรับวันนี้ กรุณาลองใหม่พรุ่งนี้")
        st.session_state.trigger_search = False
    elif not product_name:
        st.warning("กรุณากรอกชื่อสินค้า")
        st.session_state.trigger_search = False
    else:
        app_quota['used'] += 1
        st.session_state.trigger_search = False
        st.session_state.search_query = product_name
        
        if product_name in st.session_state.search_history:
            st.session_state.search_history.remove(product_name)
        st.session_state.search_history.append(product_name)
        st.session_state.search_history = st.session_state.search_history[-10:]
        
        # กล่องโหลดข้อความแบบเรียบหรู (จะถูกลบทิ้งเมื่อโหลดเสร็จ)
        loading_placeholder = st.empty()
        loading_placeholder.markdown(f"<div class='clean-loading'>⏳ กำลังรวบรวมข้อมูลซัพพลายเออร์สำหรับ '{product_name}'...</div>", unsafe_allow_html=True)
            
        prompt = f"""
        ค้นหาบริษัท B2B ในไทยที่ขาย '{product_name}' ให้ได้จำนวนมากที่สุดเท่าที่คุณจะสามารถประมวลผลได้ (เป้าหมาย 30-50 แห่งขึ้นไป) (ห้ามบริษัทค้าปลีกเด็ดขาด)
        เลือกมาเฉพาะบริษัทที่มีข้อมูล 'อีเมล' สำหรับติดต่อเท่านั้น ถ้าไม่มีให้ข้ามไปเลย
        ส่งกลับมาเป็นข้อมูลรูปแบบ JSON Array เท่านั้น ตามโครงสร้างด้านล่าง:
        [
            {{
                "name": "ชื่อบริษัท",
                "hours": "เวลาเปิด-ปิด (เช่น จ.-ศ. 08:30-17:30)",
                "email": "อีเมล",
                "phone": "เบอร์โทรศัพท์ (ถ้าไม่มีให้ใส่ 'N/A')"
            }}
        ]
        """

        try:
            response = get_ai_response(prompt, SELECTED_MODEL)
            
            try:
                data = json.loads(response.text)
            except json.JSONDecodeError:
                match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if match:
                    fixed_json_str = match.group(0).rsplit('}', 1)[0] + '}]'
                    try:
                        data = json.loads(fixed_json_str)
                    except:
                        data = []
                else:
                    data = []

            # ลบกล่องโหลดทิ้งเมื่อประมวลผลเสร็จ
            loading_placeholder.empty()

            if not data:
                st.info(f"ไม่พบข้อมูลซัพพลายเออร์ B2B ที่มีอีเมลติดต่อสำหรับ '{product_name}' หรือระบบคืนค่าผิดพลาด กรุณาลองปรับคำค้นหาใหม่")
            else:
                df_raw = pd.DataFrame(data)
                
                final_rows = []
                for _, row in df_raw.iterrows():
                    email = str(row.get('email', '')).strip()
                    if email.upper() == 'N/A' or email == '-' or email == '' or email.lower() == 'nan':
                        continue

                    row_data = {
                        "ชื่อซัพพลายเออร์": row.get('name', 'N/A'),
                        "เวลาเปิด-ปิด": row.get('hours', 'N/A'),
                        "อีเมล": email,
                        "เบอร์โทรศัพท์": row.get('phone', 'N/A')
                    }
                    final_rows.append(row_data)

                if not final_rows:
                    st.warning(f"ค้นพบข้อมูลบริษัท แต่ไม่มีบริษัทไหนที่มีข้อมูลอีเมลติดต่อเลยสำหรับ '{product_name}'")
                else:
                    df = pd.DataFrame(final_rows)

                    # แสดงผลหัวข้อแบบเรียบหรูและเล็กลง
                    st.markdown(f"<div class='result-header'>✅ ผลลัพธ์สำหรับ: {product_name} <span class='result-count'>(พบ {len(df)} รายการที่ระบุอีเมล)</span></div>", unsafe_allow_html=True)
                    st.dataframe(
                        df,
                        hide_index=True,
                        use_container_width=True
                    )
                
        except Exception as e:
            loading_placeholder.empty()
            st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
            app_quota['used'] = max(0, app_quota['used'] - 1)

st.markdown("---")
st.caption(f"⚙️ System Engine: {SELECTED_MODEL} (Auto-reset every 1 hour)")
