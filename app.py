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

# ล้าง Cache ทุก 3600 วินาที (1 ชั่วโมง) เพื่อประหยัดโควต้าหากมีคนค้นหาคำเดิม
@st.cache_data(ttl=3600)
def get_ai_response(prompt, model_name):
    model = genai.GenerativeModel(model_name)
    # บังคับให้ AI ตอบกลับมาเป็นโครงสร้าง JSON ทันที (ช่วยให้เร็วขึ้นและไม่ต้องดักจับข้อความขยะ)
    return model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )

# บังคับเลือกรุ่น 1.5-flash เป็นอันดับแรกเพื่อดึงโควต้า 1500 ครั้ง/วัน และประมวลผลเร็วที่สุด
@st.cache_resource
def get_available_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # ค้นหา 1.5-flash ก่อนเสมอ
        for m in available_models:
            if '1.5-flash' in m: return m
            
        # ถ้าไม่มี ให้ไล่หารุ่นอื่นสำรอง
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
    # สร้าง Dictionary ส่วนกลางเพื่อแชร์ให้ทุก Session
    return {"used": 0, "limit": 1500}

app_quota = get_global_quota()

# ==========================================
# 3. UI Layout & CSS
# ==========================================
st.set_page_config(page_title="SPECIFICATION COM7", layout="centered", page_icon="🏢")

st.markdown("""
    <style>
    .main-title { text-align: center; color: #7CB342; font-size: 2.8rem; font-weight: 800; margin-bottom: 0; }
    .sub-title { text-align: center; color: #666; font-size: 1rem; margin-bottom: 15px; }
    .quota-box { text-align: center; background-color: #f1f8e9; color: #33691E; padding: 8px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; margin-bottom: 25px; border: 1px solid #c5e1a5; display: inline-block; width: 100%;}
    .history-box { background-color: #ffffff; border: 2px solid #7CB342; border-radius: 8px; padding: 15px; margin-bottom: 20px; text-align: center; color: #666;}
    .stButton>button { background-color: #7CB342 !important; color: white !important; border-radius: 25px; border: none; }
    .stProgress > div > div > div > div { background-color: #7CB342 !important; } /* Com7 Green Bar */
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. จัดการ Session State (ค้นหา & ประวัติ)
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

# แสดงโควต้าการใช้งานแบบ Real-time ที่แชร์ร่วมกัน
st.markdown(f"<div class='quota-box'>📊 โควต้าการค้นหารวมของระบบวันนี้: {app_quota['used']} / {app_quota['limit']} ครั้ง</div>", unsafe_allow_html=True)

# ส่วน Search History แบบคลิกได้ (แสดงล่าสุดก่อน สูงสุด 10 รายการ)
st.markdown("**ประวัติการค้นหาล่าสุด (Search History)**")
with st.container():
    if st.session_state.search_history:
        # กลับด้านลิสต์ให้ล่าสุดอยู่ซ้ายมือสุด และตัดให้ไม่เกิน 10
        history_list = list(reversed(st.session_state.search_history[-10:]))
        
        # จัดเรียงปุ่มแถวละ 5 ปุ่มเพื่อความสวยงาม
        for i in range(0, len(history_list), 5):
            cols = st.columns(5)
            for j in range(5):
                if i + j < len(history_list):
                    btn_label = history_list[i+j]
                    cols[j].button(btn_label, key=f"hist_{i}_{j}", on_click=click_history, args=(btn_label,), use_container_width=True)
    else:
        st.markdown("<div class='history-box'>ยังไม่มีประวัติการค้นหา</div>", unsafe_allow_html=True)

# ช่องค้นหาหลัก
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
        # อัปเดต Global Quota
        app_quota['used'] += 1

        # รีเซ็ต Trigger หลังจากกดเริ่ม
        st.session_state.trigger_search = False
        st.session_state.search_query = product_name
        
        # อัปเดต History 
        if product_name in st.session_state.search_history:
            st.session_state.search_history.remove(product_name)
        st.session_state.search_history.append(product_name)
        st.session_state.search_history = st.session_state.search_history[-10:]
        
        # แสดงสถานะการโหลดแบบไม่มีการหน่วงเวลา
        with st.spinner(f"กำลังวิเคราะห์และค้นหาซัพพลายเออร์สำหรับ '{product_name}'... (ใช้เวลาประมาณ 5-15 วินาที)"):
            
            # ปรับ Prompt ใหม่ให้ดึงเฉพาะที่มีอีเมล และไม่ต้องดึงข้อมูลเว็บไซต์/ที่อยู่มาให้เสียเวลาประมวลผล
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
                # เรียกใช้งาน AI 
                response = get_ai_response(prompt, SELECTED_MODEL)
                
                # โหลดข้อมูล JSON จาก AI กลับมาเป็น List ทันที
                try:
                    data = json.loads(response.text)
                except json.JSONDecodeError:
                    # กรณีสุดวิสัย AI ส่ง JSON มาไม่สมบูรณ์ พยายามซ่อมแซม
                    match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    if match:
                        fixed_json_str = match.group(0).rsplit('}', 1)[0] + '}]'
                        try:
                            data = json.loads(fixed_json_str)
                        except:
                            data = []
                    else:
                        data = []

                if not data:
                    st.info(f"ไม่พบข้อมูลซัพพลายเออร์ B2B ที่มีอีเมลติดต่อสำหรับ '{product_name}' หรือระบบคืนค่าผิดพลาด กรุณาลองปรับคำค้นหาใหม่")
                else:
                    df_raw = pd.DataFrame(data)
                    
                    final_rows = []
                    for _, row in df_raw.iterrows():
                        email = str(row.get('email', '')).strip()
                        
                        # กรองเอาเฉพาะรายการที่มีอีเมล (ตัด N/A, -, หรือค่าว่างทิ้ง)
                        if email.upper() == 'N/A' or email == '-' or email == '' or email.lower() == 'nan':
                            continue

                        row_data = {
                            "ชื่อซัพพลายเออร์": row.get('name', 'N/A'),
                            "เวลาเปิด-ปิด": row.get('hours', 'N/A'),
                            "อีเมล": email,
                            "เบอร์โทรศัพท์": row.get('phone', 'N/A')
                        }
                        final_rows.append(row_data)

                    # ถ้าคัดกรองแล้วไม่เหลือใครเลย
                    if not final_rows:
                        st.warning(f"ค้นพบข้อมูลบริษัท แต่ไม่มีบริษัทไหนที่มีข้อมูลอีเมลติดต่อเลยสำหรับ '{product_name}'")
                    else:
                        df = pd.DataFrame(final_rows)

                        st.markdown(f"### ✅ ผลลัพธ์สำหรับ: {product_name} (พบ {len(df)} รายการที่ระบุอีเมล)")
                        st.dataframe(
                            df,
                            hide_index=True,
                            use_container_width=True
                        )
                    
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
                # ถ้าเกิด Error ให้คืนโควต้าให้ระบบ 1 ครั้ง
                app_quota['used'] = max(0, app_quota['used'] - 1)

st.markdown("---")
st.caption(f"⚙️ System Engine: {SELECTED_MODEL} (Auto-reset every 1 hour)")
