import streamlit as st
from google import genai
import json
import re
# --- 1. 初始化 (務必先取得 Key，再建立 Client) ---

# A. 先取得變數 (從 Secrets 或側邊欄)
try:
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    GEMINI_API_KEY = None

if not GEMINI_API_KEY:
    GEMINI_API_KEY = st.sidebar.text_input("請輸入新產生的 Gemini API Key", type="password")

# B. 取得 Key 之後，才建立 Client
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 測試：列出可用模型 (僅在開發測試時執行一次即可)
        # models = client.models.list()
        # for m in models:
        #     print(f"可用模型名稱: {m.name}")
            
    except Exception as e:
        st.error(f"Client 初始化失敗: {e}")
else:
    st.warning("🔑 請先提供 API Key 以繼續執行。")

st.set_page_config(page_title="RF Schematic Auditor", layout="wide")
st.title("📡 RF 線路檢查系統")

# --- 2. 核心判斷邏輯 (全面排除電壓干擾) ---
def judge_logic(act, std):
    if not act or str(act).upper() in ["N/A", "NONE", "NULL", ""]:
        return "❌ FAIL (未讀取到數據)", False

    a = str(act).upper().replace(" ", "")
    s = str(std).upper().replace(" ", "")
    
    no_part_terms = ["NI", "NC", "NA", "OPEN", "DNS", "DNP", "EMPTY"]
    
    # 邏輯 A：優先判定 NI/NC
    if "NC" in s:
        if any(term in a for term in no_part_terms):
            return "✅ PASS (NI=NC)", True
        return f"❌ FAIL (預期 NC, 實作 {act})", False
    
    # 邏輯 B：Power 關鍵字互信機制
    if "3.3" in s and "VBAT" in a:
        return "✅ PASS", True
    if "1.8" in s and ("VDDIO" in a or "SDIO" in a or "VIO" in a):
        return "✅ PASS", True

    # 3. 數字提取比對
    def extract_nums(text):
        t = text.replace("V", ".")
        return re.findall(r"\d+\.?\d*", t)

    a_nums, s_nums = extract_nums(a), extract_nums(s)
    for sn in s_nums:
        if any(sn == an for an in a_nums):
            return "✅ PASS", True

    if s in a or a in s:
        return "✅ PASS", True
    
    return "❌ FAIL (數值不符)", False

# --- 3. UI 介面 (維持原樣) ---
st.header(f"📂 Project：LiteHub_AP6281S")
st.divider()

# A. 時鐘系統
st.markdown("#### 🕒 時鐘系統 (Clock System)")
c1, c2 = st.columns(2)
with c1:
    std_xtal = st.text_input("主時鐘頻率 (Main XTAL)", value="59.97MHz")
    std_cap1 = st.text_input("XTAL 電容 1 標準值", value="10pF")
with c2:
    std_rtc = st.text_input("RTC 時鐘頻率 (LPO)", value="32.768KHz")
    std_cap2 = st.text_input("XTAL 電容 2 標準值", value="10pF")

# B. RF 路徑
st.divider()
st.markdown("#### ⚡ RF Matching 定義 (從 Pin 2: WL/BT_ANT0 出發)")
rf_configs = []
rf_cols = st.columns(3)
ref_vals = ["10pF(NC)", "10pF", "33pF(NC)"]
for i in range(3):
    with rf_cols[i]:
        st.write(f"Pin 2 後第 {i+1} 個元件")
        c_type = st.selectbox(f"類型", ["R", "L", "C", "NC"], key=f"rf_t_{i}", index=3 if i != 1 else 2)
        c_val = st.text_input(f"標準值", value=ref_vals[i], key=f"rf_v_{i}")
        rf_configs.append({"type": c_type, "std_val": c_val})

# C. 電源規範
st.divider()
st.markdown("#### 🔋 電源規範 (Power Spec)")
p_col1, p_col2, p_col3 = st.columns(3)
with p_col1:
    st.write("**VBAT 規範 (Pin 9)**")
    std_vbat_v = st.text_input("VBAT 預期電壓標籤", value="3.3V")
    std_vbat_c = st.text_input("VBAT 建議濾波電容", value="4.7uF, 1uF")
