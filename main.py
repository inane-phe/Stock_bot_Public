# -*- coding: utf-8 -*-
"""
main.py
台股量化多因子選股戰情室 - 離線 HTML 報告產出工具
全網路爬蟲與開放數據架構 (100% 免 FinMind API / 零調用上限限制)
"""
import os
import sys
import json
import datetime
import time
import webbrowser
import requests

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from strategy_fundamentals import check_fundamental_filters
from strategy_indicators import analyze_stock_indicators
from strategy_chips import ChipsEngine
from html_generator import generate_html_report

WATCHLIST_FILE = os.path.join(CURRENT_DIR, "watchlist.json")
REPORT_HTML_FILE = os.path.join(CURRENT_DIR, "report.html")

# 預設重點關注核心母體
DEFAULT_CORE_POOL = [
    "2330", "2317", "2454", "2308", "2382", "3231", "2376", "6669", # 權值AI
    "1519", "1513", "1504", "1514",                                 # 重電綠能
    "2603", "2609", "2615",                                         # 航運
    "2881", "2882", "2886", "2891",                                 # 金融
    "3034", "3035", "3037", "3443", "3661", "8028"                  # IC設計/半導體材料
]

def load_target_stocks():
    """載入掃描股票清單"""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return [(sid, name) for sid, name in data.items()]
                elif isinstance(data, list):
                    return [(sid, "") for sid in data[:30]]
        except Exception as e:
            print(f"⚠️ 讀取 {WATCHLIST_FILE} 失敗: {e}")

    return [(sid, "") for sid in DEFAULT_CORE_POOL]

def run_quant_scanner():
    print("=" * 60)
    print("🚀 啟動【台股量化多因子選股戰情室】純爬蟲掃描流程")
    print("   特性：100% 免 FinMind API，零連線次數限制，極速穩定")
    print("   漏斗架構：基本面(YoY+EPS) ➔ 布林通道+MACD+均線 ➔ 法人大戶+默默吸籌")
    print("=" * 60)

    chips_engine = ChipsEngine()

    # 取得股票基本資料 (TWSE OpenAPI)
    print("📥 正在同步台灣證券交易所股票資訊與產業分類...")
    stock_info_map = {}
    try:
        r_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", timeout=5)
        if r_twse.status_code == 200:
            for item in r_twse.json():
                sid = str(item.get("Code", "")).strip()
                sname = str(item.get("Name", "")).strip()
                if sid:
                    stock_info_map[sid] = {"name": sname, "sector": "上市股票"}
    except Exception as e:
        print(f"⚠️ 股票列表取得警告: {e}")

    targets = load_target_stocks()
    print(f"📊 本次鎖定掃描母體：共 {len(targets)} 檔精選標的\n")

    results = []

    for idx, item in enumerate(targets, 1):
        if isinstance(item, tuple):
            stock_id, fallback_name = item
        else:
            stock_id, fallback_name = str(item), ""

        meta = stock_info_map.get(stock_id, {})
        stock_name = meta.get("name") or fallback_name or f"個股 {stock_id}"
        sector = meta.get("sector", "台股標的")

        print(f"[{idx:02d}/{len(targets):02d}] 正在對 【{stock_id} {stock_name}】 進行爬蟲漏斗檢查...", end="", flush=True)

        record = {
            "stock_id": stock_id,
            "stock_name": stock_name,
            "sector": sector,
            "fund_ok": False,
            "fundamental": {},
            "tech": {},
            "chips": {},
            "is_strong_buy": False,
            "overall_note": ""
        }

        try:
            # 1. 基本面漏斗 (純爬蟲)
            fund_ok, fund_reason, fund_info = check_fundamental_filters(stock_id)
            record["fund_ok"] = fund_ok
            record["fundamental"] = fund_info

            # 2. 技術面漏斗 (yfinance)
            is_buy, is_sell, tech_summary, tech_details = analyze_stock_indicators(stock_id)
            record["tech"] = tech_details
            record["tech"]["is_buy"] = is_buy
            record["tech"]["is_sell"] = is_sell
            record["tech"]["summary"] = tech_summary

            # 3. 籌碼面漏斗 (純爬蟲)
            chips_data = chips_engine.analyze_chips(stock_id)
            record["chips"] = chips_data

            # 4. 綜合多頭共振買點判定
            tech_is_buy = record["tech"].get("is_buy", False)
            chip_favorable = (chips_data.get("is_accumulating") or
                              chips_data.get("trust_consecutive_buy") or
                              (chips_data.get("total_net_5d", 0) > 0))

            if fund_ok and tech_is_buy and chip_favorable:
                record["is_strong_buy"] = True
                print(" 👉 ✨【強烈買進共振】")
            elif fund_ok:
                print(" 👉 🟢 基本面合格")
            else:
                print(f" 👉 ⚪ 基本面淘汰")

        except Exception as e:
            print(f" 👉 ❌ 分析異常: {e}")

        results.append(record)
        time.sleep(0.3)

    # 排序：強烈買進優先，其次基本面合格，最後依營收成長排序
    results.sort(
        key=lambda r: (
            1 if r.get("is_strong_buy") else 0,
            1 if r.get("fund_ok") else 0,
            r.get("fundamental", {}).get("revenue_yoy") or -999
        ),
        reverse=True
    )

    # 產出視覺化 HTML 報告
    print("\n" + "=" * 60)
    print("🎨 正在渲染 HTML 視覺化戰情室報告...")
    generate_html_report(results, output_file=REPORT_HTML_FILE, scan_scope=f"精選池 ({len(results)} 檔)")

    # 自動開啟預設瀏覽器檢視
    abs_report_path = os.path.abspath(REPORT_HTML_FILE)
    print(f"🌐 正在自動開啟瀏覽器展示報告: file:///{abs_report_path.replace(os.sep, '/')}")
    try:
        webbrowser.open(abs_report_path)
    except Exception:
        pass

    print("🎉 量化分析全流程執行完畢！")

if __name__ == "__main__":
    run_quant_scanner()