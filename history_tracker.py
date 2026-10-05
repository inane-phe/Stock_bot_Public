# -*- coding: utf-8 -*-
"""
history_tracker.py
台股量化多因子選股戰情室 - 歷史分析紀錄與回顧檢驗核心引擎
功能：
1. 將掃描分析結果自動/手動封存為時間戳歷史紀錄 (HTML 視覺化報告、Excel CSV、完整結構化 JSON)
2. 建立 history/index.html 歷次執行時間軸目錄
3. 在未來任意時間點一鍵執行「歷史回顧檢驗」：自動抓取當前最新即時股價，比對當時推薦勝率、累積漲跌幅與回測績效
"""
import os
import sys
import json
import csv
import datetime
import time
import re
import requests
import bs4

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from html_generator import generate_html_report

HISTORY_DIR = os.path.join(CURRENT_DIR, "history")
RECORDS_DIR = os.path.join(HISTORY_DIR, "records")
REPORTS_DIR = os.path.join(HISTORY_DIR, "reports")
CSV_DIR = os.path.join(HISTORY_DIR, "csv")
VERIFY_DIR = os.path.join(HISTORY_DIR, "verifications")
INDEX_JSON_FILE = os.path.join(HISTORY_DIR, "index.json")
INDEX_HTML_FILE = os.path.join(HISTORY_DIR, "index.html")
CACHE_FILE = os.path.join(CURRENT_DIR, "scanned_cache.json")

def ensure_dirs():
    """確保歷史資料夾完整結構"""
    for d in [HISTORY_DIR, RECORDS_DIR, REPORTS_DIR, CSV_DIR, VERIFY_DIR]:
        os.makedirs(d, exist_ok=True)

def load_history_index():
    """載入歷次歷史紀錄目錄清單"""
    ensure_dirs()
    if os.path.exists(INDEX_JSON_FILE):
        try:
            with open(INDEX_JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history_index(items):
    """持久化儲存歷次歷史紀錄清單"""
    ensure_dirs()
    try:
        with open(INDEX_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 儲存 index.json 失敗: {e}")

def history_decision(record):
    """將單筆掃描結果轉換為穩定的決策代碼，供覆盤統計使用"""
    if record.get("is_strong_buy"):
        return "strong_buy", "✨ 強烈買進"
    if record.get("tech", {}).get("is_sell"):
        return "risk", "🛑 出場警戒"
    if record.get("fund_ok"):
        return "fund", "🟢 基本面優"
    return "watch", "⚪ 觀察中"

def evaluate_history_point(decision_code, base_price, next_price):
    """以下一個可觀測節點檢驗決策方向是否被股價表現支持"""
    if base_price is None or next_price is None or base_price <= 0:
        return {
            "code": "unknown",
            "label": "未定",
            "text": "尚無後續節點可檢驗",
            "return_pct": None
        }

    return_pct = round((next_price / base_price - 1) * 100, 2)
    up = return_pct > 0.05
    down = return_pct < -0.05

    if decision_code == "strong_buy":
        if up:
            result = ("meet", "✅ 符合評價", f"強烈買進後上漲 {return_pct:+.2f}%")
        elif down:
            result = ("miss", "❌ 不符合評價", f"強烈買進後下跌 {return_pct:+.2f}%")
        else:
            result = ("neutral", "⚪ 持平", f"後續節點變動 {return_pct:+.2f}%")
    elif decision_code == "risk":
        if down:
            result = ("meet", "✅ 符合評價", f"出場警戒後回檔 {return_pct:+.2f}%")
        elif up:
            result = ("miss", "❌ 不符合評價", f"警戒後反而上漲 {return_pct:+.2f}%")
        else:
            result = ("neutral", "⚪ 持平", f"後續節點變動 {return_pct:+.2f}%")
    elif decision_code == "fund":
        if up:
            result = ("meet", "✅ 符合評價", f"基本面優先方向上漲 {return_pct:+.2f}%")
        elif down:
            result = ("miss", "❌ 不符合評價", f"基本面優先方向下跌 {return_pct:+.2f}%")
        else:
            result = ("neutral", "⚪ 持平", f"後續節點變動 {return_pct:+.2f}%")
    else:
        result = ("neutral", "⚪ 中性", f"觀察決策，後續 {return_pct:+.2f}%")

    return {
        "code": result[0],
        "label": result[1],
        "text": result[2],
        "return_pct": return_pct
    }

def build_history_analysis_payload(history_list):
    """
    掃描所有歷史 JSON，輸出精簡的個股時間序列。
    每個節點保留股價、綜合決策、因子摘要，並用下一個節點計算符合/不符合評價。
    """
    nodes = []
    node_by_id = {}
    stocks = {}
    sector_index = {}

    for history_index, history in enumerate(reversed(history_list or [])):
        history_id = history.get("id", "")
        history_dt = history.get("datetime", history.get("timestamp", ""))
        label = history_dt
        try:
            label = datetime.datetime.strptime(history_dt, "%Y-%m-%d %H:%M:%S").strftime("%m/%d %H:%M")
        except ValueError:
            label = history_dt
        node = {"id": history_id, "index": history_index, "datetime": history_dt, "label": label}
        nodes.append(node)
        node_by_id[history_id] = node

        json_rel = history.get("json_file", "")
        if not json_rel:
            continue
        json_path = os.path.join(HISTORY_DIR, json_rel.replace("/", os.sep))
        if not os.path.exists(json_path):
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"⚠️ 讀取覆盤 JSON 失敗 {json_path}: {e}")
            continue

        for record in payload.get("records", []):
            stock_id = str(record.get("stock_id", "")).strip()
            tech = record.get("tech", {}) or {}
            try:
                price = float(tech.get("close"))
            except (TypeError, ValueError):
                continue

            decision_code, decision_label = history_decision(record)
            fund = record.get("fundamental", {}) or {}
            chips = record.get("chips", {}) or {}
            news = record.get("news", {}) or {}
            sector = record.get("sector", "未分類")

            stock = stocks.setdefault(stock_id, {
                "stock_id": stock_id,
                "name": record.get("stock_name", stock_id),
                "sector": sector,
                "business": record.get("main_business", ""),
                "points": []
            })
            stock["name"] = record.get("stock_name") or stock["name"]
            stock["sector"] = sector or stock["sector"]
            stock["business"] = record.get("main_business") or stock["business"]

            point = {
                "history_id": history_id,
                "node_index": history_index,
                "datetime": history_dt,
                "price": round(price, 2),
                "decision_code": decision_code,
                "decision": decision_label,
                "fund_ok": bool(record.get("fund_ok")),
                "technical": {
                    "trend": tech.get("trend_pattern", ""),
                    "signal": tech.get("signal_type", ""),
                    "summary": tech.get("summary", ""),
                    "sma20": tech.get("sma20"),
                    "bb_bandwidth": tech.get("bb_bandwidth")
                },
                "fundamental": {
                    "revenue_yoy": fund.get("revenue_yoy"),
                    "revenue_month": fund.get("revenue_month", ""),
                    "eps": fund.get("eps"),
                    "eps_quarter": fund.get("eps_quarter", "")
                },
                "chips": {
                    "summary": chips.get("status_summary", ""),
                    "signals": chips.get("chip_signals", []),
                    "foreign_net_5d": chips.get("foreign_net_5d"),
                    "trust_net_5d": chips.get("trust_net_5d"),
                    "total_net_5d": chips.get("total_net_5d")
                },
                "news_label": news.get("sentiment_label", "")
            }
            stock["points"].append(point)

            if sector:
                sector_index.setdefault(sector, set()).add(stock_id)

    # 排序節點資料，並以同一檔股票的下一個可觀測節點計算覆盤評價
    for stock in stocks.values():
        stock["points"].sort(key=lambda p: (p["node_index"], p["datetime"]))
        points = stock["points"]
        for idx, point in enumerate(points):
            next_price = points[idx + 1]["price"] if idx + 1 < len(points) else None
            point["evaluation"] = evaluate_history_point(point["decision_code"], point["price"], next_price)

    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nodes": nodes,
        "stocks": stocks,
        "sector_index": {k: sorted(v) for k, v in sorted(sector_index.items())}
    }