with p_col2:
    st.write("**VDDIO 規範 (Pin 22)**")
    std_vddio_v = st.text_input("VDDIO 電壓標籤", value="1.8V")
    std_vddio_c1 = st.text_input("VDDIO 下地電容 1", value="1uF")
    std_vddio_c2 = st.text_input("VDDIO 下地電容 2", value="4.7uF")
with p_col3:
    st.write("**ASR_VLX 回路 (Pin 21)**")
    std_pin21_l = st.text_input("L1 電感標準值", value="1uH")
    std_pin21_c = st.text_input("C14 電容標準值", value="4.7uF")

# --- 4. 執行分析 ---
st.divider()
f_ref = st.file_uploader("1. 上傳公版 PDF", type="pdf", key="ref_up")
f_imp = st.file_uploader("2. 上傳實作 PDF", type="pdf", key="imp_up")

# 診斷按鈕 (永遠顯示，只要有 API Key)
if st.button("🔍 檢查可用模型清單", key="diag"):
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        st.write("### 您的 Key 可用模型清單：")
        try:
            for m in client.models.list():
                st.code(m.name)
        except Exception as e:
            st.error(f"無法取得列表: {e}")
    else:
        st.warning("請先輸入 API Key")

# 核心邏輯：處理檔案並顯示三階段按鈕
if f_ref and f_imp:
    # 使用 session_state 防止讀取後按鈕消失
    if 'ref_content' not in st.session_state or st.sidebar.button("🔄 刷新上傳檔案"):
        st.session_state['ref_content'] = f_ref.read()
        st.session_state['imp_content'] = f_imp.read()

    pdf_ref_bytes = st.session_state['ref_content']
    pdf_imp_bytes = st.session_state['imp_content']
    
    # 你剛才清單中最強的模型
    TARGET_MODEL = "gemini-3-flash-preview"
    
    st.info(f"💡 目前使用模型: `{TARGET_MODEL}`。請根據需求點擊下方按鈕進行稽核。")
    
    col1, col2, col3 = st.columns(3)

    # --- 階段 1：時鐘按鈕 ---
# --- 階段 1：時鐘按鈕 (鎖定 Page 15) ---
    with col1:
        if st.button("🕒 1. 稽核時鐘系統", use_container_width=True, key="btn_clk"):
            with st.spinner("正在掃描 Foxconn 圖紙 Page 15..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    
                    # 修正 P1：加入 Page 15 鎖定指令
                    P1 = """
                    你是時鐘稽核專家。
                    任務：請針對實作圖紙 (Foxconn) 的『第 15 頁 (Page 15)』進行掃描。
                    1. 找到主晶振並提取其頻率 (Frequency)。
                    2. 提取與該晶振相連的負載電容 cap1, cap2。
                    3. 找到 RTC 區塊並提取其頻率。
                    
                    回傳 JSON: { 'clock_system': { 'freq', 'cap1', 'cap2', 'rtc' } }
                    """
                    
                    res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[
                            genai.types.Part.from_bytes(data=pdf_ref_bytes, mime_type="application/pdf"),
                            P1,
                            genai.types.Part.from_bytes(data=pdf_imp_bytes, mime_type="application/pdf")
                        ]
                    )
                    
                    # 取得 JSON 部分
                    json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
                    if json_match:
                        st.session_state['data_clk'] = json.loads(json_match.group())
                        st.success("✅ 時鐘分析完成 (已定位 Page 15)")
                    else:
                        st.error("未能從 AI 回覆中提取有效的 JSON 數據")
                        
                except Exception as e:
                    st.error(f"時鐘分析失敗: {e}")

