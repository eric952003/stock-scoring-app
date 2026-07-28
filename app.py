import streamlit as st
import yfinance as yf
import pandas as pd
import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面基本設定
st.set_page_config(page_title="量化選股決策系統", layout="wide")
st.title("📈 多屬性量化選股決策系統")

# 2. 側邊欄設定
st.sidebar.header("參數設定")
asset_type = st.sidebar.selectbox("選擇標的屬性", [
    "一般股票 (如 2330)",
    "高股息 ETF (如 0056, 00878, 00713, 00929)",
    "市值型 ETF (如 0050, 006208)",
    "債券 ETF (如 00720B, 00679B)",
    "主動型/動能標的 (如 00403A, 飆股)"
])

# --- 核心共用函式 ---
def calculate_technical_indicators(df, n=9):
    low_min = df['Low'].rolling(window=n).min()
    high_max = df['High'].rolling(window=n).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['10_Day_Low'] = df['Low'].rolling(window=10).min()
    return df

@st.cache_data(ttl=3600) # 加入快取時效，避免頻繁抓取
def fetch_and_calculate(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        info = stock.info
        if hist.empty: return None, None
            
        hist = calculate_technical_indicators(hist)
        latest = hist.iloc[-1]
        
        pe_ratio = info.get('trailingPE', 0)
        if pe_ratio is None or math.isnan(pe_ratio): pe_ratio = 0
            
        dividend_yield = info.get('dividendYield', 0)
        if dividend_yield is None or math.isnan(dividend_yield): dividend_yield = 0
        else: dividend_yield *= 100
        
        metrics = {
            "收盤價": round(latest['Close'], 2),
            "K值": round(latest['K'], 2) if not pd.isna(latest['K']) else 0,
            "D值": round(latest['D'], 2) if not pd.isna(latest['D']) else 0,
            "MA60": round(latest['MA60'], 2) if not pd.isna(latest['MA60']) else 0,
            "停損參考價": round(latest['10_Day_Low'], 2) if not pd.isna(latest['10_Day_Low']) else 0,
            "本益比": round(pe_ratio, 2),
            "殖利率 (%)": round(dividend_yield, 2)
        }
        return hist, metrics
    except Exception as e:
        return None, None

def plot_candlestick_chart(df, ticker):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'{ticker} 近半年走勢圖', 'KD 指標'),
                        row_width=[0.3, 0.7])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                                 increasing_line_color='red', decreasing_line_color='green', name='K線'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='orange', width=2), name='季線 (60MA)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='blue', width=1.5), name='K值'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', width=1.5, dash='dot'), name='D值'), row=2, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1)
    fig.update_layout(height=550, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False, hovermode="x unified")
    return fig

