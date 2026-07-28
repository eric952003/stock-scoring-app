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
        
        # 抓取公司名稱，若抓不到則預設顯示代碼
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
# 建立分頁介面 (Tabs)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📊 單檔深度分析", "🔍 批次掃描器", "⏱️ 歷史回測驗證", "🧬 ETF 成分股透視"])

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

        with st.expander("💡 點我查看：上方數據名詞解釋"):
            st.markdown("""
            * **本益比 (P/E)：** 股價除以每股盈餘。代表買進後需要多少年回本，數字越小通常代表估值越便宜。
            * **殖利率 (%)：** 過去一年發放的現金股利佔目前股價的比例。類似銀行定存利率，越高代表領息越豐厚。
            * **KD (K值)：** 反映近期股價強弱的動能指標。**K > 80** 代表短線過熱；**K < 20** 代表短線跌深。
            * **季線 (60MA)：** 過去 60 個交易日的平均收盤價。被視為長線的「生命線」，站上代表多頭，跌破代表空頭。
            * **技術指標狀態：** 黃金交叉 (K > D) 短期買盤力道轉強；死亡交叉 (K < D) 短期賣壓出籠，動能轉弱。
            """)

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
        
        with st.expander("🧮 算分邏輯大解密與指南 (點擊展開)", expanded=False):
            st.markdown(f"**目前選擇模式：{asset_type}**")
            for detail in score_details: st.write(detail)
    else:
        st.error("無法獲取數據，請確認代碼。")

# --- 第二頁：批次掃描器 ---
with tab2:
    st.markdown("### 🔍 多檔標的批次掃描")
    st.info("💡 確保輸入的代碼屬性相同，算出來的比較才有意義。")
    default_batch = "0056.TW, 00878.TW, 00713.TW, 00919.TW, 00929.TW" if "高股息" in asset_type else "2330.TW, 2317.TW, 2454.TW, 2382.TW, 3231.TW"
    batch_input = st.text_area("輸入多檔股票代碼 (請用逗號分隔)：", default_batch)
    
    if st.button("🚀 開始批次掃描"):
        tickers = [t.strip() for t in batch_input.split(",") if t.strip()]
        if not tickers: st.warning("請至少輸入一檔股票代碼！")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            for i, t in enumerate(tickers):
                status_text.text(f"掃描中 ({i+1}/{len(tickers)}) : {t} ...")
                hist, metrics = fetch_and_calculate(t)
                if metrics:
                    score, _ = get_score_and_details(asset_type, metrics)
                    results.append({
                        "代碼": t, 
                        "標的名稱": metrics["名稱"],
                        "綜合評分": score, 
                        "收盤價": metrics["收盤價"],
                        "趨勢 (季線)": "🟢 多頭" if metrics["收盤價"] > metrics["MA60"] else "🔴 空頭",
                        "短線動能 (KD)": "📈 黃金交叉" if metrics["K值"] > metrics["D值"] else "📉 死亡交叉"
                    })
                progress_bar.progress((i + 1) / len(tickers))
            status_text.text("✅ 掃描完成！")
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
        with st.spinner("抓取歷史資料與模擬交易中..."):
            bt_hist, bt_metrics = fetch_and_calculate(backtest_ticker, period="3y")
            if bt_hist is not None and not bt_hist.empty:
                trade_record = run_backtest(bt_hist, strategy_choice)
                if not trade_record.empty:
                    total_trades = len(trade_record)
                    winning_trades = len(trade_record[trade_record["報酬率(%)"] > 0])
                    win_rate = (winning_trades / total_trades) * 100
                    cumulative_return = trade_record["報酬率(%)"].sum()
                    
                    st.divider()
                    st.subheader(f"🏆 回測結果摘要 ({bt_metrics['名稱']} - {strategy_choice})")
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    metric_col1.metric("總交易次數", f"{total_trades} 次")
                    metric_col2.metric("交易勝率", f"{win_rate:.1f} %")
                    metric_col3.metric("累積報酬率", f"{cumulative_return:.2f} %")
                    
                    st.markdown("#### 📜 歷史交易明細")
                    st.dataframe(trade_record, use_container_width=True)
                else: st.warning("📉 在過去 3 年內，該標的沒有觸發任何符合此策略的進出場訊號。")
            else: st.error("無法獲取回測資料。")

