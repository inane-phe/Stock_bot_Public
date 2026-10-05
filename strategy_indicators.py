# -*- coding: utf-8 -*-
"""
strategy_indicators.py
技術指標與策略訊號模組 - 全網路爬蟲架構 (免 FinMind API / 零連線上限限制)
數據源：yfinance (.TW / .TWO 上市櫃日K線歷史)
計算指標：布林通道(20, 2) ✕ MACD(12, 26, 9) ✕ 均線線型(5MA, 20MA, 60MA) ✕ RSI
附加指標：顏值分數(趨勢 / 碎步上漲 / 52週高點 / 回撤 / 動能 / 波動)
"""
import pandas as pd
import pandas_ta as ta
import yfinance as yf

from strategy_beauty import calculate_beauty_score


def fetch_price_history(stock_id, period="1y"):
    """
    爬取個股歷史K線數據 (上市代號.TW / 上櫃代號.TWO 自動適配)
    回傳具備 standard columns: ['date', 'open', 'high', 'low', 'close', 'volume'] 的 DataFrame
    """
    stock_id = str(stock_id).strip()
    df_price = pd.DataFrame()

    for suffix in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{stock_id}{suffix}")
            df_yf = ticker.history(period=period)
            if not df_yf.empty and len(df_yf) >= 20:
                df_yf = df_yf.reset_index()
                df_yf['date'] = pd.to_datetime(df_yf['Date']).dt.strftime('%Y-%m-%d')
                col_map = {
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume'
                }
                df_yf = df_yf.rename(columns=col_map)
                df_price = df_yf[['date', 'open', 'high', 'low', 'close', 'volume']]
                break
        except Exception:
            continue

    return df_price

def get_technical_indicators(df):
    """
    計算核心技術指標：布林通道(20, 2) ✕ MACD(12, 26, 9) ✕ 均線線型(5MA, 20MA, 60MA)
    """
    df = df.copy()
    col_map = {}
    for c in df.columns:
        clow = str(c).lower().strip()
        if clow in ['max', 'high']: col_map[c] = 'high'
        elif clow in ['min', 'low']: col_map[c] = 'low'
        elif clow in ['trading_volume', 'volume']: col_map[c] = 'volume'
        elif clow in ['close']: col_map[c] = 'close'
        elif clow in ['open']: col_map[c] = 'open'
    df.rename(columns=col_map, inplace=True)
    df = df.sort_values('date').reset_index(drop=True)

    # 1. 布林通道 (20, 2)
    df.ta.bbands(length=20, std=2.0, append=True)
    # 2. MACD (12, 26, 9)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    # 3. 均線線型 (5MA, 20MA, 60MA)
    df.ta.sma(length=5, append=True)
    df.ta.sma(length=20, append=True)
    if len(df) >= 60:
        df.ta.sma(length=60, append=True)
    # 4. RSI (14)
    df.ta.rsi(length=14, append=True)

    return df

