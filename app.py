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

default_ticker = "2330.TW"
if "高股息" in asset_type: default_ticker = "00878.TW"
elif "市值型" in asset_type: default_ticker = "0050.TW"
elif "債券" in asset_type: default_ticker = "00720B.TW"
elif "主動型" in asset_type: default_ticker = "00403A.TW"

ticker_input = st.sidebar.text_input("輸入股票代碼 (台股請加 .TW)", default_ticker)

# --- 計算技術指標函式 ---
def calculate_technical_indicators(df, n=9):
    low_min = df['Low'].rolling(window=n).min()
    high_max = df['High'].rolling(window=n).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['10_Day_Low'] = df['Low'].rolling(window=10).min()
    return df

# --- 繪製互動式 K 線圖函式 ---
def plot_candlestick_chart(df, ticker):
    # 建立包含兩個子圖的圖表 (上: K線與均線, 下: KD)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'{ticker} 近半年走勢圖', 'KD 指標'),
                        row_width=[0.3, 0.7])

    # 1. 畫 K 線
    fig.add_trace(go.Candlestick(x=df.index,
                                 open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'],
                                 increasing_line_color='red', decreasing_line_color='green',
                                 name='K線'), row=1, col=1)
    
    # 2. 畫季線 (MA60)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], 
                             line=dict(color='orange', width=2), 
                             name='季線 (60MA)'), row=1, col=1)
    
    # 3. 畫 KD 指標
    fig.add_trace(go.Scatter(x=df.index, y=df['K'], line=dict(color='blue', width=1.5), name='K值'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['D'], line=dict(color='orange', width=1.5, dash='dot'), name='D值'), row=2, col=1)
    
    # 加上超買超賣線 (80, 20)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1, annotation_text="過熱區")
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1, annotation_text="超賣區")

    # 版面設定優化
    fig.update_layout(height=550, margin=dict(l=0, r=0, t=30, b=0),
                      xaxis_rangeslider_visible=False,
                      hovermode="x unified")
    return fig

# 3. 獲取資料函式
@st.cache_data
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

# 執行運算
with st.spinner("抓取數據與繪圖中..."):
    hist_data, stock_metrics = fetch_and_calculate(ticker_input)

