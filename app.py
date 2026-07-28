import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 頁面基本設定
st.set_page_config(page_title="量化選股評分模型", layout="wide")
st.title("📈 雙模式量化選股評分模型")

# 2. 側邊欄設定
st.sidebar.header("參數設定")
strategy_mode = st.sidebar.selectbox("選擇評分策略", ["高股息/價值型", "成長型/動能型"])
ticker_input = st.sidebar.text_input("輸入股票代碼 (台股請加 .TW，如 2330.TW)", "2330.TW")

# --- 手動計算 KD 值的函式 ---
def calculate_kd(df, n=9):
    # 計算 RSV
    low_min = df['Low'].rolling(window=n).min()
    high_max = df['High'].rolling(window=n).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    
    # 計算 K 與 D (使用平滑移動平均)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    return df

# 3. 定義獲取資料的函式
@st.cache_data
def fetch_and_calculate(ticker):
    try:
        # 抓取股價與基本面資料
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        info = stock.info
        
        if hist.empty:
            return None, None
            
        # 計算 KD
        hist = calculate_kd(hist)
        
        # 取得最新一天的 K 值與 D 值
        latest_k = hist.iloc[-1]['K']
        latest_d = hist.iloc[-1]['D']
        
        # 取得基本面數據
        pe_ratio = info.get('trailingPE', 0)
        dividend_yield = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        
        # 整理為字典回傳
        metrics = {
            "收盤價": round(hist.iloc[-1]['Close'], 2),
            "K值": round(latest_k, 2) if not pd.isna(latest_k) else 0,
            "D值": round(latest_d, 2) if not pd.isna(latest_d) else 0,
            "本益比": round(pe_ratio, 2) if pe_ratio else 0,
            "殖利率 (%)": round(dividend_yield, 2) if dividend_yield else 0
        }
        return hist, metrics
    except Exception as e:
        return None, None

# 執行運算
with st.spinner("抓取數據與計算中..."):
    hist_data, stock_metrics = fetch_and_calculate(ticker_input)

# 4. 顯示結果與評分
if stock_metrics:
    st.subheader(f"📊 {ticker_input} 當前數據")
    
    # 使用欄位排版顯示數據
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最新收盤價", stock_metrics["收盤價"])
    col2.metric("本益比 (P/E)", stock_metrics["本益比"])
    col3.metric("殖利率", f"{stock_metrics['殖利率 (%)']} %")
    col4.metric("KD (K值)", stock_metrics["K值"])
    
    st.divider()
    st.subheader("🎯 策略評分結果")
    
    score = 0
    if strategy_mode == "高股息/價值型":
        # 著重殖利率與低本益比
        if stock_metrics['殖利率 (%)'] > 5: score += 40
        elif stock_metrics['殖利率 (%)'] > 3: score += 20
        
        if 0 < stock_metrics['本益比'] < 15: score += 40
        elif 15 <= stock_metrics['本益比'] < 20: score += 20
        
        if stock_metrics['K值'] < 30: score += 20 # 技術面低檔防禦
        
    elif strategy_mode == "成長型/動能型":
        # 著重技術面動能與合理的 P/E
        if stock_metrics['K值'] > stock_metrics['D值']: score += 40 # 黃金交叉或維持強勢
        if stock_metrics['K值'] > 50: score += 20 # 動能強
        
        if 0 < stock_metrics['本益比'] < 25: score += 40 # 成長股容許較高 P/E
        
    # 顯示最終分數
    st.progress(score / 100)
    st.markdown(f"### 綜合評分： **{score}** / 100")
    
else:
    st.error("無法獲取數據，請確認股票代碼是否正確（台股記得加上 .TW，如 2330.TW）。")