def analyze_technical_signals(df):
    """
    綜合分析：MACD + 布林通道壓縮與突破 + 均線線型
    回傳: (is_buy, is_sell, summary_text, details_dict)
    """
    details = {
        "close": None,
        "bb_upper": None,
        "bb_mid": None,
        "bb_lower": None,
        "bb_bandwidth": None,
        "is_bb_compressed": False,
        "is_bb_breakout": False,
        "macd_hist": None,
        "macd_turned_positive": False,
        "macd_bullish": False,
        "sma5": None,
        "sma20": None,
        "sma60": None,
        "trend_pattern": "震盪整理",
        "signal_type": "中性",
        "beauty_score": None,
        "beauty_status": "INSUFFICIENT_DATA",
        "beauty_data_quality": "FAILED",
        "beauty_trading_days": 0,
        "beauty_components": {},
        "beauty_reasons": []
    }

    if df.empty or len(df) < 20:
        return False, False, "K線數據不足", details

    try:
        bbu_col = [c for c in df.columns if c.startswith('BBU')][0]
        bbm_col = [c for c in df.columns if c.startswith('BBM')][0]
        bbl_col = [c for c in df.columns if c.startswith('BBL')][0]
        macd_hist_col = [c for c in df.columns if c.startswith('MACDh')][0]
        sma5_col = [c for c in df.columns if c.startswith('SMA_5')][0]
        sma20_col = [c for c in df.columns if c.startswith('SMA_20')][0]
        sma60_col = [c for c in df.columns if c.startswith('SMA_60')][0] if any(c.startswith('SMA_60') for c in df.columns) else None

        c_now = float(df['close'].iloc[-1])
        bbu_now = float(df[bbu_col].iloc[-1])
        bbm_now = float(df[bbm_col].iloc[-1])
        bbl_now = float(df[bbl_col].iloc[-1])
        hist_now = float(df[macd_hist_col].iloc[-1])
        hist_prev = float(df[macd_hist_col].iloc[-2]) if len(df) >= 2 else hist_now
        sma5_now = float(df[sma5_col].iloc[-1])
        sma20_now = float(df[sma20_col].iloc[-1])
        sma60_now = float(df[sma60_col].iloc[-1]) if sma60_col else None

        bandwidth = round(((bbu_now - bbl_now) / bbm_now) * 100, 2) if bbm_now > 0 else 0

        details["close"] = round(c_now, 2)
        details["bb_upper"] = round(bbu_now, 2)
        details["bb_mid"] = round(bbm_now, 2)
        details["bb_lower"] = round(bbl_now, 2)
        details["bb_bandwidth"] = bandwidth
        details["macd_hist"] = round(hist_now, 2)
        details["sma5"] = round(sma5_now, 2)
        details["sma20"] = round(sma20_now, 2)
        if sma60_now: details["sma60"] = round(sma60_now, 2)

        # 1. 布林判斷：帶寬壓縮 (< 12%) 與突破上軌
        is_compressed = bandwidth <= 12.0
        is_breakout = c_now >= (bbu_now * 0.985)
        details["is_bb_compressed"] = is_compressed
        details["is_bb_breakout"] = is_breakout

        # 2. MACD 判斷：負翻正 (黃金交叉) 或 多頭紅柱擴大
        is_macd_turn_pos = (hist_prev <= 0 and hist_now > 0)
        is_macd_bull = (hist_now > 0)
        details["macd_turned_positive"] = is_macd_turn_pos
        details["macd_bullish"] = is_macd_bull

        # 3. 線型結構判斷
        if sma60_now and (sma5_now > sma20_now > sma60_now) and (c_now > sma5_now):
            trend_pattern = "🔥 極強多頭排列 (K > 5MA > 20MA > 60MA)"
        elif (sma5_now > sma20_now) and (c_now >= sma20_now):
            trend_pattern = "📈 短多格局 (站穩月線，5MA大於20MA)"
        elif c_now < sma20_now:
            trend_pattern = "⚠️ 弱勢破線 (收盤跌破20日線)"
        else:
            trend_pattern = "⚪ 區間震盪整理"
        details["trend_pattern"] = trend_pattern

        # 4. 買入訊號判定 (布林壓縮/突破 + MACD共振 + 站穩月線)
        buy_reasons = []
        if is_macd_turn_pos:
            buy_reasons.append("MACD柱狀圖翻正")
        elif is_macd_bull and hist_now > hist_prev:
            buy_reasons.append("MACD紅柱擴張")

        if is_breakout:
            buy_reasons.append(f"強勢挑戰/穿透布林上軌({details['bb_upper']})")
        if is_compressed:
            buy_reasons.append(f"布林帶寬高度壓縮({bandwidth}%)蓄勢中")

        if c_now >= sma20_now:
            buy_reasons.append(f"站穩月線({details['sma20']})")

        is_buy = (is_macd_turn_pos or (is_macd_bull and is_breakout)) and (c_now >= sma20_now)

        # 5. 賣出 / 出場警訊判定
        sell_reasons = []
        is_momentum_dead = (hist_prev >= 0 and hist_now < 0)
        is_trend_broken = (c_now < sma20_now)
        if is_momentum_dead: sell_reasons.append("MACD柱狀圖轉負(死叉)")
        if is_trend_broken: sell_reasons.append(f"跌破月線支撐({details['sma20']})")
        is_sell = is_momentum_dead or is_trend_broken

        if is_buy:
            details["signal_type"] = "✨ 強烈買進"
            summary_text = "✨ 買進觸發：" + "、".join(buy_reasons)
        elif is_sell:
            details["signal_type"] = "🛑 風險警告"
            summary_text = "🛑 賣出警戒：" + "、".join(sell_reasons)
        else:
            details["signal_type"] = "☕ 持股觀望"
            summary_text = f"持股觀察中（{trend_pattern}）"

        return is_buy, is_sell, summary_text, details

    except Exception as e:
        return False, False, f"指標分析異常: {e}", details

def analyze_stock_indicators(stock_id, period="1y", dl=None):
    """
    一站式分析個股技術指標（免 API / 純爬蟲容錯）
    """
    df_price = fetch_price_history(stock_id, period=period)
    if df_price.empty or len(df_price) < 20:
        return False, False, "無法取得足夠K線歷史資料", {
            "close": None, "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "bb_bandwidth": None, "sma5": None, "sma20": None, "sma60": None,
            "trend_pattern": "數據不足", "signal_type": "中性"
        }
    df_ind = get_technical_indicators(df_price)
    is_buy, is_sell, summary_text, details = analyze_technical_signals(df_ind)
    details.update(calculate_beauty_score(df_price))
    return is_buy, is_sell, summary_text, details

# 相容舊接口
def check_buy_signal(df):
    is_buy, is_sell, summary, _ = analyze_technical_signals(df)
    return is_buy, summary

def check_sell_signal(df):
    is_buy, is_sell, summary, _ = analyze_technical_signals(df)
    return is_sell, summary
