# -*- coding: utf-8 -*-
"""
app.py
台股量化多因子選股戰情室 - 後端服務
全網路爬蟲與開放數據架構 (100% 免 FinMind API / 零調用上限限制)
數據源：證交所 TWSE OpenAPI + 櫃買中心 TPEx OpenAPI + Yahoo 奇摩股市 + yfinance + Google News
"""
import os
import sys
import json
import time
import datetime
import threading
import requests
import bs4
import re
from flask import Flask, make_response, render_template, request, jsonify, send_from_directory

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURRENT_DIR)

from strategy_fundamentals import check_fundamental_filters
from strategy_indicators import analyze_stock_indicators
from strategy_chips import ChipsEngine
from strategy_news import fetch_stock_news
from history_tracker import archive_scan_results, load_history_index, verify_history, HISTORY_DIR

CACHE_FILE = os.path.join(CURRENT_DIR, "scanned_cache.json")
PROFILES_FILE = os.path.join(CURRENT_DIR, "company_profiles.json")
COMPANY_PROFILES = {}
PROFILE_LOCK = threading.Lock()

app = Flask(__name__, template_folder=os.path.join(CURRENT_DIR, "templates"))
app.config["TEMPLATES_AUTO_RELOAD"] = True

CHIPS_ENGINE = ChipsEngine()

STOCK_INFO_MAP = {}
NAME_TO_STOCK_ID = {}
SCANNED_RESULTS = []
SCAN_LOCK = threading.Lock()

def load_company_profiles():
    """載入個股主要營業項目本地快取"""
    global COMPANY_PROFILES
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                COMPANY_PROFILES = json.load(f)
                print(f"✅ [Company Profiles] 成功載入 {len(COMPANY_PROFILES)} 筆主要營業項目資料庫")
        except Exception as e:
            print(f"⚠️ 讀取 company_profiles.json 失敗: {e}")
            COMPANY_PROFILES = {}

def save_company_profiles():
    """持久化儲存主要營業項目快取"""
    with PROFILE_LOCK:
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump(COMPANY_PROFILES, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 儲存 company_profiles.json 失敗: {e}")

def get_stock_main_business(stock_id):
    """
    獲取個股主要經營業務 / 主要營業項目 (具備本地持久化與記憶體快取)
    支援上市與上櫃股票 (Yahoo Profile 網頁爬取，免付費 Token)
    """
    if not stock_id:
        return ""

    with PROFILE_LOCK:
        if stock_id in COMPANY_PROFILES and COMPANY_PROFILES[stock_id]:
            return COMPANY_PROFILES[stock_id]

    meta = STOCK_INFO_MAP.get(stock_id, {})
    if meta.get("main_business"):
        with PROFILE_LOCK:
            COMPANY_PROFILES[stock_id] = meta["main_business"]
        return meta["main_business"]

    biz = ""
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}/profile"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            soup = bs4.BeautifulSoup(r.text, 'html.parser')
            span = soup.find('span', string=lambda t: t and '主要經營業務' in t)
            if span:
                parent_container = span.find_parent('div')
                if parent_container:
                    divs = parent_container.find_all('div')
                    if divs:
                        biz = divs[-1].get_text(separator=' ', strip=True)
            if not biz:
                m = re.search(r'主要經營業務</span></span><div[^>]*>(.*?)</div>', r.text)
                if m:
                    biz = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
    except Exception:
        pass

    if not biz:
        biz = meta.get("sector", "台股標的")

    # 清理多餘換行與連續空白
    biz = re.sub(r'\s+', ' ', biz).strip()

    with PROFILE_LOCK:
        COMPANY_PROFILES[stock_id] = biz
        if stock_id in STOCK_INFO_MAP:
            STOCK_INFO_MAP[stock_id]["main_business"] = biz

    save_company_profiles()
    return biz

load_company_profiles()


WATCHLIST_FILE = os.path.join(CURRENT_DIR, "watchlist.json")
WATCHLIST_STOCKS = []

SCAN_PROGRESS = {
    "is_scanning": False,
    "total": 0,
    "current": 0,
    "current_stock": "",
    "strong_buy_count": 0,
    "fund_ok_count": 0,
    "stop_requested": False,
    "start_time": 0
}

CUSTOM_CATEGORIES_FILE = os.path.join(CURRENT_DIR, "custom_categories.json")
CUSTOM_CATEGORIES = {}