# --- 第四頁：ETF 成分股透視 (X-Ray) ---
with tab4:
    st.markdown("### 🧬 ETF 成分股健康度透視 (X-Ray)")
    st.info("💡 這裡我們將 ETF 的「前十大成分股」拆解開來，逐一進行健康度評分，幫你提早預判 ETF 未來的續航力！")
    
    etf_components = {
        "00878 國泰永續高股息": ["2357.TW", "2449.TW", "2382.TW", "3231.TW", "2379.TW", "2301.TW", "1101.TW", "2891.TW", "2881.TW", "2324.TW"],
        "0056 元大高股息": ["2317.TW", "2454.TW", "3231.TW", "2303.TW", "2382.TW", "2357.TW", "3034.TW", "2891.TW", "2324.TW", "2353.TW"],
        "00713 元大台灣高息低波": ["2881.TW", "2882.TW", "2317.TW", "2303.TW", "2886.TW", "2891.TW", "1101.TW", "2382.TW", "5880.TW", "2412.TW"],
        "00929 復華台灣科技優息": ["2454.TW", "2303.TW", "3034.TW", "2357.TW", "3711.TW", "2382.TW", "2324.TW", "3231.TW", "2379.TW", "4938.TW"]
    }
    
    etf_options = list(etf_components.keys()) + ["➕ 自訂 ETF (手動輸入成分股)"]
    selected_etf_option = st.selectbox("請選擇要透視的 ETF，或自訂輸入", etf_options)
    
    components = []
    selected_etf = selected_etf_option
    
    # 處理自訂 ETF 的輸入介面
    if selected_etf_option == "➕ 自訂 ETF (手動輸入成分股)":
        custom_etf_name = st.text_input("📝 請輸入自訂 ETF 名稱 (例如：00919 群益台灣精選高息)", "00919 群益台灣精選高息")
        custom_components = st.text_area("📋 請輸入成分股代碼 (用逗號分隔，建議輸入前十大即可)", "2603.TW, 2609.TW, 2454.TW, 5483.TW, 2886.TW, 2385.TW, 5347.TW, 2303.TW, 2892.TW, 2615.TW")
        selected_etf = custom_etf_name
        components = [t.strip() for t in custom_components.split(",") if t.strip()]
    else:
        components = etf_components[selected_etf_option]
    
    if st.button(f"🚀 開始 X-Ray 透視 {selected_etf}"):
        if not components:
            st.warning("請確保成分股清單不是空白的！")
        else:
            progress_bar_xray = st.progress(0)
            status_text_xray = st.empty()
            results_xray = []
            total_score = 0
            valid_stocks = 0
            
            for i, t in enumerate(components):
                status_text_xray.text(f"正在掃描成分股 ({i+1}/{len(components)}) : {t} ...")
                hist, metrics = fetch_and_calculate(t)
                
                if metrics:
                    # 成分股統一用「一般股票」的邏輯來健檢
                    score, _ = get_score_and_details("一般股票", metrics)
                    total_score += score
                    valid_stocks += 1
                    results_xray.append({
                        "成分股代碼": t,
                        "成分股名稱": metrics["名稱"],
                        "個股健康分數": score,
                        "收盤價": metrics["收盤價"],
                        "趨勢 (季線)": "🟢 多頭" if metrics["收盤價"] > metrics["MA60"] else "🔴 空頭",
                        "短線動能 (KD)": "📈 黃金交叉" if metrics["K值"] > metrics["D值"] else "📉 死亡交叉",
                        "本益比": metrics.get("本益比", 0)
                    })
                    
                progress_bar_xray.progress((i + 1) / len(components))
                
            status_text_xray.text("✅ 透視完成！")
            
            if valid_stocks > 0:
                avg_score = round(total_score / valid_stocks, 1)
                st.divider()
                
                st.subheader(f"🩺 {selected_etf} 內部健康度總評")
                col_s1, col_s2 = st.columns([1, 3])
                col_s1.metric("成分股平均分數", f"{avg_score} / 100")
                
                if avg_score >= 70:
                    col_s2.success("✅ **整體動能強勁！** 成分股多數處於多頭或估值合理區間，ETF 續漲或配息機率高。")
                elif avg_score >= 40:
                    col_s2.info("⏳ **表現中規中矩。** 成分股好壞參半，可能進入盤整，適合定時定額。")
                else:
                    col_s2.warning("⚠️ **內部動能疲弱！** 多數成分股跌破季線或估值過高，短期內 ETF 承壓機率大。")
                    
                st.markdown("#### 🔍 成分股詳細體檢表")
                df_xray = pd.DataFrame(results_xray).sort_values(by="個股健康分數", ascending=False).reset_index(drop=True)
                st.dataframe(df_xray, use_container_width=True)
            else:
                st.error("無法獲取成分股數據，請檢查代碼格式是否正確。")
