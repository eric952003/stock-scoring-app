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

@st.cache_data(ttl=3600)
def fetch_and_calculate(ticker, period="1y"):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        info = stock.info
        if hist.empty: return None, None
            
        hist = calculate_technical_indicators(hist)
        latest = hist.iloc[-1]
        stock_name = info.get('shortName', ticker)
        
        pe_ratio = info.get('trailingPE', 0)
        if pe_ratio is None or math.isnan(pe_ratio): pe_ratio = 0
            
        dividend_yield = info.get('dividendYield', 0)
        if dividend_yield is None or math.isnan(dividend_yield): dividend_yield = 0
        else: dividend_yield *= 100
        
        metrics = {
            "名稱": stock_name,
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

# --- 新增：大盤環境監測函式 ---
@st.cache_data(ttl=1800) # 半小時更新一次大盤
def fetch_market_environment():
    try:
        # 抓取大盤、費半、VIX 歷史資料
        twii = yf.Ticker("^TWII").history(period="6mo")
        sox = yf.Ticker("^SOX").history(period="1mo")
        vix = yf.Ticker("^VIX").history(period="1mo")

        if twii.empty: return None

        # 計算大盤布林通道與均線
        twii['MA20'] = twii['Close'].rolling(window=20).mean()
        twii['MA60'] = twii['Close'].rolling(window=60).mean()
        std = twii['Close'].rolling(window=20).std()
        twii['Upper'] = twii['MA20'] + 2 * std
        twii['Lower'] = twii['MA20'] - 2 * std

        # 計算大盤 ATR (真實波動幅度, 14天)
        high_low = twii['High'] - twii['Low']
        high_close = (twii['High'] - twii['Close'].shift()).abs()
        low_close = (twii['Low'] - twii['Close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        twii['ATR'] = tr.rolling(window=14).mean()

        latest_twii = twii.iloc[-1]
        prev_twii = twii.iloc[-2]
        twii_change = latest_twii['Close'] - prev_twii['Close']
        
        latest_sox_pct = ((sox['Close'].iloc[-1] - sox['Close'].iloc[-2]) / sox['Close'].iloc[-2]) * 100 if len(sox) > 1 else 0
        latest_vix = vix['Close'].iloc[-1] if len(vix) > 0 else 0

        return {
            "TWII_Data": twii,
            "Close": round(latest_twii['Close'], 2),
            "Change": round(twii_change, 2),
            "MA20": round(latest_twii['MA20'], 2),
            "MA60": round(latest_twii['MA60'], 2),
            "Upper": round(latest_twii['Upper'], 2),
            "Lower": round(latest_twii['Lower'], 2),
            "ATR": round(latest_twii['ATR'], 2),
            "SOX_Pct": round(latest_sox_pct, 2),
            "VIX": round(latest_vix, 2)
        }
    except Exception as e:
        return None

def plot_candlestick_chart(df, ticker):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, subplot_titles=(f'{ticker} 近半年走勢圖', 'KD 指標'), row_width=[0.3, 0.7])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='red', decreasing_line_color='green', name='K線'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='orange', width=2), name='季線 (60MA)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='blue', width=1.5), name='K值'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', width=1.5, dash='dot'), name='D值'), row=2, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1)
    fig.update_layout(height=550, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False, hovermode="x unified")
    return fig