# --- 獨立計分引擎 (打包成函式供單檔與批次共用) ---
def get_score_and_details(asset_type, stock_metrics):
    score = 0
    score_details = []
    k, d, price, ma60 = stock_metrics['K值'], stock_metrics['D值'], stock_metrics['收盤價'], stock_metrics['MA60']
    
    if "一般股票" in asset_type:
        pe = stock_metrics['本益比']
        if 0 < pe < 15: score += 40; score_details.append("✅ 本益比 < 15: +40 分")
        elif 15 <= pe < 22: score += 20; score_details.append("✅ 本益比 15~22: +20 分")
        if stock_metrics['殖利率 (%)'] > 4: score += 20; score_details.append("✅ 殖利率 > 4%: +20 分")
        if k > d: score += 20; score_details.append("✅ KD 黃金交叉: +20 分")
        if price > ma60: score += 20; score_details.append("✅ 站上季線: +20 分")
            
    elif "高股息 ETF" in asset_type:
        if k < 30: score += 50; score_details.append("✅ KD < 30 (超賣): +50 分")
        elif k < 50: score += 30; score_details.append("✅ KD < 50 (中低檔): +30 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        if price <= ma60: score += 20; score_details.append("✅ 跌破季線 (適合低接): +20 分")
            
    elif "市值型 ETF" in asset_type:
        if price > ma60: score += 50; score_details.append("✅ 站上季線: +50 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        if 40 < k < 80: score += 20; score_details.append("✅ K值 40~80 穩健區: +20 分")
            
    elif "債券 ETF" in asset_type:
        if k < 25: score += 60; score_details.append("✅ KD < 25 (超賣): +60 分")
        elif k < 40: score += 30; score_details.append("✅ KD < 40 (低檔): +30 分")
        if k > d: score += 40; score_details.append("✅ KD 黃金交叉: +40 分")
            
    elif "主動型" in asset_type:
        if price > ma60: score += 40; score_details.append("✅ 站上季線: +40 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        if k > 60: score += 30; score_details.append("✅ K值 > 60 強勢區: +30 分")
        elif k > 40: score += 10; score_details.append("✅ K值 > 40: +10 分")

    return min(score, 100), score_details


# ==========================================
# 建立分頁介面 (Tabs)
# ==========================================
tab1, tab2 = st.tabs(["📊 單檔深度分析", "🔍 批次掃描器"])

# --- 第一頁：單檔深度分析 ---
with tab1:
    default_ticker = "2330.TW"
    if "高股息" in asset_type: default_ticker = "00878.TW"
    elif "市值型" in asset_type: default_ticker = "0050.TW"
    elif "債券" in asset_type: default_ticker = "00720B.TW"
    elif "主動型" in asset_type: default_ticker = "00403A.TW"
    
    ticker_input = st.sidebar.text_input("輸入股票代碼 (台股請加 .TW)", default_ticker)
    
    with st.spinner("抓取數據與繪圖中..."):
        hist_data, stock_metrics = fetch_and_calculate(ticker_input)
        
    if stock_metrics:
        st.subheader(f"📊 {ticker_input} 當前數據")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最新收盤價", stock_metrics["收盤價"])
        col4.metric("KD (K值)", stock_metrics["K值"])
        
        if "一般股票" in asset_type:
            col2.metric("本益比 (P/E)", stock_metrics["本益比"])
            col3.metric("殖利率", f"{stock_metrics['殖利率 (%)']} %")
        elif "高股息" in asset_type:
            col2.metric("殖利率 (系統預估)", f"{stock_metrics['殖利率 (%)']} %")
            col3.metric("狀態", "黃金交叉" if stock_metrics["K值"] > stock_metrics["D值"] else "死亡交叉")
        else:
            col2.metric("季線 (60MA)", stock_metrics["MA60"])
            col3.metric("狀態", "黃金交叉" if stock_metrics["K值"] > stock_metrics["D值"] else "死亡交叉")

        # 圖表
        st.divider()
        plot_data = hist_data.tail(120) 
        fig = plot_candlestick_chart(plot_data, ticker_input)
        st.plotly_chart(fig, use_container_width=True)
        st.divider()
        
        # 算分與決策
        score, score_details = get_score_and_details(asset_type, stock_metrics)
        price, ma60 = stock_metrics['收盤價'], stock_metrics['MA60']
        is_above_ma60 = price > ma60
        
        st.subheader("🛡️ 決策輔助與行動建議")
        st.markdown(f"**長線趨勢：** {'🟢 多頭排列' if is_above_ma60 else '🔴 空頭弱勢'} *(季線: ${ma60})*")
        
        if "高股息" in asset_type or "債券" in asset_type:
            if score >= 70: st.success(f"✅ **適合分批買進建立部位。** 停損參考: ${stock_metrics['停損參考價']}")
            elif score >= 40: st.info("⏳ **位階適中，單筆投入建議等待低檔。**")
            else: st.warning("⚠️ **技術面偏高，不建議追高。**")
        else: 
            if not is_above_ma60 and "主動型" in asset_type: st.error("🚨 **動能破壞，跌破季線，嚴格避開。**")
            elif score >= 70: st.success(f"✅ **動能強勢，可分批進場。** 停損參考: ${stock_metrics['停損參考價']}")
            elif score >= 40: st.info("⏳ **動能處於整理期，空手者觀望。**")
            else: st.warning("⚠️ **動能轉弱，考慮減碼。**")
            
        st.subheader(f"🎯 綜合評分：{score} / 100")
        st.progress(score / 100)
        with st.expander("🧮 算分邏輯大解密"):
            for detail in score_details: st.write(detail)
    else:
        st.error("無法獲取數據，請確認代碼。")

# --- 第二頁：批次掃描器 ---
with tab2:
    st.markdown("### 🔍 多檔標的批次掃描")
    st.info("💡 **提示：** 程式會根據左側選單的「標的屬性」來評分。請確保輸入的代碼屬性相同（例如左邊選高股息，右邊就輸入一整串高股息 ETF），算出來的比較才有意義。")
    
    # 預設一些名單讓使用者可以直接測試
    default_batch = "0056.TW, 00878.TW, 00713.TW, 00919.TW, 00929.TW" if "高股息" in asset_type else "2330.TW, 2317.TW, 2454.TW, 2382.TW, 3231.TW"
    
    batch_input = st.text_area("輸入多檔股票代碼 (請用逗號分隔)：", default_batch)
    
    if st.button("🚀 開始批次掃描"):
        # 清理輸入字串
        tickers = [t.strip() for t in batch_input.split(",") if t.strip()]
        
        if not tickers:
            st.warning("請至少輸入一檔股票代碼！")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            
            for i, t in enumerate(tickers):
                status_text.text(f"正在掃描 ({i+1}/{len(tickers)}) : {t} ...")
                
                # 呼叫獲取資料函式
                hist, metrics = fetch_and_calculate(t)
                
                if metrics:
                    # 計算分數
                    score, _ = get_score_and_details(asset_type, metrics)
                    
                    # 將結果存入字典
                    results.append({
                        "代碼": t,
                        "綜合評分": score,
                        "收盤價": metrics["收盤價"],
                        "趨勢 (季線)": "🟢 多頭" if metrics["收盤價"] > metrics["MA60"] else "🔴 空頭",
                        "短線動能 (KD)": "📈 黃金交叉" if metrics["K值"] > metrics["D值"] else "📉 死亡交叉",
                        "本益比": metrics.get("本益比", 0),
                        "殖利率 (%)": metrics.get("殖利率 (%)", 0)
                    })
                
                # 更新進度條
                progress_bar.progress((i + 1) / len(tickers))
                
            status_text.text("✅ 掃描完成！以下是排行榜 (已依分數由高至低排序)：")
            
            if results:
                # 轉成 DataFrame 並排序
                df_results = pd.DataFrame(results)
                df_results = df_results.sort_values(by="綜合評分", ascending=False).reset_index(drop=True)
                
                # 在畫面上顯示表格
                st.dataframe(df_results, use_container_width=True)
            else:
                st.error("所有輸入的代碼皆無法獲取數據，請檢查格式是否正確。")