def render_history_analysis_section(analysis_payload):
    """產生 history 總覽內嵌的股票/類股覆盤圖表區塊"""
    payload_js = json.dumps(analysis_payload, ensure_ascii=False, separators=(",", ":"))
    payload_js = payload_js.replace("</", "<\\/")
    return f"""
    <link rel="stylesheet" href="analysis_review.css">
    <section class="analysis-section" aria-label="History 股價與決策覆盤">
        <div class="analysis-head">
            <div>
                <h2>📈 History 股價與決策覆盤</h2>
                <p>選擇特定股票或類股，折線圖的每個節點都是一次封存掃描；點擊節點可查看當時綜合決策與後續評價。</p>
            </div>
            <div class="analysis-controls">
                <div class="control-group">
                    <label class="control-label" for="historyAnalysisMode">檢視模式</label>
                    <select id="historyAnalysisMode" class="analysis-select">
                        <option value="stock">特定股票</option>
                        <option value="sector">特定類股</option>
                    </select>
                </div>
                <div class="control-group">
                    <label class="control-label" for="historyAnalysisTarget">股票 / 類股</label>
                    <select id="historyAnalysisTarget" class="analysis-select"></select>
                </div>
                <div class="control-group stock-search" id="historyAnalysisSearchGroup">
                    <label class="control-label" for="historyAnalysisStockSearch">搜尋股票</label>
                    <input id="historyAnalysisStockSearch" class="analysis-input" type="search"
                           placeholder="輸入代號 / 名稱 / 產業" autocomplete="off" aria-expanded="false"
                           aria-controls="historyAnalysisStockResults">
                    <div id="historyAnalysisStockResults" class="stock-search-results" hidden></div>
                </div>
                <button id="historyAnalysisCustomButton" class="btn-outline" type="button">自訂類股</button>
                <button id="historyAnalysisReset" class="btn-reset" type="button">重設檢視</button>
            </div>
        </div>
        <div class="metric-grid" id="historyAnalysisMetrics"></div>
        <div class="chart-card">
            <div class="chart-top">
                <h3 id="historyAnalysisChartTitle"></h3>
                <span class="chart-note" id="historyAnalysisChartNote"></span>
            </div>
            <div class="history-chart" id="historyAnalysisChart"></div>
            <div class="chart-legend">
                <span><i class="legend-dot" style="background:#fbbf24;"></i>強烈買進</span>
                <span><i class="legend-dot" style="background:#ef4444;"></i>出場警戒</span>
                <span><i class="legend-dot" style="background:#10b981;"></i>基本面優</span>
                <span><i class="legend-dot" style="background:#94a3b8;"></i>觀察中</span>
            </div>
        </div>
        <div id="historyAnalysisDetail" class="node-detail"></div>
        <div class="table-note" id="historyAnalysisTableNote"></div>
        <div class="analysis-table-wrap">
            <table class="analysis-table">
                <thead><tr id="historyAnalysisTableHead"></tr></thead>
                <tbody id="historyAnalysisTableBody"></tbody>
            </table>
        </div>
    </section>
    <div id="historyCustomCategoryModal" class="history-modal" hidden>
        <div class="history-modal-card" role="dialog" aria-modal="true" aria-labelledby="historyCustomModalTitle">
            <div class="history-modal-head">
                <h3 id="historyCustomModalTitle">自訂類股</h3>
                <button id="historyCustomCategoryClose" class="modal-close" type="button" aria-label="關閉">&times;</button>
            </div>
            <form id="historyCustomCategoryForm">
                <input id="historyCustomCategoryId" type="hidden" value="">
                <div class="modal-field">
                    <label class="control-label" for="historyCustomCategoryTitle">類股名稱</label>
                    <input id="historyCustomCategoryTitle" class="analysis-input" type="text" placeholder="例如：我的 AI 供應鏈" required>
                </div>
                <div class="modal-field">
                    <label class="control-label" for="historyCustomCategoryStocks">股票清單</label>
                    <textarea id="historyCustomCategoryStocks" class="analysis-textarea" rows="3"
                              placeholder="支援代號或名稱，用逗號 / 空格 / 換行分隔" required></textarea>
                </div>
                <div class="modal-actions">
                    <button id="historyCustomCategoryReset" class="btn-outline" type="button">清空重填</button>
                    <button id="historyCustomCategorySave" class="btn-primary" type="submit">儲存類股</button>
                </div>
                <div id="historyCustomCategoryFeedback" class="modal-feedback" role="status"></div>
            </form>
            <div class="modal-list-title">已儲存自訂類股</div>
            <div id="historyCustomCategoryList" class="modal-list"></div>
        </div>
    </div>
    <script>window.HISTORY_ANALYSIS_DATA = {payload_js};</script>
    <script src="analysis_review.js"></script>
    """