def load_watchlist():
    """載入母體 watchlist.json (1,215 檔)"""
    global WATCHLIST_STOCKS
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                stocks = []
                if isinstance(data, list):
                    for x in data:
                        sid = str(x).strip()
                        if sid and sid not in stocks and (len(sid) == 4 or sid.isdigit()):
                            stocks.append(sid)
                elif isinstance(data, dict):
                    for k in data.keys():
                        sid = str(k).strip()
                        if sid and sid not in stocks:
                            stocks.append(sid)
                WATCHLIST_STOCKS = stocks
                print(f"✅ [Watchlist] 成功載入 {len(WATCHLIST_STOCKS)} 檔定時掃描母體標的")
        except Exception as e:
            print(f"⚠️ 讀取 watchlist.json 失敗: {e}")

# 概念股分類清單 (內建集團、半導體、熱門題材等多元族群)
CONCEPT_CATEGORIES = {
    # --- 核心精選 ---
    "core": {
        "title": "⚡ 快速推薦 (核心30檔)",
        "group": "核心精選",
        "stocks": [
            "2330", "2317", "2454", "2308", "2382", "3231", "2376", "6669",
            "1519", "1513", "1504", "1514", "2603", "2609", "2615",
            "2881", "2882", "2886", "2891", "3034", "3035", "3037",
            "3443", "3661", "8028", "2356", "3017", "3324", "4961", "3189"
        ]
    },
    # --- 集團概念股 ---
    "group_foxconn": {
        "title": "🏢 鴻海集團",
        "group": "集團概念",
        "stocks": ["2317", "2354", "6414", "2328", "5243", "3149", "8046", "3651"]
    },
    "group_tsmc": {
        "title": "💎 台積電大聯盟",
        "group": "集團概念",
        "stocks": ["2330", "3131", "3583", "3413", "6187", "8028", "1560", "6805"]
    },
    "group_umc": {
        "title": "🏢 聯電集團",
        "group": "集團概念",
        "stocks": ["2303", "3035", "3014", "2388", "3264", "3037", "8150"]
    },
    "group_delta": {
        "title": "⚡ 台達電集團",
        "group": "集團概念",
        "stocks": ["2308", "6285", "3217", "6412"]
    },
    "group_finance": {
        "title": "🏛️ 金控金融集團",
        "group": "集團概念",
        "stocks": ["2881", "2882", "2891", "2886", "2884", "2885", "2892", "2880"]
    },
    "group_evergreen": {
        "title": "🚢 長榮集團",
        "group": "集團概念",
        "stocks": ["2603", "2618", "2607", "2645"]
    },
    "group_formosa": {
        "title": "🏭 台塑集團",
        "group": "集團概念",
        "stocks": ["1301", "1303", "1326", "6505", "2408"]
    },
    "group_via": {
        "title": "🚀 威盛集團",
        "group": "集團概念",
        "stocks": ["2388", "2498", "3508", "6598"]
    },
    # --- 半導體族群 ---
    "semi_cowos": {
        "title": "💎 半導體與CoWoS先進封裝",
        "group": "半導體族群",
        "stocks": ["2330", "2454", "3443", "3661", "3035", "3034", "3131", "3583", "8028", "6187"]
    },
    "semi_ic_design": {
        "title": "🧠 IC設計龍頭族群",
        "group": "半導體族群",
        "stocks": ["2454", "3034", "3661", "3443", "6415", "3035", "4961", "2379", "3227"]
    },
    "semi_foundry": {
        "title": "🏭 晶圓代工與製造",
        "group": "半導體族群",
        "stocks": ["2330", "2303", "5347", "6770"]
    },
    "semi_equip": {
        "title": "⚙️ 半導體設備與材料",
        "group": "半導體族群",
        "stocks": ["3131", "3583", "6187", "8028", "3413", "1773", "4755", "1560"]
    },
    "semi_package": {
        "title": "📦 封裝與測試",
        "group": "半導體族群",
        "stocks": ["3711", "2449", "6239", "3264", "6515"]
    },
    "semi_memory": {
        "title": "💾 記憶體族群",
        "group": "半導體族群",
        "stocks": ["2408", "2344", "2337", "8299", "3006", "3260"]
    },
    # --- 熱門題材族群 ---
    "ai": {
        "title": "🔥 AI伺服器核心鏈",
        "group": "熱門題材",
        "stocks": ["2330", "2317", "2382", "3231", "6669", "2376", "2356", "3017", "3324", "2308"]
    },
    "cooling": {
        "title": "❄️ 散熱與水冷模組",
        "group": "熱門題材",
        "stocks": ["3017", "3324", "3653", "2421", "6230", "8996"]
    },
    "cpo": {
        "title": "⚡ 光通訊與矽光子CPO",
        "group": "熱門題材",
        "stocks": ["3450", "4977", "3163", "4979", "6442", "3363"]
    },
    "robot": {
        "title": "🤖 機器人與自動化概念",
        "group": "熱門題材",
        "stocks": ["2359", "4583", "2049", "8234", "6188", "2365"]
    },
    "power": {
        "title": "⚡ 重電與綠能族群",
        "group": "熱門題材",
        "stocks": ["1519", "1513", "1504", "1514", "6806", "1609", "9958"]
    },
    "shipping": {
        "title": "🚢 貨櫃航運與航空",
        "group": "熱門題材",
        "stocks": ["2603", "2609", "2615", "2618", "2610"]
    },
    "defense": {
        "title": "🛡️ 高股息與大型金融防守",
        "group": "熱門題材",
        "stocks": ["2881", "2882", "2886", "2891", "2880", "2412", "3045"]
    }
}

