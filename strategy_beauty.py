# -*- coding: utf-8 -*-
"""
strategy_beauty.py
台股顏值價格結構評分模組。

分數範圍 0~100，權重依 plan_顏值.md：
趨勢 25 + 碎步上漲 20 + 52週高點 20 + 回撤 15 + 動能 15 + 波動 5。
"""

import math

import pandas as pd


YEAR_WINDOW = 240


def _round(value, digits=1):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _clean_price_frame(df):
    work = df.copy()
    work.columns = [str(col).lower().strip() for col in work.columns]

    renamed = {}
    for col in work.columns:
        if col in ["max", "high"]:
            renamed[col] = "high"
        elif col in ["min", "low"]:
            renamed[col] = "low"
        elif col in ["trading_volume", "volume"]:
            renamed[col] = "volume"
    work = work.rename(columns=renamed)

    required = ["date", "high", "low", "close"]
    missing = [col for col in required if col not in work.columns]
    if missing:
        raise ValueError("missing columns: " + ", ".join(missing))

    for col in ["high", "low", "close"]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date", "high", "low", "close"])
    work = work[work["high"] > 0]
    work = work[work["low"] > 0]
    work = work[work["close"] > 0]
    work = work.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return work


def _period_return(close, window):
    if len(close) <= 1:
        return 0.0
    if len(close) > window:
        return float(close.iloc[-1] / close.iloc[-window - 1] - 1)
    return float(close.iloc[-1] / close.iloc[0] - 1)


def _momentum_points(value, lower=-0.30, upper=0.50):
    if value is None:
        return 0.0
    ratio = (float(value) - lower) / (upper - lower)
    return max(0.0, min(1.0, ratio))