# 4. 顯示結果與獨立計分引擎
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
        col3.metric("技術指標狀態", "K > D (黃金交叉)" if stock_metrics["K值"] > stock_metrics["D值"] else "K < D (死亡交叉)")
    else:
        col2.metric("季線 (60MA)", stock_metrics["MA60"])
        col3.metric("技術指標狀態", "K > D (黃金交叉)" if stock_metrics["K值"] > stock_metrics["D值"] else "K < D (死亡交叉)")

    with st.expander("💡 點我查看：上方數據名詞解釋"):
        st.markdown("""
        * **本益比 (P/E)：** 股價除以每股盈餘。代表買進後需要多少年回本，數字越小通常代表估值越便宜。
        * **殖利率 (%)：** 過去一年發放的現金股利佔目前股價的比例。類似銀行定存利率，越高代表領息越豐厚。
        * **KD (K值)：** 反映近期股價強弱的動能指標。**K > 80** 代表短線過熱；**K < 20** 代表短線跌深。
        * **季線 (60MA)：** 過去 60 個交易日的平均收盤價。被視為長線的「生命線」，站上代表多頭，跌破代表空頭。
        * **技術指標狀態：** 黃金交叉 (K > D) 短期買盤力道轉強；死亡交叉 (K < D) 短期賣壓出籠。
        """)

    # --- 繪製並顯示互動式圖表 ---
    st.divider()
    # 為了讓畫面清晰，我們取近半年的資料來畫圖就好
    plot_data = hist_data.tail(120) 
    fig = plot_candlestick_chart(plot_data, ticker_input)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    
    # --- 獨立計分引擎 ---
    score = 0
    score_details = []
    
    k, d, price, ma60 = stock_metrics['K值'], stock_metrics['D值'], stock_metrics['收盤價'], stock_metrics['MA60']
    
    if "一般股票" in asset_type:
        pe = stock_metrics['本益比']
        if 0 < pe < 15: score += 40; score_details.append("✅ 本益比小於 15 (極度便宜): +40 分")
        elif 15 <= pe < 22: score += 20; score_details.append("✅ 本益比介於 15~22 (估值合理): +20 分")
        else: score_details.append("❌ 本益比過高或無獲利: +0 分")
            
        if stock_metrics['殖利率 (%)'] > 4: score += 20; score_details.append("✅ 殖利率大於 4%: +20 分")
        else: score_details.append("❌ 殖利率小於 4%: +0 分")
            
        if k > d: score += 20; score_details.append("✅ KD 黃金交叉 (動能向上): +20 分")
        else: score_details.append("❌ KD 死亡交叉 (動能向下): +0 分")
            
        if price > ma60: score += 20; score_details.append("✅ 股價站上季線 (長線多頭): +20 分")
        else: score_details.append("❌ 股價跌破季線 (長線空頭): +0 分")
            
    elif "高股息 ETF" in asset_type:
        if k < 30: score += 50; score_details.append("✅ KD 極度超賣 (K < 30，適合撿便宜): +50 分")
        elif k < 50: score += 30; score_details.append("✅ KD 處於中低檔 (K < 50，價格合理): +30 分")
        else: score_details.append("❌ KD 處於高檔 (追高風險大): +0 分")
            
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉 (底部成型): +30 分")
        else: score_details.append("❌ KD 死亡交叉 (還在探底): +0 分")
            
        if price <= ma60: score += 20; score_details.append("✅ 股價跌破季線 (高股息專屬加分，越跌越買): +20 分")
        else: score_details.append("❌ 股價在季線之上 (乖離較大): +0 分")
            
    elif "市值型 ETF" in asset_type:
        if price > ma60: score += 50; score_details.append("✅ 股價站上季線 (順應大盤多頭): +50 分")
        else: score_details.append("❌ 股價跌破季線 (大盤弱勢): +0 分")
            
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉 (動能轉強): +30 分")
        else: score_details.append("❌ KD 死亡交叉 (動能轉弱): +0 分")
            
        if 40 < k < 80: score += 20; score_details.append("✅ K值 位於 40~80 (多方穩健攻擊區): +20 分")
        else: score_details.append("❌ K值 過熱或過冷: +0 分")
            
    elif "債券 ETF" in asset_type:
        if k < 25: score += 60; score_details.append("✅ KD 嚴重超賣 (K < 25，債券極佳買點): +60 分")
        elif k < 40: score += 30; score_details.append("✅ KD 處於低檔 (K < 40，具備安全邊際): +30 分")
        else: score_details.append("❌ KD 處於高檔: +0 分")
            
        if k > d: score += 40; score_details.append("✅ KD 黃金交叉 (跌勢停止，確立反轉): +40 分")
        else: score_details.append("❌ KD 死亡交叉 (還在跌): +0 分")
            
    elif "主動型" in asset_type:
        if price > ma60: score += 40; score_details.append("✅ 股價站上季線 (多頭排列): +40 分")
        else: score_details.append("❌ 股價跌破季線 (破壞動能): +0 分")
            
        if k > d: score += 30; score_details.append("✅ KD 黃金交叉 (強勢攻擊): +30 分")
        else: score_details.append("❌ KD 死亡交叉 (攻擊熄火): +0 分")
            
        if k > 60: score += 30; score_details.append("✅ K值 大於 60 (強者恆強，動能極佳): +30 分")
        elif k > 40: score += 10; score_details.append("✅ K值 大於 40 (動能溫和): +10 分")
        else: score_details.append("❌ K值 低迷 (缺乏主力資金): +0 分")

    score = min(score, 100)

    # --- 關鍵決策輔助模組 ---
    st.subheader("🛡️ 決策輔助與行動建議")
    is_above_ma60 = price > ma60
    trend_color = "🟢" if is_above_ma60 else "🔴"
    trend_text = "多頭排列 (站上季線)" if is_above_ma60 else "空頭弱勢 (跌破季線)"
    st.markdown(f"**長線趨勢：** {trend_color} {trend_text}  *(季線位置: ${ma60})*")
    
    if "高股息" in asset_type or "債券" in asset_type:
        if score >= 70: st.success(f"✅ **存股建議：目前處於相對低檔或反轉區間，非常適合分批買進建立部位。**\n\n🎯 **【防守線】：若跌破近10日低點 $ {stock_metrics['停損參考價']}，短線可能持續測底，資金有限者可暫緩加碼。**")
        elif score >= 40: st.info("⏳ **存股建議：位階適中。定期定額者可維持扣款，單筆投入者建議等待更佳的低檔時機。**")
        else: st.warning("⚠️ **存股建議：目前技術面處於高檔熱度區。高股息與債券不建議在此追高，請耐心等待回檔。**")
    else: 
        if not is_above_ma60 and "主動型" in asset_type: st.error("🚨 **警告：主動型/動能標的跌破季線，動能徹底破壞，請嚴格執行停損或避開。**")
        elif score >= 70: st.success(f"✅ **波段建議：動能強勢，條件滿足，可考慮分批進場。**\n\n🎯 **【強制防守線】：請將停損價設定在近10日低點 $ {stock_metrics['停損參考價']}**。若收盤跌破此價位，代表防線崩潰，請無條件撤退。")
        elif score >= 40: st.info("⏳ **波段建議：動能處於尷尬期或正在整理。持股者可續抱，空手者建議觀望。**")
        else: st.warning("⚠️ **波段建議：風險過高或動能嚴重轉弱。若有持股應考慮減碼。**")
    
    st.divider()
    
    # --- 顯示最終分數 ---
    st.subheader(f"🎯 {asset_type.split(' ')[0]} 專屬綜合評分")
    st.progress(score / 100)
    st.markdown(f"### **{score}** / 100")
    
    with st.expander("🧮 算分邏輯大解密與指南 (點擊展開)", expanded=False):
        st.markdown(f"**目前選擇模式：{asset_type}**")
        st.markdown("本系統滿分為 100 分。以下是這檔股票本次拿分的具體細節：")
        for detail in score_details:
            st.write(detail)
            
else:
    st.error("無法獲取數據，請確認股票代碼是否正確。")