# --- 繪製大盤專用圖表 (含布林通道) ---
def plot_market_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='red', decreasing_line_color='green', name='加權指數'))
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1.5), name='月線 (20MA)'))
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='purple', width=2), name='季線 (60MA)'))
    fig.add_trace(go.Scatter(x=df.index, y=df['Upper'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'))
    fig.add_trace(go.Scatter(x=df.index, y=df['Lower'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌', fill='tonexty', fillcolor='rgba(128, 128, 128, 0.1)'))
    fig.update_layout(height=450, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False, hovermode="x unified", title="台灣加權指數與布林通道")
    return fig

def get_score_and_details(asset_type, stock_metrics):
    score = 0
    score_details = []
    k, d, price, ma60 = stock_metrics['K值'], stock_metrics['D值'], stock_metrics['收盤價'], stock_metrics['MA60']
    
    if "一般股票" in asset_type:
        pe = stock_metrics['本益比']
        if 0 < pe < 15: score += 40; score_details.append("✅ 本益比小於 15: +40 分")
        elif 15 <= pe < 22: score += 20; score_details.append("✅ 本益比介於 15~22: +20 分")
        else: score_details.append("❌ 本益比過高或無獲利: +0 分")
        if stock_metrics['殖利率 (%)'] > 4: score += 20; score_details.append("✅ 殖利率大於 4%: +20 分")
        else: score_details.append("❌ 殖利率小於 4%: +0 分")
        if k > d: score += 20; score_details.append("✅ KD 黃金交叉: +20 分")
        else: score_details.append("❌ KD 死亡交叉: +0 分")
        if price > ma60: score += 20; score_details.append("✅ 股價站上季線: +20 分")
        else: score_details.append("❌ 股價跌破季線: +0 分")
            
    elif "高股息 ETF" in asset_type:
        if k < 30: score += 50; score_details.append("✅ KD 極度超賣 (K < 30): +50 分")
        elif k < 50: score += 30; score_details.append("✅ KD 處於中低檔 (K < 50): +30 分")
        else: score_details.append("❌ KD 處於高檔: +0 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        else: score_details.append("❌ KD 死亡交叉: +0 分")
        if price <= ma60: score += 20; score_details.append("✅ 股價跌破季線 (越跌越買): +20 分")
        else: score_details.append("❌ 股價在季線之上: +0 分")
            
    elif "市值型 ETF" in asset_type:
        if price > ma60: score += 50; score_details.append("✅ 股價站上季線: +50 分")
        else: score_details.append("❌ 股價跌破季線: +0 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        else: score_details.append("❌ KD 死亡交叉: +0 分")
        if 40 < k < 80: score += 20; score_details.append("✅ K值 位於 40~80: +20 分")
        else: score_details.append("❌ K值 過熱或過冷: +0 分")
            
    elif "債券 ETF" in asset_type:
        if k < 25: score += 60; score_details.append("✅ KD 嚴重超賣 (K < 25): +60 分")
        elif k < 40: score += 30; score_details.append("✅ KD 處於低檔 (K < 40): +30 分")
        else: score_details.append("❌ KD 處於高檔: +0 分")
        if k > d: score += 40; score_details.append("✅ KD 黃金交叉: +40 分")
        else: score_details.append("❌ KD 死亡交叉: +0 分")
            
    elif "主動型" in asset_type:
        if price > ma60: score += 40; score_details.append("✅ 股價站上季線: +40 分")
        else: score_details.append("❌ 股價跌破季線: +0 分")
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉: +30 分")
        else: score_details.append("❌ KD 死亡交叉: +0 分")
        if k > 60: score += 30; score_details.append("✅ K值 大於 60 (動能強): +30 分")
        elif k > 40: score += 10; score_details.append("✅ K值 大於 40: +10 分")
        else: score_details.append("❌ K值 低迷: +0 分")

    return min(score, 100), score_details

def run_backtest(df, strategy_type):
    trades = []
    holding = False
    buy_price = 0
    buy_date = None
    
    df = df.dropna()
    for i in range(1, len(df)):
        curr_k, prev_k = df['K'].iloc[i], df['K'].iloc[i-1]
        curr_d, prev_d = df['D'].iloc[i], df['D'].iloc[i-1]
        close, ma60 = df['Close'].iloc[i], df['MA60'].iloc[i]
        date = df.index[i].strftime('%Y-%m-%d')
        
        buy_signal, sell_signal = False, False
        if strategy_type == "波段動能 (順勢)":
            buy_signal = (close > ma60) and (prev_k <= prev_d) and (curr_k > curr_d)
            sell_signal = (close < ma60) or ((prev_k >= prev_d) and (curr_k < curr_d))
        elif strategy_type == "低檔逆勢 (存股)":
            buy_signal = (curr_k < 30) and (prev_k <= prev_d) and (curr_k > curr_d)
            sell_signal = (curr_k > 70) and (prev_k >= prev_d) and (curr_k < curr_d)
            
        if buy_signal and not holding:
            buy_price = close
            buy_date = date
            holding = True
        elif sell_signal and holding:
            sell_price = close
            ret = (sell_price - buy_price) / buy_price
            trades.append({"買進日期": buy_date, "買進價": round(buy_price, 2), "賣出日期": date, "賣出價": round(sell_price, 2), "報酬率(%)": round(ret * 100, 2)})
            holding = False
            
    return pd.DataFrame(trades)

# ==========================================
# 建立分頁介面 (Tabs) - 擴增為 5 頁
# ==========================================
tab_market, tab1, tab2, tab3, tab4 = st.tabs(["🌐 大盤氣象局", "📊 單檔深度分析", "🔍 批次掃描器", "⏱️ 歷史回測", "🧬 ETF 透視"])

# --- 第零頁：大盤環境氣象局 ---
with tab_market:
    st.markdown("### 🌐 大盤環境與波動度監測")
    st.info("💡 **量化心法：** 先看環境，再看個股。如果大盤處於空頭或恐慌狀態，請降低選股系統的買進部位。")
    
    with st.spinner("獲取全球市場數據中..."):
        market_data = fetch_market_environment()
        
    if market_data:
        m_close = market_data["Close"]
        m_change = market_data["Change"]
        m_ma20 = market_data["MA20"]
        m_ma60 = market_data["MA60"]
        atr = market_data["ATR"]
        vix = market_data["VIX"]
        sox_pct = market_data["SOX_Pct"]
        
        # 1. 頂部數據看板
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("台股加權指數", f"{m_close:,.0f}", f"{m_change:,.0f}")
        c2.metric("預估波動區間 (ATR)", f"± {atr:,.0f} 點", help="依據近期走勢，今日合理的上下震盪點數")
        c3.metric("美股 VIX 恐慌指數", vix, "危險 > 20" if vix > 20 else "安全", delta_color="inverse")
        c4.metric("美股費半指數變化", f"{sox_pct}%", help="台股高度連動費城半導體")
        
        st.divider()
        
        # 2. 趨勢風向球判定
        st.subheader("🧭 當前大盤資金控管建議")
        
        if vix > 20 or sox_pct < -3:
            st.error("🚨 **外部系統性風險警示！** VIX 飆高或費半重挫。建議今日**多看少做，暫緩新部位買進**，並檢查持股停損點。")
        elif m_close > m_ma20 and m_ma20 > m_ma60:
            st.success("🟢 **多頭順風區：** 指數站上月線且多頭排列。環境極佳，個股選股系統勝率高，可積極操作。")
        elif m_close < m_ma60:
            st.warning("🔴 **空頭逆風區：** 指數跌破季線 (牛熊分界)。覆巢之下無完卵，**強烈建議降低持股水位至 3 成以下**。")
        else:
            st.info("🟡 **震盪整理區：** 指數在均線間糾結。大盤缺乏明確方向，適合逢低佈局高股息，波段操作見好就收。")
            
        # 3. 大盤走勢與布林通道
        st.divider()
        st.markdown("#### 📈 加權指數技術面與布林通道")
        st.markdown(f"**布林上軌：** `{market_data['Upper']:,.0f}` (壓力區) ｜ **布林下軌：** `{market_data['Lower']:,.0f}` (支撐區)")
        
        if m_close >= market_data['Upper']:
            st.error("🔥 注意：大盤已觸碰布林上軌，短線過熱，隨時可能面臨拉回修正。")
        elif m_close <= market_data['Lower']:
            st.success("🧊 注意：大盤已觸碰布林下軌，短線跌幅已深，乖離過大可能醞釀反彈。")
            
        fig_market = plot_market_chart(market_data["TWII_Data"].tail(120))
        st.plotly_chart(fig_market, use_container_width=True)
        
    else:
        st.error("無法連線取得大盤數據，請確認網路狀態或稍後再試。")

# --- 其他頁籤 (預設股票代碼邏輯) ---
default_ticker = "2330.TW"
if "高股息" in asset_type: default_ticker = "00878.TW"
elif "市值型" in asset_type: default_ticker = "0050.TW"
elif "債券" in asset_type: default_ticker = "00720B.TW"
elif "主動型" in asset_type: default_ticker = "00403A.TW"

# --- 第一頁：單檔深度分析 ---
with tab1:
    ticker_input = st.sidebar.text_input("輸入股票代碼 (台股請加 .TW)", default_ticker)
    with st.spinner("抓取數據與繪圖中..."):
        hist_data, stock_metrics = fetch_and_calculate(ticker_input)
    if stock_metrics:
        st.subheader(f"📊 {ticker_input} ({stock_metrics['名稱']}) 當前數據")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最新收盤價", stock_metrics["收盤價"])
        col4.metric("KD (K值)", stock_metrics["K值"])
        if "一般股票" in asset_type:
            col2.metric("本益比 (P/E)", stock_metrics["本益比"])
            col3.metric("殖利率", f"{stock_metrics['殖利率 (%)']} %")
        elif "高股息" in asset_type:
            col2.metric("殖利率 (系統預估)", f"{stock_metrics['殖利率 (%)']} %")
            col3.metric("技術指標", "K > D (黃金交叉)" if stock_metrics["K值"] > stock_metrics["D值"] else "K < D (死亡交叉)")
        else:
            col2.metric("季線 (60MA)", stock_metrics["MA60"])
            col3.metric("技術指標", "K > D (黃金交叉)" if stock_metrics["K值"] > stock_metrics["D值"] else "K < D (死亡交叉)")
        st.divider()
        plot_data = hist_data.tail(120) 
        fig = plot_candlestick_chart(plot_data, ticker_input)
        st.plotly_chart(fig, use_container_width=True)
        st.divider()
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
    else: st.error("無法獲取數據，請確認代碼。")

# --- 第二頁：批次掃描器 ---
with tab2:
    st.markdown("### 🔍 多檔標的批次掃描")
    default_batch = "0056.TW, 00878.TW, 00713.TW, 00919.TW, 00929.TW" if "高股息" in asset_type else "2330.TW, 2317.TW, 2454.TW, 2382.TW, 3231.TW"
    batch_input = st.text_area("輸入多檔股票代碼 (請用逗號分隔)：", default_batch)
    if st.button("🚀 開始批次掃描"):
        tickers = [t.strip() for t in batch_input.split(",") if t.strip()]
        if tickers:
            progress_bar = st.progress(0)
            results = []
            for i, t in enumerate(tickers):
                hist, metrics = fetch_and_calculate(t)
                if metrics:
                    score, _ = get_score_and_details(asset_type, metrics)
                    results.append({"代碼": t, "標的名稱": metrics["名稱"], "綜合評分": score, "收盤價": metrics["收盤價"]})
                progress_bar.progress((i + 1) / len(tickers))
            if results:
                df_results = pd.DataFrame(results).sort_values(by="綜合評分", ascending=False).reset_index(drop=True)
                st.dataframe(df_results, use_container_width=True)

# --- 第三頁：歷史回測驗證 ---
with tab3:
    st.markdown("### ⏱️ 策略歷史回測 (近3年)")
    col_a, col_b = st.columns(2)
    backtest_ticker = col_a.text_input("測試股票代碼 (台股請加 .TW)", default_ticker, key="bt_ticker")
    strategy_choice = col_b.selectbox("選擇回測策略邏輯", ["波段動能 (順勢)", "低檔逆勢 (存股)"])
    if st.button("📊 執行歷史回測"):
        bt_hist, bt_metrics = fetch_and_calculate(backtest_ticker, period="3y")
        if bt_hist is not None and not bt_hist.empty:
            trade_record = run_backtest(bt_hist, strategy_choice)
            if not trade_record.empty:
                st.dataframe(trade_record, use_container_width=True)
            else: st.warning("📉 無觸發進出場訊號。")

# --- 第四頁：ETF 成分股透視 (X-Ray) ---
with tab4:
    st.markdown("### 🧬 ETF 成分股健康度透視 (X-Ray)")
    etf_options = ["00878 國泰永續高股息", "0056 元大高股息", "00713 元大台灣高息低波", "00929 復華台灣科技優息", "➕ 自訂 ETF (手動輸入成分股)"]
    selected_etf_option = st.selectbox("請選擇要透視的 ETF，或自訂輸入", etf_options)
    
    if selected_etf_option == "➕ 自訂 ETF (手動輸入成分股)":
        custom_etf_name = st.text_input("📝 自訂 ETF 名稱", "00919 群益台灣精選高息")
        custom_components = st.text_area("📋 成分股代碼 (逗號分隔)", "2603.TW, 2609.TW, 2454.TW, 5483.TW, 2886.TW, 2385.TW, 5347.TW, 2303.TW, 2892.TW, 2615.TW")
        selected_etf, components = custom_etf_name, [t.strip() for t in custom_components.split(",") if t.strip()]
    else:
        components_map = {
            "00878 國泰永續高股息": ["2357.TW", "2449.TW", "2382.TW", "3231.TW", "2379.TW", "2301.TW", "1101.TW", "2891.TW", "2881.TW", "2324.TW"],
            "0056 元大高股息": ["2317.TW", "2454.TW", "3231.TW", "2303.TW", "2382.TW", "2357.TW", "3034.TW", "2891.TW", "2324.TW", "2353.TW"],
            "00713 元大台灣高息低波": ["2881.TW", "2882.TW", "2317.TW", "2303.TW", "2886.TW", "2891.TW", "1101.TW", "2382.TW", "5880.TW", "2412.TW"],
            "00929 復華台灣科技優息": ["2454.TW", "2303.TW", "3034.TW", "2357.TW", "3711.TW", "2382.TW", "2324.TW", "3231.TW", "2379.TW", "4938.TW"]
        }
        selected_etf, components = selected_etf_option, components_map[selected_etf_option]
        
    if st.button(f"🚀 開始 X-Ray 透視 {selected_etf}"):
        if components:
            progress_bar_xray = st.progress(0)
            results_xray, total_score = [], 0
            for i, t in enumerate(components):
                hist, metrics = fetch_and_calculate(t)
                if metrics:
                    score, _ = get_score_and_details("一般股票", metrics)
                    total_score += score
                    results_xray.append({"成分股代碼": t, "名稱": metrics["名稱"], "個股分數": score})
                progress_bar_xray.progress((i + 1) / len(components))
            if results_xray:
                df_xray = pd.DataFrame(results_xray).sort_values(by="個股分數", ascending=False).reset_index(drop=True)
                st.dataframe(df_xray, use_container_width=True)