def get_latest_price(stock_id):
    """
    抓取最新即時股價 (供歷史回顧檢驗時比對當時價格)
    """
    stock_id = str(stock_id).strip()
    # 1. 優先爬取 Yahoo 奇摩股市 (免 Token，極速)
    try:
        url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            soup = bs4.BeautifulSoup(r.text, 'html.parser')
            el = soup.find(class_=re.compile(r'Fz\((32|36|40)px\)'))
            if el:
                txt = el.text.replace(',', '').strip()
                if txt and txt != '-':
                    return float(txt)
            meta = soup.find('meta', property='og:description')
            if meta:
                m = re.search(r'([\d,]+\.?\d*)', meta.get('content', ''))
                if m:
                    return float(m.group(1).replace(',', ''))
    except Exception:
        pass

    # 2. 備援採用 yfinance
    try:
        import yfinance as yf
        for suffix in ['.TW', '.TWO']:
            ticker = yf.Ticker(f"{stock_id}{suffix}")
            df = ticker.history(period="3d")
            if not df.empty:
                return round(float(df['Close'].iloc[-1]), 2)
    except Exception:
        pass

    return None

def archive_scan_results(records=None, tag="manual", scan_scope="台股多因子量化掃描"):
    """
    封存當前掃描結果至歷史紀錄 (產生 JSON / CSV / HTML 及更新總表)
    """
    ensure_dirs()

    # 若未傳入 records 或為空列表，自動自 scanned_cache.json 載入
    if not records:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception as e:
                return {"success": False, "error": f"讀取 scanned_cache.json 失敗: {e}"}
        else:
            return {"success": False, "error": "目前沒有任何掃描暫存資料，請先執行掃描！"}

    if not records:
        return {"success": False, "error": "暫存資料為空，無法封存歷史紀錄！"}

    now = datetime.datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    dt_display = now.strftime("%Y-%m-%d %H:%M:%S")

    total_count = len(records)
    strong_buys = [r for r in records if r.get("is_strong_buy")]
    fund_passes = [r for r in records if r.get("fund_ok")]
    risk_sells = [r for r in records if r.get("tech", {}).get("is_sell")]

    record_id = f"history_{ts}"
    json_filename = f"history_{ts}.json"
    csv_filename = f"history_{ts}.csv"
    report_filename = f"report_{ts}.html"

    json_filepath = os.path.join(RECORDS_DIR, json_filename)
    csv_filepath = os.path.join(CSV_DIR, csv_filename)
    report_filepath = os.path.join(REPORTS_DIR, report_filename)

    meta_entry = {
        "id": record_id,
        "timestamp": ts,
        "datetime": dt_display,
        "tag": tag,
        "scan_scope": scan_scope,
        "total_stocks": total_count,
        "strong_buy_count": len(strong_buys),
        "fund_pass_count": len(fund_passes),
        "risk_sell_count": len(risk_sells),
        "strong_buy_stocks": [f"{r.get('stock_id')} {r.get('stock_name')}" for r in strong_buys],
        "json_file": f"records/{json_filename}",
        "csv_file": f"csv/{csv_filename}",
        "report_file": f"reports/{report_filename}"
    }

    # 1. 寫入完整 JSON 歷史紀錄
    try:
        full_payload = {
            "meta": meta_entry,
            "records": records
        }
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(full_payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "error": f"寫入歷史 JSON 失敗: {e}"}

    # 2. 寫入 Excel 試算表 CSV (帶 UTF-8 BOM 避免 Excel 繁體中文亂碼)
    try:
        with open(csv_filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            # 欄位清單
            writer.writerow([
                "紀錄時間", "股票代號", "股票名稱", "所屬產業", "主要營業項目",
                "綜合決策", "當時基準股價", "營收YoY%", "營收月份", "單季EPS(元)",
                "布林帶寬%", "月線SMA20", "型態趨勢特徵",
                "外資5日買賣超(張)", "投信5日買賣超(張)", "三大法人合計5日(張)",
                "籌碼訊號標籤", "新聞情緒標籤",
                "最新股價(回顧檢驗)", "累積漲跌幅%(回顧檢驗)", "檢驗判定結論", "投資筆記與覆盤備註"
            ])

            for r in records:
                sid = r.get("stock_id", "")
                sname = r.get("stock_name", "")
                sec = r.get("sector", "")
                biz = r.get("main_business", "")
                
                if r.get("is_strong_buy"):
                    dec = "✨ 強烈買進"
                elif r.get("tech", {}).get("is_sell"):
                    dec = "🛑 出場警戒"
                elif r.get("fund_ok"):
                    dec = "🟢 基本面優"
                else:
                    dec = "⚪ 觀察中"

                fund = r.get("fundamental", {})
                tech = r.get("tech", {})
                chips = r.get("chips", {})
                news = r.get("news", {})

                close_p = tech.get("close", "")
                yoy = fund.get("revenue_yoy", "")
                yoy_m = fund.get("revenue_month", "")
                eps = fund.get("eps", "")
                bw = tech.get("bb_bandwidth", "")
                sma20 = tech.get("sma20", "")
                trend = tech.get("trend_pattern", "")

                f_net = chips.get("foreign_net_5d", "")
                t_net = chips.get("trust_net_5d", "")
                tot_net = chips.get("total_net_5d", "")
                chip_sig = " / ".join(chips.get("chip_signals", []))
                news_lbl = news.get("sentiment_label", "")

                writer.writerow([
                    dt_display, sid, sname, sec, biz,
                    dec, close_p, yoy, yoy_m, eps,
                    bw, sma20, trend,
                    f_net, t_net, tot_net,
                    chip_sig, news_lbl,
                    "", "", "", "" # 預留未來回顧欄位
                ])
    except Exception as e:
        print(f"⚠️ 寫入 CSV 失敗: {e}")

    # 3. 渲染獨立離線 HTML 報告
    try:
        generate_html_report(records, output_file=report_filepath, scan_scope=f"{scan_scope} [{dt_display}]")
    except Exception as e:
        print(f"⚠️ 渲染 HTML 報告失敗: {e}")

    # 4. 更新歷史目錄 index.json 與 index.html
    history_list = load_history_index()
    # 移除同 ID 的舊項目（若有）
    history_list = [item for item in history_list if item.get("id") != record_id]
    history_list.insert(0, meta_entry)
    save_history_index(history_list)
    render_history_index_html(history_list)

    print(f"✅ [History] 成功封存歷史紀錄：{record_id} ({total_count} 檔標的)")
    print(f"   📁 歷史 JSON：{json_filepath}")
    print(f"   📊 試算表 CSV：{csv_filepath}")
    print(f"   🌐 視覺化報告：{report_filepath}")

    return {
        "success": True,
        "record_id": record_id,
        "datetime": dt_display,
        "total_stocks": total_count,
        "strong_buy_count": len(strong_buys),
        "json_path": json_filepath,
        "csv_path": csv_filepath,
        "report_path": report_filepath
    }

def render_history_index_html(history_list):
    """產出 history/index.html 歷次執行時間軸總表頁面"""
    analysis_section = render_history_analysis_section(build_history_analysis_payload(history_list))
    rows_html = []
    for h in history_list:
        hid = h.get("id", "")
        dt = h.get("datetime", "")
        scope = h.get("scan_scope", "")
        total = h.get("total_stocks", 0)
        s_buy = h.get("strong_buy_count", 0)
        f_pass = h.get("fund_pass_count", 0)
        risk = h.get("risk_sell_count", 0)
        stocks_sample = ", ".join(h.get("strong_buy_stocks", [])[:5])
        if len(h.get("strong_buy_stocks", [])) > 5:
            stocks_sample += f" ...等共 {s_buy} 檔"
        elif not stocks_sample:
            stocks_sample = "無"

        rep_link = h.get("report_file", "")
        csv_link = h.get("csv_file", "")
        json_link = h.get("json_file", "")

        rows_html.append(f"""
        <tr>
            <td>
                <strong style="color:#38bdf8; font-size:15px;">{dt}</strong>
                <div style="font-size:12px; color:#94a3b8; font-family:monospace;">{hid}</div>
            </td>
            <td><span style="color:#f8fafc;">{scope}</span> ({total} 檔)</td>
            <td>
                <span class="pill pill-gold">✨ 推薦: {s_buy} 檔</span>
                <div style="font-size:12px; color:#fbbf24; margin-top:4px;">{stocks_sample}</div>
            </td>
            <td>
                <span class="pill pill-green">🟢 基本優: {f_pass}</span>
                <span class="pill pill-red">🛑 警戒: {risk}</span>
            </td>
            <td>
                <div style="display:flex; gap:6px; flex-wrap:wrap;">
                    <a href="{rep_link}" target="_blank" class="btn btn-view">👁️ HTML 報告</a>
                    <a href="{csv_link}" download class="btn btn-csv">📊 Excel CSV</a>
                    <a href="{json_link}" target="_blank" class="btn btn-json">📄 JSON</a>
                    <button class="btn btn-verify" onclick="triggerVerify('{hid}')">🎯 回顧檢驗</button>
                </div>
            </td>
        </tr>
        """)

    body_content = "".join(rows_html) if rows_html else '<tr><td colspan="5" style="text-align:center; padding:30px; color:#94a3b8;">目前尚無任何歷史紀錄，請執行掃描後點擊「封存歷史紀錄」！</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📜 台股多因子戰情室 - 歷次執行歷史紀錄總覽</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#f8fafc; padding:20px; line-height:1.5; }}
        .container {{ max-width:1300px; margin:0 auto; }}
        header {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:16px; border-bottom:1px solid #334155; margin-bottom:20px; flex-wrap:wrap; gap:12px; }}
        h1 {{ font-size:22px; font-weight:700; color:#fff; display:flex; align-items:center; gap:8px; }}
        .btn {{ padding:7px 14px; border-radius:8px; font-size:13px; font-weight:700; text-decoration:none; display:inline-flex; align-items:center; cursor:pointer; border:none; transition:all 0.2s; }}
        .btn:hover {{ filter:brightness(1.15); transform:translateY(-1px); }}
        .btn-home {{ background:#38bdf8; color:#0f172a; }}
        .btn-view {{ background:#fbbf24; color:#000; }}
        .btn-csv {{ background:#10b981; color:#fff; }}
        .btn-json {{ background:#64748b; color:#fff; }}
        .btn-verify {{ background:#c084fc; color:#000; }}
        .table-wrap {{ background:#1e293b; border:1px solid #334155; border-radius:12px; overflow-x:auto; }}
        table {{ width:100%; border-collapse:collapse; text-align:left; font-size:14px; }}
        th {{ background:#172033; color:#94a3b8; padding:12px 16px; border-bottom:1px solid #334155; white-space:nowrap; }}
        td {{ padding:14px 16px; border-bottom:1px solid rgba(51,65,85,0.4); vertical-align:middle; }}
        tr:hover {{ background:#334155; }}
        .pill {{ padding:3px 8px; border-radius:9999px; font-size:12px; font-weight:700; display:inline-block; margin-right:4px; }}
        .pill-gold {{ background:rgba(251,191,36,0.2); color:#fbbf24; border:1px solid rgba(251,191,36,0.4); }}
        .pill-green {{ background:rgba(16,185,129,0.2); color:#10b981; }}
        .pill-red {{ background:rgba(239,68,68,0.2); color:#ef4444; }}
        .verify-panel {{ background:#1e293b; border:1px solid #38bdf8; border-radius:12px; padding:16px; margin-bottom:20px; display:none; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>📜 歷次量化分析歷史紀錄總覽</h1>
                <div style="font-size:13px; color:#94a3b8; margin-top:4px;">
                    支援離線回顧 ✕ 歷次選股 HTML 報告 ✕ Excel CSV 試算表 ✕ 即時回測檢驗命中率
                </div>
            </div>
            <div>
                <a href="http://localhost:5000" class="btn btn-home">🌐 返回 Web 戰情室</a>
            </div>
        </header>

        <div id="verifyPanel" class="verify-panel">
            <h3 style="color:#38bdf8; margin-bottom:8px;">🎯 正在執行回顧檢驗...</h3>
            <div id="verifyResultText" style="font-size:14px; color:#cbd5e1; line-height:1.6;"></div>
        </div>

        {analysis_section}

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>分析執行時間</th>
                        <th>掃描母體</th>
                        <th>當時推薦名單 (多頭共振)</th>
                        <th>因子過濾統計</th>
                        <th>查看歷史檔案與回顧檢驗</th>
                    </tr>
                </thead>
                <tbody>
                    {body_content}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        async function triggerVerify(historyId) {{
            const p = document.getElementById('verifyPanel');
            const resBox = document.getElementById('verifyResultText');
            p.style.display = 'block';
            resBox.innerHTML = '<span style="color:#fbbf24;">⏳ 正在連線台灣股市最新即時報價，比對 ' + historyId + ' 當時推薦標的表現...</span>';

            try {{
                const res = await fetch('/api/history/verify?id=' + encodeURIComponent(historyId));
                const data = await res.json();
                if (data.success) {{
                    const s = data.summary;
                    resBox.innerHTML = `
                        <div style="font-size:16px; font-weight:700; color:#10b981; margin-bottom:6px;">
                            ✅ 回顧檢驗完成！【${{historyId}}】
                        </div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; margin:10px 0;">
                            <div>✨ 推薦檔數：<strong>${{s.strong_buy_total}}</strong> 檔</div>
                            <div>🎯 獲利勝率：<strong style="color:#fbbf24; font-size:16px;">${{s.win_rate}}%</strong> (${{s.profitable_count}} 贏 / ${{s.loss_count}} 輸)</div>
                            <div>📈 平均累積漲幅：<strong style="color:${{s.avg_return >= 0 ? '#ef4444':'#10b981'}};">${{s.avg_return >= 0 ? '+':''}}${{s.avg_return}}%</strong></div>
                            <div>🏆 最佳標的：<strong>${{s.best_stock || '無'}}</strong> (${{s.best_return >= 0 ? '+':''}}${{s.best_return}}%)</div>
                        </div>
                        <div style="margin-top:8px;">
                            <a href="${{data.verify_report_url}}" target="_blank" class="btn btn-view" style="font-size:12px; padding:4px 10px;">檢視完整回測檢驗報告</a>
                        </div>
                    `;
                }} else {{
                    resBox.innerHTML = '<span style="color:#ef4444;">❌ 檢驗失敗: ' + (data.error || '未知原因') + '</span>';
                }}
            }} catch(e) {{
                resBox.innerHTML = '<span style="color:#ef4444;">連線錯誤: 請確認 app.py 服務正在運行中 (' + e + ')</span>';
            }}
        }}
    </script>
</body>
</html>
"""
    try:
        with open(INDEX_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"⚠️ 寫入 history/index.html 失敗: {e}")

def verify_history(target_id=None):
    """
    執行歷史回顧檢驗：比對最新即時報價，驗證當時分析是否正確
    """
    ensure_dirs()
    index_list = load_history_index()
    if not index_list:
        print("❌ 目前無任何歷史紀錄可供檢驗！請先執行掃描並封存紀錄。")
        return {"success": False, "error": "無歷史紀錄"}

    selected = None
    if target_id:
        for item in index_list:
            if item.get("id") == target_id:
                selected = item
                break
    
    if not selected:
        # 預設挑選最新一筆
        selected = index_list[0]

    rec_id = selected.get("id")
    json_rel = selected.get("json_file")
    json_path = os.path.join(HISTORY_DIR, json_rel.replace("/", os.sep))

    if not os.path.exists(json_path):
        print(f"❌ 找不到歷史資料檔: {json_path}")
        return {"success": False, "error": f"找不到歷史檔案: {json_path}"}

    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    records = payload.get("records", [])
    analysis_dt = selected.get("datetime")
    print("=" * 65)
    print(f"🎯 啟動歷史回顧檢驗引擎")
    print(f"   歷史紀錄代碼: {rec_id}")
    print(f"   當時分析時間: {analysis_dt}")
    print(f"   受測標的總數: 共 {len(records)} 檔")
    print("=" * 65)

    verified_results = []
    strong_buy_verified = []

    for idx, r in enumerate(records, 1):
        sid = r.get("stock_id")
        sname = r.get("stock_name")
        tech = r.get("tech", {})
        base_price = tech.get("close")
        is_strong_buy = r.get("is_strong_buy", False)
        is_sell = tech.get("is_sell", False)
        fund_ok = r.get("fund_ok", False)

        if not base_price or base_price == "N/A":
            continue

        try:
            base_price = float(base_price)
        except Exception:
            continue

        print(f"[{idx:02d}/{len(records):02d}] 正在比對 【{sid} {sname}】(當時價: {base_price})...", end="", flush=True)

        latest_p = get_latest_price(sid)
        if latest_p is None:
            print(" 👉 ⚠️ 無法取得即時報價 (跳過)")
            continue

        diff = latest_p - base_price
        pct = round((diff / base_price) * 100, 2)
        diff_str = f"{pct:+.2f}%"

        # 準確性判定邏輯
        conclusion = ""
        is_win = False

        if is_strong_buy:
            if pct > 0:
                conclusion = "🎯 推薦成功 (獲利)"
                is_win = True
            elif pct < 0:
                conclusion = "❌ 推薦失誤 (虧損)"
                is_win = False
            else:
                conclusion = "⚪ 持平"
        elif is_sell:
            if pct < 0:
                conclusion = "🛡️ 避險成功 (股價回檔)"
                is_win = True
            else:
                conclusion = "⚠️ 賣出後反彈"
        elif fund_ok:
            if pct > 0:
                conclusion = "🟢 基本面推升 (上漲)"
            else:
                conclusion = "⚪ 基本面回檔"
        else:
            conclusion = "⚪ 觀察中"

        print(f" 👉 最新價: {latest_p} ({diff_str}) | {conclusion}")

        item_res = {
            "stock_id": sid,
            "stock_name": sname,
            "sector": r.get("sector", ""),
            "main_business": r.get("main_business", ""),
            "decision": "✨ 強烈買進" if is_strong_buy else ("🛑 出場警戒" if is_sell else ("🟢 基本面優" if fund_ok else "⚪ 觀察中")),
            "base_price": base_price,
            "latest_price": latest_p,
            "diff": round(diff, 2),
            "return_pct": pct,
            "is_win": is_win,
            "conclusion": conclusion
        }
        verified_results.append(item_res)

        if is_strong_buy:
            strong_buy_verified.append(item_res)

        time.sleep(0.1)

    # 績效統計計算
    total_sb = len(strong_buy_verified)
    wins = sum(1 for x in strong_buy_verified if x["is_win"])
    losses = sum(1 for x in strong_buy_verified if not x["is_win"] and x["return_pct"] < 0)
    win_rate = round((wins / total_sb) * 100, 1) if total_sb > 0 else 0.0
    avg_ret = round(sum(x["return_pct"] for x in strong_buy_verified) / total_sb, 2) if total_sb > 0 else 0.0

    best_stock = ""
    best_return = 0.0
    if strong_buy_verified:
        sorted_sb = sorted(strong_buy_verified, key=lambda x: x["return_pct"], reverse=True)
        best_stock = f"{sorted_sb[0]['stock_id']} {sorted_sb[0]['stock_name']}"
        best_return = sorted_sb[0]['return_pct']

    summary = {
        "record_id": rec_id,
        "analysis_datetime": analysis_dt,
        "verify_datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_verified": len(verified_results),
        "strong_buy_total": total_sb,
        "profitable_count": wins,
        "loss_count": losses,
        "win_rate": win_rate,
        "avg_return": avg_ret,
        "best_stock": best_stock,
        "best_return": best_return
    }

    print("\n" + "=" * 65)
    print("📊 【歷史回顧檢驗成果摘要】")
    print(f"   ✨ 強烈買進推薦標的：共 {total_sb} 檔")
    print(f"   🎯 獲利勝率 (Win Rate)：{win_rate}%  ({wins} 檔獲利 / {losses} 檔虧損)")
    print(f"   📈 推薦平均報酬率：{avg_ret:+.2f}%")
    if best_stock:
        print(f"   🏆 最佳獲利標的：{best_stock} ({best_return:+.2f}%)")
    print("=" * 65)

    # 產生檢驗 HTML 報告
    verify_html_name = f"verify_{rec_id}.html"
    verify_html_path = os.path.join(VERIFY_DIR, verify_html_name)
    render_verification_html(summary, verified_results, verify_html_path)

    # 更新回填原 CSV 試算表
    csv_rel = selected.get("csv_file")
    if csv_rel:
        update_csv_with_verification(os.path.join(HISTORY_DIR, csv_rel.replace("/", os.sep)), verified_results)

    return {
        "success": True,
        "summary": summary,
        "verify_report_url": f"/history/verifications/{verify_html_name}",
        "verify_report_path": verify_html_path
    }

def update_csv_with_verification(csv_path, verified_results):
    """將檢驗得到的最新價格與報酬率回寫至歷史 CSV"""
    if not os.path.exists(csv_path):
        return
    try:
        price_map = {x["stock_id"]: x for x in verified_results}
        rows = []
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows.append(headers)
            for r in reader:
                if len(r) >= 2:
                    sid = r[1].strip()
                    if sid in price_map:
                        v = price_map[sid]
                        # 補齊長度
                        while len(r) < 22:
                            r.append("")
                        r[18] = str(v["latest_price"])
                        r[19] = f"{v['return_pct']:+.2f}%"
                        r[20] = v["conclusion"]
                rows.append(r)

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    except Exception as e:
        print(f"⚠️ 更新 CSV 失敗: {e}")

def render_verification_html(summary, verified_results, output_path):
    """產生視覺化回測檢驗報告 HTML"""
    rows_html = []
    for v in verified_results:
        ret = v["return_pct"]
        ret_class = "color:#ef4444;" if ret > 0 else ("color:#10b981;" if ret < 0 else "color:#94a3b8;")
        diff_str = f"{ret:+.2f}%"
        biz = v.get("main_business") or "—"
        clean_biz = biz.replace('"', '&quot;')

        rows_html.append(f"""
        <tr>
            <td>
                <strong>{v['stock_name']}</strong>
                <div style="font-size:12px; color:#38bdf8; font-family:monospace;">{v['stock_id']} ({v['sector']})</div>
            </td>
            <td><div style="font-size:12px; color:#cbd5e1; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{clean_biz}">{biz}</div></td>
            <td><span style="font-weight:700;">{v['decision']}</span></td>
            <td><strong>{v['base_price']}</strong> 元</td>
            <td><strong>{v['latest_price']}</strong> 元</td>
            <td><strong style="{ret_class} font-size:15px;">{diff_str}</strong></td>
            <td><span style="font-weight:600;">{v['conclusion']}</span></td>
        </tr>
        """)

    body_rows = "".join(rows_html)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>🎯 歷史分析回測檢驗報告 - {summary['record_id']}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#f8fafc; padding:24px; line-height:1.5; }}
        .container {{ max-width:1300px; margin:0 auto; }}
        header {{ border-bottom:1px solid #334155; padding-bottom:16px; margin-bottom:24px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }}
        h1 {{ font-size:22px; font-weight:700; color:#fff; }}
        .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:14px; margin-bottom:24px; }}
        .stat-card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:16px 20px; }}
        .stat-title {{ font-size:13px; color:#94a3b8; }}
        .stat-val {{ font-size:26px; font-weight:800; margin-top:4px; }}
        .table-wrap {{ background:#1e293b; border:1px solid #334155; border-radius:12px; overflow-x:auto; }}
        table {{ width:100%; border-collapse:collapse; text-align:left; font-size:14px; }}
        th {{ background:#172033; color:#94a3b8; padding:12px 16px; border-bottom:1px solid #334155; }}
        td {{ padding:12px 16px; border-bottom:1px solid rgba(51,65,85,0.4); vertical-align:middle; }}
        tr:hover {{ background:#334155; }}
        .btn {{ padding:8px 16px; border-radius:8px; font-weight:700; text-decoration:none; display:inline-block; }}
        .btn-home {{ background:#38bdf8; color:#0f172a; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🎯 歷史分析回測檢驗成果報告</h1>
                <div style="color:#94a3b8; font-size:13px; margin-top:4px;">
                    歷史基準時間：{summary['analysis_datetime']} ➔ 最新比對時間：{summary['verify_datetime']}
                </div>
            </div>
            <div>
                <a href="../index.html" class="btn btn-home">📜 返回歷史總表</a>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-title">多因子強烈推薦標的</div>
                <div class="stat-val" style="color:#fbbf24;">{summary['strong_buy_total']} <span style="font-size:14px; color:#94a3b8;">檔</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-title">🎯 推薦獲利勝率 (Win Rate)</div>
                <div class="stat-val" style="color:#10b981;">{summary['win_rate']}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">📈 推薦平均累積漲幅</div>
                <div class="stat-val" style="color:{'#ef4444' if summary['avg_return']>=0 else '#10b981'};">{summary['avg_return']:+.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">🏆 最佳獲利標的</div>
                <div class="stat-val" style="color:#fbbf24; font-size:18px;">{summary['best_stock'] or '無'} ({summary['best_return']:+.2f}%)</div>
            </div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>標的名稱 / 代碼</th>
                        <th>主要營業項目</th>
                        <th>當時決策</th>
                        <th>當時價格</th>
                        <th>最新價格</th>
                        <th>累積漲跌幅</th>
                        <th>回顧檢驗結論</th>
                    </tr>
                </thead>
                <tbody>
                    {body_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"⚠️ 寫入檢驗 HTML 失敗: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="台股量化多因子選股歷史紀錄管理工具")
    parser.add_argument("--save", action="store_true", help="將當前快取封存為歷史紀錄")
    parser.add_argument("--auto-backup", action="store_true", help="run.bat 清空前的自動安全備份")
    parser.add_argument("--verify", type=str, nargs="?", const="latest", help="回顧檢驗歷史紀錄 (可指定 ID 或預設 latest)")
    parser.add_argument("--open", action="store_true", help="開啟歷史紀錄總覽頁面")
    args = parser.parse_args()

    if args.auto_backup:
        if os.path.exists(CACHE_FILE):
            archive_scan_results(tag="auto_backup", scan_scope="啟動前自動安全備份")
    elif args.save:
        res = archive_scan_results(tag="manual", scan_scope="量化手動封存")
        if res.get("success"):
            print("🎉 歷史紀錄封存完畢！")
        else:
            print(f"❌ 封存失敗: {res.get('error')}")
    elif args.verify is not None:
        target = None if args.verify == "latest" else args.verify
        verify_history(target)
    elif args.open:
        ensure_dirs()
        index_list = load_history_index()
        render_history_index_html(index_list)
        import webbrowser
        abs_index = os.path.abspath(INDEX_HTML_FILE)
        print(f"🌐 正在開啟歷史紀錄總表: file:///{abs_index.replace(os.sep, '/')}")
        webbrowser.open(abs_index)
    else:
        # 預設執行手動封存並顯示檢驗
        res = archive_scan_results(tag="manual", scan_scope="戰情室歷史封存")
        if res.get("success"):
            print("🎉 當前分析結果已成功封存！")