def load_custom_categories():
    """載入使用者自訂類股清單"""
    global CUSTOM_CATEGORIES
    if os.path.exists(CUSTOM_CATEGORIES_FILE):
        try:
            with open(CUSTOM_CATEGORIES_FILE, "r", encoding="utf-8") as f:
                CUSTOM_CATEGORIES = json.load(f)
                print(f"✅ 成功載入 {len(CUSTOM_CATEGORIES)} 個自訂類股")
        except Exception as e:
            print(f"⚠️ 讀取自訂類股失敗: {e}")
            CUSTOM_CATEGORIES = {}
    else:
        # 提供初始自訂範例方便使用者立即參考與修改
        CUSTOM_CATEGORIES = {
            "custom_sample_1": {
                "id": "custom_sample_1",
                "title": "🏷️ 關鍵自選觀察股",
                "group": "自訂類股",
                "stocks": ["2330", "2454", "2317", "3008", "3017"],
                "is_custom": True
            }
        }
        save_custom_categories()

def save_custom_categories():
    """儲存使用者自訂類股清單"""
    try:
        with open(CUSTOM_CATEGORIES_FILE, "w", encoding="utf-8") as f:
            json.dump(CUSTOM_CATEGORIES, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 儲存自訂類股失敗: {e}")

def get_all_categories():
    """整合內建類股、母體自選池與自訂類股"""
    all_cats = {}
    for k, v in CONCEPT_CATEGORIES.items():
        all_cats[k] = {
            "id": k,
            "title": v.get("title", k),
            "group": v.get("group", "熱門題材"),
            "stocks": v.get("stocks", []),
            "is_custom": False
        }

    # 加入全市場定時母體 (1,215 檔)
    if WATCHLIST_STOCKS:
        all_cats["watchlist_all"] = {
            "id": "watchlist_all",
            "title": f"📋 全自選母體池 ({len(WATCHLIST_STOCKS)}檔)",
            "group": "核心精選",
            "stocks": WATCHLIST_STOCKS,
            "is_custom": False
        }

    # 加入上市櫃總庫 (2,096 檔)
    if STOCK_INFO_MAP:
        all_sids = [sid for sid in STOCK_INFO_MAP.keys() if len(sid) == 4 and sid.isdigit()]
        all_cats["all_market"] = {
            "id": "all_market",
            "title": f"🌐 全台上市櫃總庫 ({len(all_sids)}檔)",
            "group": "核心精選",
            "stocks": all_sids,
            "is_custom": False
        }

    for k, v in CUSTOM_CATEGORIES.items():
        all_cats[k] = {
            "id": k,
            "title": v.get("title", k),
            "group": "自訂類股",
            "stocks": v.get("stocks", []),
            "is_custom": True
        }
    return all_cats


def init_stock_info():
    """
    透過台灣證券交易所 (TWSE) 與櫃買中心 (TPEx) 官方 OpenAPI 加載全台股票代號清單 (免 Token)
    建立 雙向索引 [代號 -> 名稱] 與 [名稱 -> 代號]
    """
    global STOCK_INFO_MAP, NAME_TO_STOCK_ID
    # 1. 證交所 (TWSE) 上市公司 (1,081 檔)
    try:
        r_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", timeout=5)
        if r_twse.status_code == 200:
            for item in r_twse.json():
                sid = str(item.get("Code", "")).strip()
                sname = str(item.get("Name", "")).strip()
                if sid:
                    STOCK_INFO_MAP[sid] = {"name": sname, "sector": "上市股票"}
                    if sname:
                        NAME_TO_STOCK_ID[sname] = sid
        print(f"✅ [TWSE OpenData] 成功加載 {len(STOCK_INFO_MAP)} 檔上市基本資料")
    except Exception as e:
        print(f"⚠️ 加載 TWSE 失敗: {e}")

    # 2. 櫃買中心 (TPEx) 上櫃公司 (1,013 檔)
    try:
        import urllib3
        urllib3.disable_warnings()
        r_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", verify=False, timeout=5)
        if r_tpex.status_code == 200:
            for item in r_tpex.json():
                sid = str(item.get("SecuritiesCompanyCode", "")).strip()
                sname = str(item.get("CompanyName", "")).strip()
                if sid and sid not in STOCK_INFO_MAP:
                    STOCK_INFO_MAP[sid] = {"name": sname, "sector": "上櫃股票"}
                if sname and sname not in NAME_TO_STOCK_ID:
                    NAME_TO_STOCK_ID[sname] = sid
        print(f"✅ [TPEx OpenData] 累計加載 {len(STOCK_INFO_MAP)} 檔上市櫃公司資料庫")
    except Exception as e:
        print(f"⚠️ 加載 TPEx 失敗: {e}")

def resolve_stock_query(query):
    """
    智能識別輸入字串：自動將中文名稱 (如 '大立光'、'聯發科') 或混合字串解析為標準 4 碼台股代號
    """
    query = str(query).strip()
    if not query:
        return ""

    # 1. 若輸入包含 4 位純數字代號 (例如 '3008', '2330.TW', '2330 台積電')
    m = re.search(r'\b(\d{4})\b', query)
    if m:
        return m.group(1)

    # 2. 繁體中文全名精準比對 (如 '大立光' -> '3008')
    if query in NAME_TO_STOCK_ID:
        return NAME_TO_STOCK_ID[query]

    # 3. 本地資料庫模糊比對 (優先選取 4 碼正規股票)
    for sname, sid in NAME_TO_STOCK_ID.items():
        if len(sid) == 4 and (query in sname or sname in query):
            return sid

    # 4. Yahoo 官方即時聯想 API (支援任何最新上市/特殊簡稱公司)
    try:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/AutocompleteService;query={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            results = r.json().get('ResultSet', {}).get('Result', [])
            for item in results:
                sym = item.get('symbol', '').split('.')[0]
                if len(sym) == 4 and sym.isdigit():
                    sname = item.get('name', '')
                    STOCK_INFO_MAP[sym] = {"name": sname, "sector": "台股標的"}
                    NAME_TO_STOCK_ID[sname] = sym
                    return sym
    except Exception:
        pass

    return query

def get_stock_name_and_sector(stock_id):
    """
    動態爬取個股中文簡稱與所屬產業
    """
    meta = STOCK_INFO_MAP.get(stock_id, {})
    name = meta.get("name", "").strip()
    sector = meta.get("sector", "").strip()

    if not name or name == f"個股 {stock_id}":
        try:
            url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                soup = bs4.BeautifulSoup(r.text, 'html.parser')
                t = soup.find('title')
                if t:
                    m = re.match(r'^([^(]+)', t.text.strip())
                    if m:
                        name = m.group(1).strip()
                cat_el = soup.find(lambda el: el.name == 'a' and '/class-quote?category=' in el.get('href', ''))
                if cat_el:
                    sector = cat_el.text.strip()
        except Exception:
            pass

    if not name:
        name = f"台股 {stock_id}"
    if not sector:
        sector = "電子/傳產"

    STOCK_INFO_MAP[stock_id] = {"name": name, "sector": sector}
    return name, sector

def load_cache():
    global SCANNED_RESULTS
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                cleaned = []
                for item in raw:
                    sid = str(item.get("stock_id", "")).strip()
                    # 清洗非數字的錯誤代碼記錄 (例如歷史殘留的 "大立光")
                    if not sid.isdigit() and len(sid) != 4:
                        continue
                    # 若快取已有主要營業項目，登記至 COMPANY_PROFILES；若無則自快取補足
                    if item.get("main_business"):
                        COMPANY_PROFILES[sid] = item["main_business"]
                    elif sid in COMPANY_PROFILES:
                        item["main_business"] = COMPANY_PROFILES[sid]
                    cleaned.append(item)
                SCANNED_RESULTS = cleaned
                print(f"✅ 成功自快取載入 {len(SCANNED_RESULTS)} 檔已掃描資料")
        except Exception as e:
            print(f"⚠️ 讀取快取失敗: {e}")

def save_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(SCANNED_RESULTS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 儲存快取失敗: {e}")

def analyze_single_stock(stock_input):
    """
    全爬蟲式深度掃描單一股票 (支援代碼如 3008 或中文名稱如 大立光)
    """
    stock_input = str(stock_input).strip()
    stock_id = resolve_stock_query(stock_input)
    stock_name, sector = get_stock_name_and_sector(stock_id)
    main_business = get_stock_main_business(stock_id)
    now = datetime.datetime.now()

    record = {
        "stock_id": stock_id,
        "stock_name": stock_name,
        "sector": sector,
        "main_business": main_business,
        "fund_ok": False,
        "fundamental": {},
        "tech": {},
        "chips": {},
        "news": {},
        "is_strong_buy": False,
        "scan_time": now.strftime("%H:%M:%S")
    }

    # 1. 基本面爬蟲 (營收 YoY >= 10% ✕ 單季 EPS > 0)
    try:
        fund_ok, fund_reason, fund_info = check_fundamental_filters(stock_id)
        record["fund_ok"] = fund_ok
        record["fundamental"] = fund_info
    except Exception as e:
        record["fundamental"] = {"revenue_yoy": None, "eps": None, "error": str(e)}

    # 2. 技術面爬蟲 (布林通道壓縮與突破 ✕ MACD翻正 ✕ 均線多頭排列)
    try:
        is_buy, is_sell, tech_summary, tech_details = analyze_stock_indicators(stock_id)
        record["tech"] = tech_details
        record["tech"]["is_buy"] = is_buy
        record["tech"]["is_sell"] = is_sell
        record["tech"]["summary"] = tech_summary
    except Exception as e:
        record["tech"] = {"is_buy": False, "is_sell": False, "summary": f"技術指標異常: {e}"}

    # 3. 籌碼面爬蟲 (三大法人5日買賣超、投信連買、主力吸籌)
    try:
        chips_data = CHIPS_ENGINE.analyze_chips(stock_id)
        record["chips"] = chips_data
    except Exception as e:
        record["chips"] = {"status_summary": f"籌碼查詢異常: {e}"}

    # 4. 新聞情報爬蟲 (Google News 即時新聞 + 關鍵詞情緒判定)
    try:
        news_data = fetch_stock_news(stock_id, stock_name, max_items=5)
        record["news"] = news_data
    except Exception as e:
        record["news"] = {"sentiment_label": "新聞爬蟲跳過", "news_list": []}

    # 5. 數據缺漏自動複檢機制 (Double-Check Mechanism)
    is_rechecked = False

    # (1) 籌碼複檢：若5日合計、外資、投信皆為0，主動發起備援複檢
    chips_cur = record.get("chips", {})
    if (chips_cur.get("total_net_5d", 0) == 0 and 
        chips_cur.get("foreign_net_5d", 0) == 0 and 
        chips_cur.get("trust_net_5d", 0) == 0):
        try:
            chips_retry = CHIPS_ENGINE.analyze_chips(stock_id, allow_recheck=True)
            if (chips_retry.get("total_net_5d", 0) != 0 or 
                chips_retry.get("foreign_net_5d", 0) != 0 or 
                chips_retry.get("is_rechecked")):
                record["chips"] = chips_retry
                is_rechecked = True
        except Exception:
            pass

    # (2) 基本面複檢：若營收 YoY 或 EPS 為 None，再複檢一次
    fund_cur = record.get("fundamental", {})
    if fund_cur.get("revenue_yoy") is None or fund_cur.get("eps") is None:
        try:
            fund_ok_2, fund_reason_2, fund_info_2 = check_fundamental_filters(stock_id)
            if fund_info_2.get("revenue_yoy") is not None or fund_info_2.get("eps") is not None:
                record["fund_ok"] = fund_ok_2
                record["fundamental"] = fund_info_2
                is_rechecked = True
        except Exception:
            pass

    # (3) 技術面複檢：若收盤價為 None，重新以備援後綴複檢
    tech_cur = record.get("tech", {})
    if tech_cur.get("close") is None:
        try:
            is_buy_2, is_sell_2, tech_summary_2, tech_details_2 = analyze_stock_indicators(stock_id)
            if tech_details_2.get("close") is not None:
                record["tech"] = tech_details_2
                record["tech"]["is_buy"] = is_buy_2
                record["tech"]["is_sell"] = is_sell_2
                record["tech"]["summary"] = tech_summary_2
                is_rechecked = True
        except Exception:
            pass

    record["is_rechecked"] = is_rechecked

    # 6. 綜合強烈推薦判定
    fund_pass = record.get("fund_ok", False)
    tech_is_buy = record["tech"].get("is_buy", False)
    chip_favorable = (
        record["chips"].get("is_accumulating") or
        record["chips"].get("trust_consecutive_buy") or
        (record["chips"].get("total_net_5d", 0) > 0)
    )
    news_not_bearish = (record["news"].get("sentiment_score", 0) >= -1)

    if fund_pass and tech_is_buy and chip_favorable and news_not_bearish:
        record["is_strong_buy"] = True

    return record

# --- API 路由區 ---

@app.route("/")
def index():
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response

@app.route("/api/scan_single", methods=["GET", "POST"])
def api_scan_single():
    stock_id = request.args.get("stock_id") or (request.json and request.json.get("stock_id"))
    if not stock_id:
        return jsonify({"success": False, "error": "請提供股票代號"}), 400

    record = analyze_single_stock(stock_id)
    real_id = record["stock_id"]

    with SCAN_LOCK:
        idx = next((i for i, r in enumerate(SCANNED_RESULTS) if r["stock_id"] == real_id), -1)
        if idx >= 0:
            SCANNED_RESULTS[idx] = record
        else:
            SCANNED_RESULTS.insert(0, record)
        save_cache()

    return jsonify({"success": True, "data": record})

@app.route("/api/scan_batch", methods=["POST"])
def api_scan_batch():
    data = request.json or {}
    mode = data.get("mode", "core")
    limit = data.get("limit")  # 自訂檔數，如 30, 50, 100, 200 或 None
    all_cats = get_all_categories()

    if mode in ["all", "watchlist", "watchlist_all"]:
        stock_list = WATCHLIST_STOCKS if WATCHLIST_STOCKS else all_cats.get("core", {}).get("stocks", [])
        cat_title = f"全市場自選母體 (共 {len(stock_list)} 檔)"
    elif mode == "all_market":
        stock_list = list(STOCK_INFO_MAP.keys())
        cat_title = f"全台上市櫃總庫 (共 {len(stock_list)} 檔)"
    else:
        stock_list = all_cats.get(mode, {}).get("stocks", [])
        cat_title = all_cats.get(mode, {}).get("title", "選定類股")

    if not stock_list and data.get("stocks"):
        stock_list = data.get("stocks")
        cat_title = "指定股票清單"

    # 確保代碼標準化並去重
    cleaned_stocks = []
    for s in stock_list:
        real_id = resolve_stock_query(str(s).strip())
        if real_id and real_id not in cleaned_stocks:
            cleaned_stocks.append(real_id)

    # 處理自訂檔數限制 (例如 "掃描 XX 檔股票")
    if limit is not None:
        try:
            lim_val = int(limit)
            if lim_val > 0 and lim_val < len(cleaned_stocks):
                cleaned_stocks = cleaned_stocks[:lim_val]
                cat_title += f" [限前 {lim_val} 檔]"
        except Exception:
            pass

    if not cleaned_stocks:
        return jsonify({"success": False, "error": "無可掃描股票"}), 400

    global SCAN_PROGRESS
    with SCAN_LOCK:
        SCAN_PROGRESS["is_scanning"] = True
        SCAN_PROGRESS["total"] = len(cleaned_stocks)
        SCAN_PROGRESS["current"] = 0
        SCAN_PROGRESS["current_stock"] = "準備啟動多執行緒加速爬蟲..."
        SCAN_PROGRESS["strong_buy_count"] = 0
        SCAN_PROGRESS["fund_ok_count"] = 0
        SCAN_PROGRESS["stop_requested"] = False
        SCAN_PROGRESS["start_time"] = time.time()

    def background_scan(stocks):
        global SCAN_PROGRESS
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def worker(sid):
            if SCAN_PROGRESS.get("stop_requested", False):
                return None
            try:
                rec = analyze_single_stock(sid)
                with SCAN_LOCK:
                    idx = next((i for i, r in enumerate(SCANNED_RESULTS) if r["stock_id"] == sid), -1)
                    if idx >= 0:
                        SCANNED_RESULTS[idx] = rec
                    else:
                        SCANNED_RESULTS.append(rec)

                    SCAN_PROGRESS["current"] += 1
                    sname = rec.get("stock_name", "")
                    SCAN_PROGRESS["current_stock"] = f"{sid} {sname}"
                    if rec.get("is_strong_buy"):
                        SCAN_PROGRESS["strong_buy_count"] += 1
                    if rec.get("fund_ok"):
                        SCAN_PROGRESS["fund_ok_count"] += 1

                    if SCAN_PROGRESS["current"] % 5 == 0 or SCAN_PROGRESS["current"] == len(stocks):
                        save_cache()
                return rec
            except Exception as e:
                with SCAN_LOCK:
                    SCAN_PROGRESS["current"] += 1
                print(f"掃描 {sid} 失敗: {e}")
                return None

        # 採用 4 個並行 Worker 進行高效掃描
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, sid) for sid in stocks]
            for future in as_completed(futures):
                if SCAN_PROGRESS.get("stop_requested", False):
                    break

        with SCAN_LOCK:
            SCAN_PROGRESS["is_scanning"] = False
            SCAN_PROGRESS["current_stock"] = "掃描完畢"
            save_cache()

    thread = threading.Thread(target=background_scan, args=(cleaned_stocks,))
    thread.daemon = True
    thread.start()

    return jsonify({
        "success": True,
        "message": f"已在背景啟動【{cat_title}】共 {len(cleaned_stocks)} 檔股票爬蟲掃描",
        "count": len(cleaned_stocks)
    })

@app.route("/api/scan_progress", methods=["GET"])
def api_scan_progress():
    with SCAN_LOCK:
        total = SCAN_PROGRESS.get("total", 0)
        current = SCAN_PROGRESS.get("current", 0)
        percent = int((current / total) * 100) if total > 0 else 0
        elapsed = int(time.time() - SCAN_PROGRESS.get("start_time", time.time())) if SCAN_PROGRESS.get("is_scanning") else 0
        return jsonify({
            "success": True,
            "progress": {
                "is_scanning": SCAN_PROGRESS.get("is_scanning", False),
                "total": total,
                "current": current,
                "percent": percent,
                "current_stock": SCAN_PROGRESS.get("current_stock", ""),
                "strong_buy_count": SCAN_PROGRESS.get("strong_buy_count", 0),
                "fund_ok_count": SCAN_PROGRESS.get("fund_ok_count", 0),
                "stop_requested": SCAN_PROGRESS.get("stop_requested", False),
                "elapsed_seconds": elapsed
            }
        })

@app.route("/api/scan_stop", methods=["POST"])
def api_scan_stop():
    with SCAN_LOCK:
        if SCAN_PROGRESS.get("is_scanning", False):
            SCAN_PROGRESS["stop_requested"] = True
            return jsonify({"success": True, "message": "已成功發送中止指令，系統正在停止背景掃描。"})
        else:
            return jsonify({"success": True, "message": "目前無進行中的掃描作業。"})

@app.route("/api/all_results", methods=["GET"])
def api_all_results():
    return jsonify({
        "success": True,
        "total": len(SCANNED_RESULTS),
        "data": SCANNED_RESULTS
    })

@app.route("/api/clear_cache", methods=["POST"])
def api_clear_cache():
    global SCANNED_RESULTS
    with SCAN_LOCK:
        SCANNED_RESULTS = []
        save_cache()
    report_file = os.path.join(CURRENT_DIR, "report.html")
    if os.path.exists(report_file):
        try:
            os.remove(report_file)
        except Exception:
            pass
    return jsonify({"success": True, "message": "已成功清空所有掃描資料與 HTML 報告"})

@app.route("/api/categories", methods=["GET"])
def api_categories():
    all_cats = get_all_categories()
    groups = ["核心精選", "集團概念", "半導體族群", "熱門題材", "自訂類股"]
    formatted = {}
    for k, v in all_cats.items():
        formatted[k] = {
            "id": k,
            "title": v["title"],
            "group": v.get("group", "熱門題材"),
            "count": len(v.get("stocks", [])),
            "stocks": v.get("stocks", []),
            "is_custom": v.get("is_custom", False)
        }
    return jsonify({
        "success": True,
        "categories": formatted,
        "groups": groups
    })

@app.route("/api/custom_category", methods=["POST"])
def api_custom_category():
    data = request.json or {}
    cat_id = str(data.get("id", "")).strip()
    title = str(data.get("title", "")).strip()
    raw_stocks = data.get("stocks", [])

    if not title:
        return jsonify({"success": False, "error": "請填寫類股名稱"}), 400

    # 解析股票代號（支援逗號/空格/換行/分號分割字串，或陣列）
    stock_tokens = []
    if isinstance(raw_stocks, str):
        tokens = re.split(r'[,;\s\n\r]+', raw_stocks)
        stock_tokens = [t.strip() for t in tokens if t.strip()]
    elif isinstance(raw_stocks, list):
        stock_tokens = [str(t).strip() for t in raw_stocks if str(t).strip()]

    resolved_stocks = []
    for token in stock_tokens:
        sid = resolve_stock_query(token)
        if sid and sid not in resolved_stocks:
            resolved_stocks.append(sid)

    if not resolved_stocks:
        return jsonify({"success": False, "error": "請至少提供一檔有效的股票代號或名稱"}), 400

    if not cat_id or cat_id not in CUSTOM_CATEGORIES:
        cat_id = f"custom_{int(time.time())}"

    # 若名稱無前綴 emoji，自動加上預設圖示
    has_emoji = any(ord(char) > 0x2000 for char in title[:3]) if title else False
    if not has_emoji:
        title = f"🏷️ {title}"

    CUSTOM_CATEGORIES[cat_id] = {
        "id": cat_id,
        "title": title,
        "group": "自訂類股",
        "stocks": resolved_stocks,
        "is_custom": True,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_custom_categories()

    return jsonify({
        "success": True,
        "message": f"成功儲存自訂類股「{title}」（共 {len(resolved_stocks)} 檔）",
        "category": CUSTOM_CATEGORIES[cat_id]
    })

@app.route("/api/custom_category/<cat_id>", methods=["DELETE"])
def api_delete_custom_category(cat_id):
    if cat_id in CUSTOM_CATEGORIES:
        title = CUSTOM_CATEGORIES[cat_id].get("title", cat_id)
        del CUSTOM_CATEGORIES[cat_id]
        save_custom_categories()
        return jsonify({"success": True, "message": f"已成功刪除自訂類股「{title}」"})
    return jsonify({"success": False, "error": "找不到此自訂類股"}), 404

@app.route("/api/top_gainers", methods=["GET"])
def api_top_gainers():
    active_stocks = [
        {"stock_id": "3450", "name": "聯鈞", "sector": "光電/CPO"},
        {"stock_id": "3017", "name": "奇鋐", "sector": "散熱模組"},
        {"stock_id": "3324", "name": "雙鴻", "sector": "散熱模組"},
        {"stock_id": "8028", "name": "昇陽半", "sector": "再生晶圓"},
        {"stock_id": "6669", "name": "緯穎", "sector": "AI伺服器"},
        {"stock_id": "1519", "name": "華城", "sector": "重電能源"},
        {"stock_id": "2382", "name": "廣達", "sector": "AI伺服器"},
        {"stock_id": "2454", "name": "聯發科", "sector": "IC設計"}
    ]
    return jsonify({"success": True, "stocks": active_stocks})

@app.route("/api/history/save", methods=["POST"])
def api_history_save():
    with SCAN_LOCK:
        records_copy = list(SCANNED_RESULTS)
    data = request.get_json(silent=True) or {}
    tag = data.get("tag", "web_manual")
    scope = data.get("scope", "戰情室歷史封存")
    res = archive_scan_results(records=records_copy, tag=tag, scan_scope=scope)
    return jsonify(res)

@app.route("/api/history/list", methods=["GET"])
def api_history_list():
    items = load_history_index()
    return jsonify({"success": True, "history": items})

@app.route("/api/history/verify", methods=["GET", "POST"])
def api_history_verify():
    target_id = request.args.get("id") or (request.get_json(silent=True) or {}).get("id")
    res = verify_history(target_id)
    return jsonify(res)

@app.route("/history/<path:filename>")
def serve_history_files(filename):
    return send_from_directory(HISTORY_DIR, filename)

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "台股量化多因子戰情室",
        "short_name": "量化選股",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#38bdf8",
        "icons": [
            {
                "src": "https://cdn-icons-png.flaticon.com/512/2422/2422796.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    })

init_stock_info()
load_watchlist()
load_custom_categories()
load_company_profiles()
load_cache()

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 【台股量化多因子選股戰情室】純爬蟲架構 Web 服務已就緒！")
    print("   特性：100% 免 FinMind API，零連線次數限制，極速穩定")
    print("   本機電腦網址： http://localhost:5000")
    print("   手機區域網路： http://<你的電腦IP>:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
