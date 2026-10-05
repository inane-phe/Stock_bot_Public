# 檔案名稱：tool_sector_broad_test.py (全產業板塊跨市場交叉盲測)
import pandas as pd
import pandas_ta as ta
import datetime
import time
from FinMind.data import DataLoader

FINMIND_TOKEN = "<your FinMind API Token>"

# 🎯 華爾街八大行業組合矩陣 (嚴格測試普適性)
SECTOR_UNIVERSE = {
    "2330": {"name": "台積電", "sector": "半導體核心"},
    "2454": {"name": "聯發科", "sector": "IC設計高價"},
    "2382": {"name": "廣達",   "sector": "AI伺服器代工"},
    "4169": {"name": "旭富",   "sector": "生技醫療族群"},
    "2603": {"name": "長榮",   "sector": "航運景氣循環"},
    "2002": {"name": "中鋼",   "sector": "傳統鋼鐵週期"},
    "1301": {"name": "台塑",   "sector": "塑化龍頭牛皮"},
    "2881": {"name": "富邦金", "sector": "大型金融防守"}
}

START_DATE = "2024-06-01"  
END_DATE = "2026-07-01"    

def evaluate_strategy_on_ticker(dl, stock_id):
    """回測核心 (RSI(14) ✕ MACD(12) 鎖利流)"""
    try:
        # 降頻保護，避免 Rate Limit
        time.sleep(0.5)
        
        df = dl.taiwan_stock_daily(stock_id=stock_id, start_date=START_DATE, end_date=END_DATE)
        if df.empty or len(df) < 50: return 0, 0, 0
        
        df.rename(columns={'max': 'high', 'min': 'low', 'Trading_Volume': 'volume'}, inplace=True)
        df = df.sort_values('date').reset_index(drop=True)
        
        # 指標計算
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df = df.dropna().reset_index(drop=True)
        
        rsi_col = [c for c in df.columns if c.startswith('RSI_14')][0]
        macd_hist = [c for c in df.columns if c.startswith('MACDh_12')][0]
        
        in_position = False
        entry_price = 0
        winning_trades = 0
        total_trades = 0
        total_return = 0.0
        
        for i in range(1, len(df)):
            today_close = df['close'].iloc[i]
            
            # 進場：RSI > 50 且 MACD 柱狀圖翻正
            if not in_position:
                if df[rsi_col].iloc[i] > 50 and df[macd_hist].iloc[i] > 0 and df[macd_hist].iloc[i-1] <= 0:
                    in_position = True
                    entry_price = today_close
            # 出場：MACD 柱狀圖翻紅變綠(動能轉折) 或是 跌破中軌(此處以MACD柱狀圖死叉為出場做測試)
            elif in_position:
                if df[macd_hist].iloc[i] < 0 and df[macd_hist].iloc[i-1] >= 0:
                    in_position = False
                    total_trades += 1
                    profit_pct = (today_close - entry_price) / entry_price - 0.004425
                    total_return += profit_pct
                    if profit_pct > 0: winning_trades += 1
                    
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        return total_trades, round(win_rate, 2), round(total_return * 100, 2)
    except Exception as e:
        return 0, 0, 0

def run_broad_validation():
    print("🚀 啟動【全產業板塊盲測管線】... 正在調閱各行各業歷史數據...")
    dl = DataLoader()
    dl.login_by_token(api_token=FINMIND_TOKEN)
    
    print("\n📊 【2024-2026 全台股八大板塊跨市場大盲測】")
    print("=" * 90)
    print(f"{'代號':<5} | {'股票名稱':<8} | {'產業類別':<14} | {'交易次數':<8} | {'勝率(%)':<10} | {'總報酬率(%)':<15}")
    print("=" * 90)
    
    total_valid_return = 0.0
    strategy_win_shares = 0
    
    for stock_id, info in SECTOR_UNIVERSE.items():
        trades, win, ret = evaluate_strategy_on_ticker(dl, stock_id)
        print(f"{stock_id:<5} | {info['name']:<6} | {info['sector']:<12} | {trades:<8} | {win:<10}% | {ret:<15}%")
        
        total_valid_return += ret
        if ret > 0:
            strategy_win_shares += 1
            
    avg_return = round(total_valid_return / len(SECTOR_UNIVERSE), 2)
    win_share_ratio = round((strategy_win_shares / len(SECTOR_UNIVERSE)) * 100, 1)
    
    print("=" * 90)
    print(f"📈 策略產業適應率：{win_share_ratio}% 的板塊能成功實現獲利。")
    print(f"🏆 全產業跨市場平均報酬率期望值：{avg_return} %")
    print("=" * 90)

if __name__ == "__main__":
    run_broad_validation()
