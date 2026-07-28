import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 頁面基本設定
st.set_page_config(page_title="量化選股決策系統", layout="wide")
st.title("📈 雙模式量化選股決策系統")

# 2. 側邊欄設定
st.sidebar.header("參數設定")
strategy_mode = st.sidebar.selectbox("選擇評分策略", ["高股息/價值型", "成長型/動能型"])
ticker_input = st.sidebar.text_input("輸入股票代碼 (台股請加 .TW，如 2330.TW)", "2330.TW")

# --- 計算 KD 值與進階均線的函式 ---
def calculate_technical_indicators(df, n=9):
    # KD 計算
    low_min = df['Low'].rolling(window=n).min()
    high_max = df['High'].rolling(window=n).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # 新增：季線 (60MA) 計算
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # 新增：近 10 日最低價 (作為停損參考)
    df['10_Day_Low'] = df['Low'].rolling(window=10).min()
    
    return df

# 3. 定義獲取資料的函式
@st.cache_data
def fetch_and_calculate(ticker):
    try:
        stock = yf.Ticker(ticker)
        # 為了計算準確的季線 (60天)，我們需要抓取更長的歷史資料 (至少半年)
        hist = stock.history(period="1y")
        info = stock.info
        
        if hist.empty:
            return None, None
            
        # 計算技術指標
        hist = calculate_technical_indicators(hist)
        
        # 取得最新一天的數據
        latest = hist.iloc[-1]
        
        # 取得基本面數據
        pe_ratio = info.get('trailingPE', 0)
        dividend_yield = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        
        metrics = {
            "收盤價": round(latest['Close'], 2),
            "K值": round(latest['K'], 2) if not pd.isna(latest['K']) else 0,
            "D值": round(latest['D'], 2) if not pd.isna(latest['D']) else 0,
            "MA60": round(latest['MA60'], 2) if not pd.isna(latest['MA60']) else 0,
            "停損參考價": round(latest['10_Day_Low'], 2) if not pd.isna(latest['10_Day_Low']) else 0,
            "本益比": round(pe_ratio, 2) if pe_ratio else 0,
            "殖利率 (%)": round(dividend_yield, 2) if dividend_yield else 0
        }
        return hist, metrics
    except Exception as e:
        return None, None

# 執行運算
with st.spinner("抓取數據與計算中..."):
    hist_data, stock_metrics = fetch_and_calculate(ticker_input)

# 4. 顯示結果與決策
if stock_metrics:
    st.subheader(f"📊 {ticker_input} 當前數據")
    
    # 顯示核心數據
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新收盤價", stock_metrics["收盤價"])
    col2.metric("本益比 (P/E)", stock_metrics["本益比"])
    col3.metric("殖利率", f"{stock_metrics['殖利率 (%)']} %")
    col4.metric("KD (K值)", stock_metrics["K值"])
    
    st.divider()
    
    # --- 評分邏輯 ---
    score = 0
    if strategy_mode == "高股息/價值型":
        if stock_metrics['殖利率 (%)'] > 5: score += 40
        elif stock_metrics['殖利率 (%)'] > 3: score += 20
        if 0 < stock_metrics['本益比'] < 15: score += 40
        elif 15 <= stock_metrics['本益比'] < 20: score += 20
        if stock_metrics['K值'] < 30: score += 20 
        
    elif strategy_mode == "成長型/動能型":
        if stock_metrics['K值'] > stock_metrics['D值']: score += 40 
        elif stock_metrics['K值'] > 30 and (stock_metrics['D值'] - stock_metrics['K值']) < 5: score += 20
        if stock_metrics['K值'] > 75: score += 20 
        elif stock_metrics['K值'] > 50: score += 10 
        pe = stock_metrics['本益比']
        if pe == 0: score += 10 
        elif 0 < pe < 30: score += 40 
        elif 30 <= pe < 50: score += 20 
    
    # --- 關鍵決策輔助模組 (新增) ---
    st.subheader("🛡️ 決策輔助與行動建議")
    
    # 1. 趨勢保護傘 (MA60 判定)
    is_above_ma60 = stock_metrics['收盤價'] > stock_metrics['MA60']
    trend_color = "🟢" if is_above_ma60 else "🔴"
    trend_text = "多頭排列 (站上季線)" if is_above_ma60 else "空頭弱勢 (跌破季線)"
    
    st.markdown(f"**長線趨勢：** {trend_color} {trend_text}  *(季線位置: ${stock_metrics['MA60']})*")
    
    # 2. 自動行動建議
    if not is_above_ma60:
        st.warning("⚠️ **警告：股價處於季線之下，屬於長線空頭或弱勢整理格局。為避免「接刀」風險，強烈建議空手觀望，即使綜合評分高也不宜重壓。**")
    elif score >= 60:
        st.success(f"✅ **建議：條件滿足，可考慮分批進場。**\n\n🎯 **【強制防守線】：請將停損價設定在近10日低點 $ {stock_metrics['停損參考價']}**。若收盤跌破此價位，代表短期防線崩潰，請無條件撤退，保護本金。")
    elif score >= 40:
        st.info("⏳ **建議：動能或估值處於尷尬期。持股者可續抱，空手者建議等待回檔或訊號更明確時再進場。**")
    else:
        st.error("🚨 **建議：風險過高或動能嚴重轉弱。建議避開，若有持股應考慮減碼或嚴格執行停損。**")
    
    st.divider()
    
    # --- 顯示最終分數 ---
    st.subheader("🎯 策略綜合評分")
    st.progress(score / 100)
    st.markdown(f"### **{score}** / 100")
    
    # 評分指南摺疊區保留...
    with st.expander("📖 評分指南與分數意義 (點擊展開)"):
        st.markdown("分數高低僅代表符合該策略條件的程度。請務必搭配上方的「長線趨勢」與「強制防守線」來制定最終交易計畫。")
    
else:
    st.error("無法獲取數據，請確認股票代碼是否正確。")
