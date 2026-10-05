import json
import datetime

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>台股量化多因子選股戰情室</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans TC', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            line-height: 1.5;
            padding: 24px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid #334155;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }
        h1 { font-size: 24px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
        .badge-live {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
        }
        .meta { color: #94a3b8; font-size: 13px; text-align: right; }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px 20px;
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; bottom: 0; width: 4px;
        }
        .stat-card.c-blue::before { background: #38bdf8; }
        .stat-card.c-gold::before { background: #fbbf24; }
        .stat-card.c-green::before { background: #10b981; }
        .stat-card.c-purple::before { background: #c084fc; }
        .stat-card.c-red::before { background: #ef4444; }
        .stat-title { font-size: 13px; color: #94a3b8; text-transform: uppercase; }
        .stat-val { font-size: 28px; font-weight: 800; margin-top: 4px; }

        .controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
        .tab-btn {
            background: #1e293b;
            border: 1px solid #334155;
            color: #94a3b8;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
        }
        .tab-btn:hover, .tab-btn.active {
            background: #38bdf8;
            color: #0f172a;
            border-color: #38bdf8;
        }
        .search-box {
            background: #1e293b;
            border: 1px solid #334155;
            padding: 8px 14px;
            border-radius: 8px;
            color: #f8fafc;
            font-size: 14px;
            outline: none;
            width: 260px;
        }
        .search-box:focus { border-color: #38bdf8; }

        .table-container {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 14px;
        }
        th {
            background: #172033;
            color: #94a3b8;
            font-weight: 600;
            padding: 14px 16px;
            border-bottom: 1px solid #334155;
            white-space: nowrap;
        }
        td {
            padding: 14px 16px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.4);
            vertical-align: middle;
        }
        tr:hover { background: #334155; }

        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            margin-right: 4px;
            margin-bottom: 2px;
        }
        .tag-buy { background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.4); }
        .tag-pass { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .tag-fail { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
        .tag-chip { background: rgba(192, 132, 252, 0.2); color: #c084fc; }
        .tag-neutral { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

        .stock-name { font-weight: 700; font-size: 15px; color: #fff; }
        .stock-id { color: #38bdf8; font-family: monospace; font-size: 13px; }
        .stock-sector { color: #94a3b8; font-size: 12px; margin-left: 6px; }
        .main-business-box {
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.45;
            max-width: 220px;
            min-width: 140px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
            word-break: break-word;
            cursor: default;
        }

        .signal-pill {
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 700;
            display: inline-block;
            white-space: nowrap;
        }
        .sig-buy { background: #fbbf24; color: #000; box-shadow: 0 0 12px rgba(251, 191, 36, 0.4); }
        .sig-hold { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
        .sig-sell { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .sig-wait { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

        .num-pos { color: #ef4444; font-weight: 600; }
        .num-neg { color: #10b981; font-weight: 600; }
        .num-neutral { color: #94a3b8; }

        footer {
            margin-top: 40px;
            text-align: center;
            color: #64748b;
            font-size: 12px;
            border-top: 1px solid #334155;
            padding-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🎯 台股量化多因子選股戰情室 <span class="badge-live">LIVE REPORT</span></h1>
                <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">
                    多因子漏斗：基本面營收EPS ✕ 布林帶寬壓縮突破 ✕ MACD柱狀圖翻正 ✕ 大戶吸籌與鉅額防守
                </div>
            </div>
            <div class="meta">
                <div>掃描母體：<strong>__SCAN_SCOPE__</strong></div>
                <div>更新時間：__NOW_STR__</div>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card c-blue">
                <div class="stat-title">掃描標的總數</div>
                <div class="stat-val">__TOTAL_COUNT__ <span style="font-size: 14px; font-weight: normal; color: #94a3b8;">檔</span></div>
            </div>
            <div class="stat-card c-gold">
                <div class="stat-title">✨ 多頭共振買點</div>
                <div class="stat-val" style="color: #fbbf24;">__STRONG_BUY_COUNT__ <span style="font-size: 14px; font-weight: normal;">檔</span></div>
            </div>
            <div class="stat-card c-green">
                <div class="stat-title">🏢 基本面合格 (YoY>10%, EPS>0)</div>
                <div class="stat-val" style="color: #10b981;">__FUND_PASS_COUNT__ <span style="font-size: 14px; font-weight: normal;">檔</span></div>
            </div>
            <div class="stat-card c-purple">
                <div class="stat-title">🔥 大戶連買/吸籌標的</div>
                <div class="stat-val" style="color: #c084fc;">__CHIP_BULL_COUNT__ <span style="font-size: 14px; font-weight: normal;">檔</span></div>
            </div>
            <div class="stat-card c-red">
                <div class="stat-title">🛑 風險警示 / 破線</div>
                <div class="stat-val" style="color: #ef4444;">__RISK_SELL_COUNT__ <span style="font-size: 14px; font-weight: normal;">檔</span></div>
            </div>
        </div>

        <div class="controls">
            <div class="tabs">
                <button class="tab-btn active" onclick="filterTab('all', this)">全部標的 (__TOTAL_COUNT__)</button>
                <button class="tab-btn" onclick="filterTab('strong_buy', this)">✨ 多因子推薦 (__STRONG_BUY_COUNT__)</button>
                <button class="tab-btn" onclick="filterTab('fund_pass', this)">🏢 基本面資優 (__FUND_PASS_COUNT__)</button>
                <button class="tab-btn" onclick="filterTab('chip_bull', this)">🐋 主力吸籌 (__CHIP_BULL_COUNT__)</button>
                <button class="tab-btn" onclick="filterTab('risk', this)">🛑 賣出警戒 (__RISK_SELL_COUNT__)</button>
            </div>
            <input type="text" id="searchInput" class="search-box" placeholder="🔍 搜尋股票代號、名稱、產業、營業項目..." onkeyup="searchTable()">
        </div>

        <div class="table-container">
            <table id="stocksTable">
                <thead>
                    <tr>
                        <th>標的名稱</th>
                        <th>主要營業項目</th>
                        <th>綜合決策</th>
                        <th>顏值</th>
                        <th>基本面 (營收 YoY / EPS)</th>
                        <th>技術面 (布林通道 ✕ MACD ✕ 均線)</th>
                        <th>籌碼面 (大戶多空 / 主力吸籌)</th>
                    </tr>
                </thead>
                <tbody id="tableBody">
__BODY_ROWS__
                </tbody>
            </table>
        </div>

        <footer>
            台股多因子量化模型 ✕ 採用 FinMind 即時金融數據庫 ✕ 僅供策略量化研究與參考，投資請審慎評估風險
        </footer>
    </div>

    <script>
        let currentFilter = 'all';

        function filterTab(filter, btn) {
            currentFilter = filter;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }

        function searchTable() {
            applyFilters();
        }

        function applyFilters() {
            const searchKeyword = document.getElementById('searchInput').value.trim().toLowerCase();
            const rows = document.querySelectorAll('.stock-row');

            rows.forEach(row => {
                const type = row.getAttribute('data-type');
                const chip = row.getAttribute('data-chip');
                const searchData = row.getAttribute('data-search').toLowerCase();

                let matchesTab = false;
                if (currentFilter === 'all') matchesTab = true;
                else if (currentFilter === 'strong_buy' && type === 'strong_buy') matchesTab = true;
                else if (currentFilter === 'fund_pass' && type === 'fund_pass') matchesTab = true;
                else if (currentFilter === 'chip_bull' && chip === 'chip_bull') matchesTab = true;
                else if (currentFilter === 'risk' && type === 'risk') matchesTab = true;

                let matchesSearch = (!searchKeyword || searchData.includes(searchKeyword));

                if (matchesTab && matchesSearch) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
"""

def generate_html_report(results, output_file="report.html", scan_scope="核心監控名單"):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    total_count = len(results)
    strong_buy_count = sum(1 for r in results if r.get("is_strong_buy"))
    fund_pass_count = sum(
        1 for r in results
        if r.get("fund_ok")
        and not r.get("is_strong_buy")
        and not r.get("tech", {}).get("is_sell")
    )
    chip_bull_count = sum(1 for r in results if r.get("chips", {}).get("is_accumulating") or r.get("chips", {}).get("trust_consecutive_buy"))
    risk_sell_count = sum(
        1 for r in results
        if r.get("tech", {}).get("is_sell")
        and not r.get("is_strong_buy")
    )

    rows_html = []
    for s in results:
        sid = s.get("stock_id", "")
        sname = s.get("stock_name", "")
        sector = s.get("sector", "")
        is_strong_buy = s.get("is_strong_buy", False)
        fund_ok = s.get("fund_ok", False)
        fund = s.get("fundamental", {})
        tech = s.get("tech", {})
        chips = s.get("chips", {})

        if is_strong_buy:
            sig_html = '<span class="signal-pill sig-buy">✨ 強烈買進</span>'
            row_type = "strong_buy"
        elif tech.get("is_sell"):
            sig_html = '<span class="signal-pill sig-sell">🛑 出場警戒</span>'
            row_type = "risk"
        elif fund_ok:
            sig_html = '<span class="signal-pill sig-hold">🟢 基本面優</span>'
            row_type = "fund_pass"
        else:
            sig_html = '<span class="signal-pill sig-wait">⚪ 觀察中</span>'
            row_type = "normal"

        chip_flag = "chip_bull" if (chips.get("is_accumulating") or chips.get("trust_consecutive_buy")) else ""

        beauty_score = tech.get("beauty_score")
        beauty_status = tech.get("beauty_status", "INSUFFICIENT_DATA")
        beauty_status_map = {
            "HIGH": "高顏值",
            "WATCHLIST": "觀察名單",
            "LOW": "弱勢",
            "INSUFFICIENT_DATA": "資料不足"
        }
        beauty_text = beauty_status_map.get(beauty_status, "待重掃")
        beauty_color = "#94a3b8"
        if beauty_score is not None:
            beauty_color = "#10b981" if beauty_score >= 80 else ("#38bdf8" if beauty_score >= 65 else "#ef4444")
        beauty_components = tech.get("beauty_components", {})
        beauty_detail = " / ".join(
            str(round(beauty_components.get(key, 0)))
            for key in ["trend", "stair_step", "high_52w", "drawdown", "momentum", "volatility"]
            if beauty_components.get(key) is not None
        )
        if beauty_score is None:
            beauty_cell = '''
                <div style="color: #94a3b8;">待重掃</div>
                <div style="color: #94a3b8; font-size: 11px;">新掃描後顯示</div>
            '''
        else:
            beauty_cell = f'''
                <div style="font-size: 22px; font-weight: 800; color: {beauty_color};">{beauty_score}</div>
                <div style="font-size: 11px; font-weight: 700; color: {beauty_color};">{beauty_text}</div>
                <div style="color: #94a3b8; font-size: 11px; margin-top: 3px;">{beauty_detail}</div>
            '''

        # 基本面
        yoy_val = fund.get("revenue_yoy")
        yoy_str = f"{yoy_val:+.2f}%" if yoy_val is not None else "N/A"
        yoy_class = "num-pos" if (yoy_val or 0) > 0 else "num-neg"
        eps_val = fund.get("eps")
        eps_str = f"{eps_val:.2f} 元" if eps_val is not None else "N/A"
        fund_tag = '<span class="tag tag-pass">合格</span>' if fund_ok else '<span class="tag tag-fail">淘汰</span>'
        fund_month = fund.get("revenue_month", "")
        fallback_tag = '<span class="tag tag-chip">月初容錯</span>' if fund.get("is_fallback") else ""

        fund_cell = f'''
            <div>{fund_tag}{fallback_tag}</div>
            <div style="margin-top:4px;">營收YoY: <span class="{yoy_class}">{yoy_str}</span> ({fund_month})</div>
            <div>單季EPS: <strong>{eps_str}</strong></div>
        '''

        # 技術面
        close_p = tech.get("close", "N/A")
        bw = tech.get("bb_bandwidth", 0)
        bw_tag = '<span class="tag tag-buy">帶寬壓縮</span>' if tech.get("is_bb_compressed") else ''
        bo_tag = '<span class="tag tag-buy">突破上軌</span>' if tech.get("is_bb_breakout") else ''
        macd_tag = '<span class="tag tag-pass">MACD翻正</span>' if tech.get("macd_turned_positive") else ('<span class="tag tag-pass">MACD紅柱</span>' if tech.get("macd_bullish") else '<span class="tag tag-fail">MACD綠柱</span>')
        trend_str = tech.get("trend_pattern", "")

        tech_cell = f'''
            <div><strong style="font-size: 15px;">收盤: {close_p}</strong> {bw_tag}{bo_tag}{macd_tag}</div>
            <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">布林帶寬: {bw}% | 支撐月線: {tech.get("sma20", "N/A")}</div>
            <div style="color: #e2e8f0; font-size: 12px;">{trend_str}</div>
        '''

        # 籌碼面
        f_net = chips.get("foreign_net_5d", 0)
        t_net = chips.get("trust_net_5d", 0)
        tot_net = chips.get("total_net_5d", 0)
        f_class = "num-pos" if f_net > 0 else ("num-neg" if f_net < 0 else "num-neutral")
        t_class = "num-pos" if t_net > 0 else ("num-neg" if t_net < 0 else "num-neutral")
        tot_class = "num-pos" if tot_net > 0 else ("num-neg" if tot_net < 0 else "num-neutral")

        chip_tags = "".join([f'<span class="tag tag-chip">{t}</span>' for t in chips.get("chip_signals", [])])
        block_str = f"<div style='color: #fbbf24; font-size: 12px;'>🐋 鉅額防守價: {chips.get('block_price')} 元</div>" if chips.get("block_price") else ""

        chips_cell = f'''
            <div>{chip_tags if chip_tags else '<span class="tag tag-neutral">籌碼溫和</span>'}</div>
            <div style="margin-top: 4px; font-size: 13px;">外資5日: <span class="{f_class}">{f_net:+.1f}張</span> | 投信5日: <span class="{t_class}">{t_net:+.1f}張</span></div>
            <div style="font-size: 13px;">三大法人合計: <span class="{tot_class}">{tot_net:+.1f}張</span></div>
            {block_str}
        '''

        main_biz = s.get("main_business") or "—"
        clean_biz = main_biz.replace('"', '&quot;')

        row_html = f'''
            <tr class="stock-row" data-type="{row_type}" data-chip="{chip_flag}" data-search="{sid} {sname} {sector} {main_biz}">
                <td>
            <div><span class="stock-name">{sname}</span> <span class="stock-sector">{sector}</span></div>
            <div class="stock-id">{sid}</div>
        </td>
        <td><div class="main-business-box" title="{clean_biz}">{main_biz}</div></td>
        <td>{sig_html}</td>
        <td>{beauty_cell}</td>
        <td>{fund_cell}</td>
                <td>{tech_cell}</td>
                <td>{chips_cell}</td>
            </tr>
        '''
        rows_html.append(row_html)

    body_rows = "\n".join(rows_html)

    rendered = HTML_TEMPLATE.replace("__SCAN_SCOPE__", scan_scope)\
                            .replace("__NOW_STR__", now_str)\
                            .replace("__TOTAL_COUNT__", str(total_count))\
                            .replace("__STRONG_BUY_COUNT__", str(strong_buy_count))\
                            .replace("__FUND_PASS_COUNT__", str(fund_pass_count))\
                            .replace("__CHIP_BULL_COUNT__", str(chip_bull_count))\
                            .replace("__RISK_SELL_COUNT__", str(risk_sell_count))\
                            .replace("__BODY_ROWS__", body_rows)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"✅ 視覺化戰情室報告已儲存至: {output_file}")
