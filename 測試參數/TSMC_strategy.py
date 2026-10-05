# 檔案名稱：tool_out_of_sample_test.py (樣本外混沌數據壓力盲測)
import pandas as pd
import pandas_ta as ta
import datetime
from FinMind.data import DataLoader

# --- 設定區 ---
FINMIND_TOKEN = "<your FinMind API Token>"
TEST_STOCK = "2330"        

# 🚨 核心切換：完全使用【樣本外(Out-of-Sample)】混沌時間軸
START_DATE = "2024-06-01"  
END_DATE = "2026-07-01"    

def backtest_specific_strategy(df_raw, osc_name, trend_name, osc_p, trend_param):
    """模擬特定因子組合的樣本外績效"""
    df = df_raw.copy()
    
    # 計算指標
    if osc_name == "KD":
        df.ta.stoch(k=osc_p, d=3, append=True)
    else:
        df.ta.rsi(length=osc_p, append=True)
        
    if trend_name == "MACD":
        df.ta.macd(fast=trend_param, slow=26, signal=9, append=True)
    else:
        df.ta.bbands(length=trend_param, std=2.0, append=True)
        
    df = df.dropna().reset_index(drop=True)
    
    # 欄位模糊定位
    osc_col = [c for c in df.columns if c.startswith('STOCHk_')][0] if osc_name == "KD" else [c for c in df.columns if c.startswith('RSI_')][0]
    osc_sig = [c for c in df.columns if c.startswith('STOCHd_')][0] if osc_name == "KD" else osc_col
    
    if trend_name == "BBANDS":
        trd_in = [c for c in df.columns if c.startswith('BBU_')][0]
        trd_out = [c for c in df.columns if c.startswith('BBM_')][0]
    else:
        trd_in = [c for c in df.columns if c.startswith('MACDh_')][0]
        trd_out = trd_in
        
    in_position = False
    entry_price = 0
    winning_trades = 0
    total_trades = 0
    total_return = 0.0
    
    for i in range(1, len(df)):
        today_close = df['close'].iloc[i]
        
        if not in_position:
            cond_osc = (df[osc_col].iloc[i] > df[osc_sig].iloc[i]) if osc_name == "KD" else (df[osc_col].iloc[i] > 50)
            cond_trend = (today_close > df[trd_in].iloc[i]) if trend_name == "BBANDS" else (df[trd_in].iloc[i] > 0)
            if cond_osc and cond_trend:
                in_position = True
                entry_price = today_close
        elif in_position:
            cond_exit = (today_close < df[trd_out].iloc[i]) if trend_name == "BBANDS" else (df[trd_out].iloc[i] < 0)
            if cond_exit:
                in_position = False
                total_trades += 1
                profit_pct = (today_close - entry_price) / entry_price - 0.004425
                total_return += profit_pct
                if profit_pct > 0: winning_trades += 1
                
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    return total_trades, round(win_rate, 2), round(total_return * 100, 2)

def run_out_of_sample_blind_test():
    print(f"🐋 啟動華爾街樣本外盲測機制... 正在加載 {TEST_STOCK} 2024-2026 混沌數據...")
    dl = DataLoader()
    dl.login_by_token(api_token=FINMIND_TOKEN)
    df_raw = dl.taiwan_stock_daily(stock_id=TEST_STOCK, start_date=START_DATE, end_date=END_DATE)
    if df_raw.empty: return
    
    df_raw.rename(columns={'max': 'high', 'min': 'low', 'Trading_Volume': 'volume'}, inplace=True)
    df_raw = df_raw.sort_values('date').reset_index(drop=True)
    
    # 驗證四大核心參賽者
    strategies = [
        {"osc": "KD", "trd": "MACD", "osc_p": 14, "trd_p": 19, "name": "🏆 暴風動能流組合 A"},
        {"osc": "KD", "trd": "MACD", "osc_p": 35, "trd_p": 19, "name": "🥈 巨鯨方向流組合"},
        {"osc": "RSI", "trd": "MACD", "osc_p": 14, "trd_p": 12, "name": "🥉 穩健狙擊手組合 B"},
        {"osc": "KD", "trd": "BBANDS", "osc_p": 35, "trd_p": 20, "name": "📊 舊版常態布林組合"},
    ]
    
    print("\n⚡ 【2024-2026 樣本外混沌市場壓力測試白皮書】 結算報告：")
    print("-" * 85)
    print(f"{'策略組合名稱':<25} | {'交易次數':<8} | {'勝率(%)':<10} | {'樣本外總報酬率(%)':<15}")
    print("-" * 85)
    
    for strat in strategies:
        trades, win, ret = backtest_specific_strategy(df_raw, strat['osc'], strat['trd'], strat['osc_p'], strat['trd_p'])
        print(f"{strat['name']:<22} | {trades:<8} | {win:<10}% | {ret:<15}%")
    print("-" * 85)

if __name__ == "__main__":
    run_out_of_sample_blind_test()


"""
    ⚡ 【2024-2026 樣本外混沌市場壓力測試白皮書】 結算報告：
-------------------------------------------------------------------------------------
策略組合名稱                    | 交易次數     | 勝率(%)      | 樣本外總報酬率(%)     
-------------------------------------------------------------------------------------
🏆 暴風動能流組合 A            | 18       | 33.33     % | 36.02          %
🥈 巨鯨方向流組合              | 18       | 33.33     % | 36.02          %
🥉 穩健狙擊手組合 B            | 20       | 40.0      % | 37.6           %
📊 舊版常態布林組合             | 10       | 50.0      % | 35.05          %
-------------------------------------------------------------------------------------"""
