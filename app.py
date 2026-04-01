import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import urllib.parse
import re
import time

# ==========================================
# 1. ตั้งค่าระบบและจัดการ Cache
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ล้าง Cache ทุก 3600 วินาที (1 ชั่วโมง) เพื่อประหยัดโควต้าหากมีคนค้นหาคำเดิม
@st.cache_data(ttl=3600)
def get_ai_response(prompt, model_name):
    model = genai.GenerativeModel(model_name)
    return model.generate_content(prompt)

# บังคับเลือกรุ่น 1.5-flash เป็นอันดับแรกเพื่อดึงโควต้า 1500 ครั้ง/วัน
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
        # อัปเดต Global Quota (นับทุกครั้งที่มีการรันค้นหา)
        app_quota['used'] += 1

        # รีเซ็ต Trigger หลังจากกดเริ่ม
        st.session_state.trigger_search = False
        st.session_state.search_query = product_name
        
        # อัปเดต History 
        if product_name in st.session_state.search_history:
            st.session_state.search_history.remove(product_name)
        st.session_state.search_history.append(product_name)
        st.session_state.search_history = st.session_state.search_history[-10:]
        
        # หลอดโหลดสีเขียว Com7
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i in range(1, 101, 10):
            time.sleep(0.05) 
            progress_bar.progress(i)
            status_text.text(f"กำลังรวบรวมข้อมูลซัพพลายเออร์... {i}%")

        prompt = f"""
        ค้นหาบริษัท B2B ในไทยที่ขาย '{product_name}' ให้ได้จำนวนมากที่สุดเท่าที่คุณจะสามารถประมวลผลได้ใน 1 ครั้ง (เป้าหมาย 30-50 แห่งขึ้นไป) (ห้ามค้าปลีกเด็ดขาด)
        ข้อควรระวังสำคัญ: คุณต้องตอบเป็นรูปแบบ JSON Array ที่สมบูรณ์แบบเท่านั้น หากข้อมูลยาวเกินไป ให้หยุดที่จำนวนที่คุณสามารถปิดวงเล็บ ] ได้ทัน ห้ามส่งข้อมูลที่ขาดหายกลางคัน
        หากไม่เจอหรือเป็นสินค้าไม่มีจริงให้ตอบ []
        โครงสร้าง JSON:
        [
            {{
                "name": "ชื่อบริษัท",
                "unit": "ราคา/ชิ้น (ถ้าไม่มีข้อมูลจริงให้ใส่ 'N/A')",
                "pack": "ราคา/แพ็ค (ถ้าไม่มีข้อมูลจริงให้ใส่ 'N/A')",
                "box": "ราคา/ลัง (ถ้าไม่มีข้อมูลจริงให้ใส่ 'N/A')",
                "hours": "เวลาเปิด-ปิด (เช่น จ.-ศ. 08:30-17:30)",
                "address": "ที่อยู่เต็ม",
                "phone": "เบอร์โทรศัพท์ (ถ้าไม่มีให้ใส่ 'N/A')",
                "website": "URL เว็บไซต์แบบเต็ม (ต้องขึ้นต้นด้วย http:// หรือ https:// ถ้าไม่มีให้ใส่ 'N/A')"
            }}
        ]
        """

        try:
            response = get_ai_response(prompt, SELECTED_MODEL)
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    fixed_json_str = match.group(0).rsplit('}', 1)[0] + '}]'
                    try:
                        data = json.loads(fixed_json_str)
                    except:
                        data = []
                        st.warning("⚠️ ข้อมูลมีขนาดใหญ่เกินไป ทำให้บางส่วนสูญหาย กรุณาลองค้นหาให้แคบลง")
            else:
                data = []

            progress_bar.progress(100)
            status_text.empty()

            if not data:
                st.info(f"ไม่พบข้อมูลซัพพลายเออร์ B2B สำหรับ '{product_name}' หรือรูปแบบข้อมูลไม่ถูกต้อง")
            else:
                df_raw = pd.DataFrame(data)
                
                final_rows = []
                for _, row in df_raw.iterrows():
                    addr = row.get('address', '')
                    maps_url = f"https://www.google.com/maps/dir/{urllib.parse.quote('บริษัท คอมเซเว่น บางนา')}/{urllib.parse.quote(addr)}"
                    
                    web = row.get('website', 'N/A')
                    if pd.isna(web) or web == 'N/A' or web == '-' or web == '':
                        web_url = None
                    else:
                        web_url = str(web)
                        if not web_url.startswith('http'):
                            web_url = 'https://' + web_url

                    row_data = {
                        "ชื่อซัพพลายเออร์": row.get('name'),
                        "ราคา/ชิ้น": row.get('unit'),
                        "ราคา/แพ็ค": row.get('pack'),
                        "ราคา/ลัง": row.get('box'),
                        "เวลาเปิด-ปิด": row.get('hours'),
                        "แผนที่นำทาง": maps_url,
                        "เบอร์โทรศัพท์": row.get('phone'),
                        "เว็บไซต์": web_url
                    }
                    final_rows.append(row_data)

                df = pd.DataFrame(final_rows)

                cols_to_check = ["ราคา/ชิ้น", "ราคา/แพ็ค", "ราคา/ลัง"]
                for col in cols_to_check:
                    if col in df.columns and (df[col] == "N/A").all():
                        df = df.drop(columns=[col])

                st.markdown(f"### ✅ ผลลัพธ์สำหรับ: {product_name} (พบ {len(df)} รายการ)")
                st.dataframe(
                    df,
                    column_config={
                        "แผนที่นำทาง": st.column_config.LinkColumn("📍 ดูเส้นทาง (Com7)", display_text="เปิด Google Maps"),
                        "เว็บไซต์": st.column_config.LinkColumn("🌐 เว็บไซต์", display_text="เข้าสู่เว็บไซต์")
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # รีเฟรชหน้าเบาๆ เพื่ออัปเดตตัวเลขโควต้าให้ผู้ใช้คนอื่นเห็นทันที (ถ้าจำเป็น)
                # st.rerun() 

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
            # ถ้าเกิด Error แล้วอยากคืนโควต้าให้ระบบ
            app_quota['used'] = max(0, app_quota['used'] - 1)
            progress_bar.empty()

st.markdown("---")
st.caption(f"⚙️ System Engine: {SELECTED_MODEL} (Auto-reset every 1 hour)")
