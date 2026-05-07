import streamlit as st
from google import genai
import json
import re

# --- 1. 初始化 (從 Streamlit Secrets 讀取，安全捕捉報錯) ---
try:
    # 嘗試從 Secrets 讀取
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
except Exception:
    # 如果完全找不到 secrets.toml 或是讀取失敗，將變數設為 None
    GEMINI_API_KEY = None

if not GEMINI_API_KEY:
    # 在本地端或未設定 Secret 的情況下，顯示側邊欄輸入框
    GEMINI_API_KEY = st.sidebar.text_input("請輸入新產生的 Gemini API Key", type="password")

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
f_ref = st.file_uploader("1. 上傳公版 PDF", type="pdf")
f_imp = st.file_uploader("2. 上傳實作 PDF", type="pdf")

if st.button("🚀 啟動全方位稽核"):
    if GEMINI_API_KEY and f_ref and f_imp:
        with st.spinner("正在進行視覺強化掃描..."):
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                
                PROMPT = f"""
                你是專業硬體稽核專家。請分析實作圖紙 (Foxconn Implementation) 並嚴格執行：

                1. RF 路徑精準辨識：
                   - 定位到 Pin 2 (WL/BT_ANT0) 往外延伸的走線。
                   - 找到元件 C628, C627, C626。
                   - **核心動作**：請檢查每個元件符號的正下方是否有 'NI'。
                   - 若有 'NI'，act 欄位必須回傳 "NI"。不要只回傳 10pF。

                2. 電源區塊排除干擾：
                   - Pin 9 (VBAT): 必須找 C 開頭的元件值 (如 4.7uF)。如果讀到 3.3V，那是電壓，請跳過。提取兩顆電容分別放入 vbat_cap1, vbat_cap2。
                   - VDDIO 電壓標籤 請Scan Foxconn 圖紙 找到VBAT3.3V or VBAT:3.3V 相關字眼
                   - Pin 22 (VDDIO): 必須找 VDDIO 或 PWR_1V8 等標籤。
                   - Pin 21 (ASR_VLX): 找到L49跟C630。分別提取感值跟容值分別放入 pin21_l1, pin21_c14。
                回傳純 JSON：
                {{
                  "clock_system": {{ "freq", "cap1", "cap2", "rtc" }},
                  "rf_path": [ {{ "des": "C628", "act": "NI" }}, {{ "des": "C627", "act": "10pF" }}, {{ "des": "C626", "act": "NI" }} ],
                  "power_config": {{ "vbat_net", "vbat_cap1", "vbat_cap2", "vddio_net", "vddio_cap1", "vddio_cap2", "pin21_l1", "pin21_c14" }}
                }}
                """
                
                response = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=[
                        genai.types.Part.from_bytes(data=f_ref.read(), mime_type="application/pdf"),
                        PROMPT,
                        genai.types.Part.from_bytes(data=f_imp.read(), mime_type="application/pdf")
                    ]
                )
                
                data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
                st.success("稽核完成！")
                
                t1, t2, t3 = st.tabs(["時鐘比對", "RF 路徑 (Foxconn)", "電源規範"])
                
                with t1:
                    clk = data.get('clock_system', {})
                    for label, act, std in [("主頻率", clk.get('freq'), std_xtal), ("負載電容 1", clk.get('cap1'), std_cap1), ("負載電容 2", clk.get('cap2'), std_cap2), ("RTC 頻率", clk.get('rtc'), std_rtc)]:
                        msg, _ = judge_logic(act, std)
                        st.write(f"🔹 **{label}**: `{act}` (標準: {std}) -> **{msg}**")

                with t2:
                    st.subheader("⚡ Pin 2 (Foxconn 實作) 路徑稽核")
                    rf_res = []
                    path_data = data.get("rf_path", [])
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

                with t3:
                    p = data.get("power_config", {})
                    
                    # 交叉檢查電容函式
                    def check_caps(a1, a2, s1, s2):
                        r1, b1 = judge_logic(a1, s1); r2, b2 = judge_logic(a2, s2)
                        if b1 and b2: return r1, r2
                        r1a, b1a = judge_logic(a1, s2); r2a, b2a = judge_logic(a2, s1)
                        if b1a and b2a: return "✅ PASS (順序調整)", "✅ PASS (順序調整)"
                        return r1, r2

                    # VBAT 判定
                    v_net = p.get('vbat_net')
                    st.write(f"⚡ **VBAT 標籤**: `{v_net}` (標準: {std_vbat_v}) -> **{judge_logic(v_net, std_vbat_v)[0]}**")
                    
                    # 拆分 VBAT UI 標準值 (4.7uF, 1uF)
                    v_std_list = [x.strip() for x in std_vbat_c.split(',')]
                    v_s1 = v_std_list[0] if len(v_std_list) > 0 else ""
                    v_s2 = v_std_list[1] if len(v_std_list) > 1 else ""
                    
                    # 使用交叉檢查比對 VBAT 的兩顆電容
                    v1r, v2r = check_caps(p.get('vbat_cap1'), p.get('vbat_cap2'), v_s1, v_s2)
                    st.write(f"🔸 **VBAT 電容 1**: `{p.get('vbat_cap1')}` -> **{v1r}**")
                    st.write(f"🔸 **VBAT 電容 2**: `{p.get('vbat_cap2')}` -> **{v2r}**")
                    
                    st.divider()
                    
                    # VDDIO 判定
                    v_net_io = p.get('vddio_net')
                    st.write(f"⚡ **VDDIO 標籤**: `{v_net_io}` (標準: {std_vddio_v}) -> **{judge_logic(v_net_io, std_vddio_v)[0]}**")
                    
                    c1r, c2r = check_caps(p.get('vddio_cap1'), p.get('vddio_cap2'), std_vddio_c1, std_vddio_c2)
                    st.write(f"🔸 **VDDIO 電容 1**: `{p.get('vddio_cap1')}` -> **{c1r}**")
                    st.write(f"🔸 **VDDIO 電容 2**: `{p.get('vddio_cap2')}` -> **{c2r}**")
                    
                    st.divider()
                    st.write(f"🔹 **L1 電感**: `{p.get('pin21_l1')}` -> **{judge_logic(p.get('pin21_l1'), std_pin21_l)[0]}**")
                    st.write(f"🔹 **C14 電容**: `{p.get('pin21_c14')}` -> **{judge_logic(p.get('pin21_c14'), std_pin21_c)[0]}**")

            except Exception as e:
                st.error(f"分析失敗: {e}")