def _block_structure(high, low, block_size=10):
    """以不重疊的 10 日區塊近似 Higher High / Higher Low，避免未來資料污染。"""
    if len(high) < block_size * 3:
        return 0.0, 0.0

    sample = min(len(high), 120)
    block_ids = [idx // block_size for idx in range(sample)]
    block_high = high.iloc[-sample:].groupby(block_ids).max()
    block_low = low.iloc[-sample:].groupby(block_ids).min()

    high_pairs = list(zip(block_high.iloc[:-1], block_high.iloc[1:]))
    low_pairs = list(zip(block_low.iloc[:-1], block_low.iloc[1:]))
    higher_high = sum(1 for prev, curr in high_pairs if curr > prev)
    higher_low = sum(1 for prev, curr in low_pairs if curr > prev)

    hh_ratio = higher_high / len(high_pairs) if high_pairs else 0.0
    hl_ratio = higher_low / len(low_pairs) if low_pairs else 0.0
    return hh_ratio, hl_ratio


def calculate_beauty_score(df):
    """
    計算顏值分數與元件分數。

    回傳欄位設計成可直接放進 record["tech"]，UI 與離線報告共用同一份資料。
    """
    result = {
        "beauty_score": None,
        "beauty_status": "INSUFFICIENT_DATA",
        "beauty_data_quality": "FAILED",
        "beauty_trading_days": 0,
        "beauty_components": {},
        "beauty_reasons": [],
        "breakout_52w_high": False,
        "near_52w_high": False,
    }

    try:
        work = _clean_price_frame(df)
    except Exception as exc:
        result["beauty_reasons"] = [f"資料清洗失敗: {exc}"]
        return result

    trading_days = len(work)
    result["beauty_trading_days"] = trading_days
    if trading_days < 120:
        result["beauty_reasons"] = ["有效交易日少於 120 日，不足以形成穩定評分"]
        return result

    close = work["close"]
    high = work["high"]
    low = work["low"]
    current = float(close.iloc[-1])

    sma20 = close.rolling(20).mean()
    sma60 = close.rolling(60).mean()
    sma120 = close.rolling(120).mean()

    ret_20d = _period_return(close, 20)
    ret_60d = _period_return(close, 60)
    ret_120d = _period_return(close, 120)
    ret_240d = _period_return(close, YEAR_WINDOW)

    reasons = []

    # Trend: 25 points
    trend_points = 0.0
    if current > float(sma20.iloc[-1]):
        trend_points += 6.25
        reasons.append("收盤站上 20 日線")
    if len(sma60.dropna()) and float(sma20.iloc[-1]) > float(sma60.iloc[-1]):
        trend_points += 6.25
        reasons.append("20 日線高於 60 日線")
    if len(sma120.dropna()) and float(sma60.iloc[-1]) > float(sma120.iloc[-1]):
        trend_points += 6.25
        reasons.append("60 日線高於 120 日線")
    if ret_240d > 0:
        trend_points += 6.25
        reasons.append("一年期報酬為正")

    # Stair-step: 20 points
    hh_ratio, hl_ratio = _block_structure(high, low)
    positive_days = int((close.pct_change().tail(20) > 0).sum())
    recovery_ratio = positive_days / 20
    stair_points = hh_ratio * 8 + hl_ratio * 8 + recovery_ratio * 4
    if hh_ratio >= 0.6:
        reasons.append("近期區塊高點多數墊高")
    if hl_ratio >= 0.6:
        reasons.append("近期區塊低點多數墊高")

    # 52W high: 20 points
    previous_240d_high = float(close.iloc[:-1].tail(YEAR_WINDOW).max())
    distance_to_high = current / previous_240d_high - 1 if previous_240d_high > 0 else -1.0
    breakout = current > previous_240d_high
    near_high = distance_to_high >= -0.05
    result["breakout_52w_high"] = bool(breakout)
    result["near_52w_high"] = bool(near_high)
    if breakout:
        high_points = 20.0
        reasons.append("收盤突破前 240 日高點")
    elif distance_to_high >= -0.03:
        high_points = 18.0
        reasons.append("收盤貼近 52 週高點")
    elif distance_to_high >= -0.08:
        high_points = 16.0
        reasons.append("距離 52 週高點 8% 內")
    elif distance_to_high >= -0.15:
        high_points = 12.0
        reasons.append("距離 52 週高點 15% 內")
    elif distance_to_high >= -0.25:
        high_points = 7.0
        reasons.append("距離 52 週高點 25% 內")
    else:
        high_points = 0.0
        reasons.append("距離 52 週高點過遠")

    # Drawdown: 15 points
    lookback_close = close.tail(YEAR_WINDOW)
    running_high = lookback_close.cummax()
    drawdown_series = lookback_close / running_high - 1
    max_drawdown = float(drawdown_series.min())
    if max_drawdown >= -0.05:
        drawdown_points = 15.0
        reasons.append("一年期最大回撤小於 5%")
    elif max_drawdown >= -0.10:
        drawdown_points = 13.0
        reasons.append("一年期最大回撤小於 10%")
    elif max_drawdown >= -0.15:
        drawdown_points = 11.0
        reasons.append("一年期最大回撤小於 15%")
    elif max_drawdown >= -0.20:
        drawdown_points = 8.0
        reasons.append("一年期最大回撤小於 20%")
    elif max_drawdown >= -0.30:
        drawdown_points = 4.0
        reasons.append("一年期最大回撤小於 30%")
    else:
        drawdown_points = 0.0
        reasons.append("一年期最大回撤過深")

    # Momentum: 15 points
    momentum_points = (
        _momentum_points(ret_20d) * 3.0
        + _momentum_points(ret_60d) * 4.5
        + _momentum_points(ret_120d) * 4.5
        + _momentum_points(ret_240d) * 3.0
    )
    if ret_60d > 0 and ret_120d > 0:
        reasons.append("中期與中長期動能同向向上")

    # Volatility: 5 points
    daily_vol = float(close.pct_change().tail(20).std(skipna=True))
    annual_vol = daily_vol * math.sqrt(252) if daily_vol == daily_vol else 1.0
    if annual_vol <= 0.15:
        volatility_points = 5.0
        reasons.append("20 日年化波動低於 15%")
    elif annual_vol <= 0.25:
        volatility_points = 4.0
        reasons.append("20 日年化波動低於 25%")
    elif annual_vol <= 0.35:
        volatility_points = 3.0
        reasons.append("20 日年化波動低於 35%")
    elif annual_vol <= 0.50:
        volatility_points = 2.0
        reasons.append("20 日年化波動偏高")
    elif annual_vol <= 0.70:
        volatility_points = 1.0
        reasons.append("20 日年化波動明顯偏高")
    else:
        volatility_points = 0.0
        reasons.append("20 日年化波動過高")

    score = trend_points + stair_points + high_points + drawdown_points + momentum_points + volatility_points
    score = max(0.0, min(100.0, score))

    if trading_days < YEAR_WINDOW:
        status = "INSUFFICIENT_DATA"
        data_quality = "PARTIAL"
        reasons.append("歷史不足 240 日，分數僅供參考")
    elif score >= 80:
        status = "HIGH"
        data_quality = "PASS"
    elif score >= 65:
        status = "WATCHLIST"
        data_quality = "PASS"
    else:
        status = "LOW"
        data_quality = "PASS"

    result.update(
        {
            "beauty_score": _round(score),
            "beauty_status": status,
            "beauty_data_quality": data_quality,
            "beauty_components": {
                "trend": _round(trend_points),
                "stair_step": _round(stair_points),
                "high_52w": _round(high_points),
                "drawdown": _round(drawdown_points),
                "momentum": _round(momentum_points),
                "volatility": _round(volatility_points),
            },
            "beauty_metrics": {
                "return_20d": _round(ret_20d * 100, 2),
                "return_60d": _round(ret_60d * 100, 2),
                "return_120d": _round(ret_120d * 100, 2),
                "return_240d": _round(ret_240d * 100, 2),
                "max_drawdown": _round(max_drawdown * 100, 2),
                "annual_volatility": _round(annual_vol * 100, 2),
                "distance_to_52w_high": _round(distance_to_high * 100, 2),
            },
            "beauty_reasons": reasons,
        }
    )
    return result