# --- 階段 2：RF 按鈕 (視覺狙擊版) ---
    with col2:
        if st.button("⚡ 2. 稽核 RF 路徑", use_container_width=True, key="btn_rf"):
            with st.spinner("偵測到特殊 NI 標註，啟動深度視覺掃描..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    P2 = """
                    你是專業硬體稽核專家，現在檢查 Foxconn 圖紙 Page 15。
                    
                    任務：稽核 C626, C627, C626 狀態。
                    ⚠️ 核心視覺掃描指令：
                    1. 先定位 C626, C627, C628 的元件位置。
                    2. 檢查每個元件『兩條平行橫線 (電容符號)』的的正下方或正中間。
                    3. ⚠️ 視覺警告：在 C626 和 C628 的電容圖示正下方，有非常小的『NI』字樣，請務必識別出來。
                    
                    判定規則：
                    - 如果電容符號下方或旁邊有任何『NI』或『NC』字樣：'act' 欄位請填寫 'NI'。
                    - 如果符號乾淨且只有數值：則填寫讀到的數值 (例如 '10pF')。
                    
                    回傳 JSON: { 'rf_path': [ {'des': 'C628', 'act': '...'}, {'des': 'C627', 'act': '...'}, {'des': 'C626', 'act': '...'} ] }
                    """
                    res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[
                            genai.types.Part.from_bytes(data=pdf_ref_bytes, mime_type="application/pdf"),
                            P2,
                            genai.types.Part.from_bytes(data=pdf_imp_bytes, mime_type="application/pdf")
                        ]
                    )
                    st.session_state['data_rf'] = json.loads(re.search(r'\{.*\}', res.text, re.DOTALL).group())
                    st.success("✅ RF 視覺掃描完成 (已針對隱藏式 NI 優化)")
                except Exception as e:
                    st.error(f"分析失敗: {e}")

# --- 階段 3：電源按鈕 (座標綁定版) ---
    with col3:
        if st.button("🔋 3. 稽核電源規範", use_container_width=True, key="btn_pwr"):
            with st.spinner("正在執行 Pin-to-Cap 視覺追蹤 (Page 15)..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    P3 = """
                    你是專業電源硬體專家。任務：檢查實作圖紙 (Foxconn) Page 15。
                    ⚠️ 嚴格執行路徑追蹤：
                    1. 定位 Pin 9 (VBAT): 沿著線路尋找最靠近該引腳的兩顆旁路電容。確認位號與數值。
                    2. 定位 Pin 22 (VDDIO): 沿著線路尋找最靠近該引腳的兩顆旁路電容。務必區分清楚，不要跟 Pin 9 的混淆。
                    3. 定位 Pin 21 (ASR_VLX): 提取電感 L49 與電容 C630。

                    回傳 JSON 格式 (請確保位號正確):
                    { 
                      'power_config': { 
                        'vbat_net': '...', 
                        'vbat_cap1': '位號(數值)', 
                        'vbat_cap2': '位號(數值)', 
                        'vddio_net': '...', 
                        'vddio_cap1': '位號(數值)', 
                        'vddio_cap2': '位號(數值)', 
                        'pin21_l1': '...', 
                        'pin21_c14': '...' 
                      } 
                    }
                    """
                    res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[
                            genai.types.Part.from_bytes(data=pdf_ref_bytes, mime_type="application/pdf"),
                            P3,
                            genai.types.Part.from_bytes(data=pdf_imp_bytes, mime_type="application/pdf")
                        ]
                    )
                    st.session_state['data_pwr'] = json.loads(re.search(r'\{.*\}', res.text, re.DOTALL).group())
                    st.success("✅ 電源分析完成 (已強化腳位追蹤)")
                except Exception as e:
                    st.error(f"分析失敗: {e}")

# --- 5. 結果顯示區 ---
if any(key in st.session_state for key in ['data_clk', 'data_rf', 'data_pwr']):
    st.divider()
    t1, t2, t3 = st.tabs(["時鐘比對", "RF 路徑 (Foxconn)", "電源規範"])

    with t1:
        if 'data_clk' in st.session_state:
            data_source = st.session_state['data_clk']
            clk = data_source.get('clock_system', {})
            for label, act, std in [
                ("主頻率", clk.get('freq'), std_xtal), 
                ("負載電容 1", clk.get('cap1'), std_cap1), 
                ("負載電容 2", clk.get('cap2'), std_cap2), 
                ("RTC 頻率", clk.get('rtc'), std_rtc)
            ]:
                msg, _ = judge_logic(act, std)
                st.write(f"🔹 **{label}**: `{act}` (標準: {std}) -> **{msg}**")
        else:
            st.info("請點擊上方按鈕 1 開始分析時鐘")

    with t2:
        if 'data_rf' in st.session_state:
            data_source = st.session_state['data_rf']
            st.subheader("⚡ Pin 2 (Foxconn 實作) 路徑稽核")
            rf_res = []
            path_data = data_source.get("rf_path", [])
            for i in range(3):
                item = path_data[i] if i < len(path_data) else {}
                ui_std = rf_configs[i]['std_val']
                res, _ = judge_logic(item.get('act'), ui_std)
                rf_res.append({
                    "元件位號": item.get('des', '未抓到'),
                    "讀取值 (Actual)": item.get('act', 'N/A'),
                    "標準值 (Standard)": ui_std,
                    "結果判定": res
                })
            st.table(rf_res)
        else:
            st.info("請點擊上方按鈕 2 開始分析 RF 路徑")

    with t3:
        if 'data_pwr' in st.session_state:
            data_source = st.session_state['data_pwr']
            p = data_source.get("power_config", {})
            
            def check_caps(a1, a2, s1, s2):
                r1, b1 = judge_logic(a1, s1); r2, b2 = judge_logic(a2, s2)
                if b1 and b2: return r1, r2
                r1a, b1a = judge_logic(a1, s2); r2a, b2a = judge_logic(a2, s1)
                if b1a and b2a: return "✅ PASS (順序調整)", "✅ PASS (順序調整)"
                return r1, r2

            v_net = p.get('vbat_net')
            st.write(f"⚡ **VBAT 標籤**: `{v_net}` (標準: {std_vbat_v}) -> **{judge_logic(v_net, std_vbat_v)[0]}**")
            
            v_std_list = [x.strip() for x in std_vbat_c.split(',')]
            v_s1 = v_std_list[0] if len(v_std_list) > 0 else ""
            v_s2 = v_std_list[1] if len(v_std_list) > 1 else ""
            
            v1r, v2r = check_caps(p.get('vbat_cap1'), p.get('vbat_cap2'), v_s1, v_s2)
            st.write(f"🔸 **VBAT 電容 1**: `{p.get('vbat_cap1')}` -> **{v1r}**")
            st.write(f"🔸 **VBAT 電容 2**: `{p.get('vbat_cap2')}` -> **{v2r}**")
            
            st.divider()
            
            v_net_io = p.get('vddio_net')
            st.write(f"⚡ **VDDIO 標籤**: `{v_net_io}` (標準: {std_vddio_v}) -> **{judge_logic(v_net_io, std_vddio_v)[0]}**")
            
            c1r, c2r = check_caps(p.get('vddio_cap1'), p.get('vddio_cap2'), std_vddio_c1, std_vddio_c2)
            st.write(f"🔸 **VDDIO 電容 1**: `{p.get('vddio_cap1')}` -> **{c1r}**")
            st.write(f"🔸 **VDDIO 電容 2**: `{p.get('vddio_cap2')}` -> **{c2r}**")
            
            st.divider()
            st.write(f"🔹 **L49 電感**: `{p.get('pin21_l1')}` -> **{judge_logic(p.get('pin21_l1'), std_pin21_l)[0]}**")
            st.write(f"🔹 **C630 電容**: `{p.get('pin21_c14')}` -> **{judge_logic(p.get('pin21_c14'), std_pin21_c)[0]}**")
        else:
            st.info("請點擊上方按鈕 3 開始分析電源系統")