# -*- coding: utf-8 -*-
"""
strategy_fundamentals.py
基本面漏斗篩選模組 - 全網路爬蟲架構 (免 FinMind API / 零連線上限限制)
數據源：Yahoo 奇摩股市 (月營收年月、YoY、單季 EPS) + yfinance 容錯備援
"""
import datetime
import requests
import bs4
import re

def scrape_yahoo_fundamentals(stock_id):
    """
    爬取 Yahoo 奇摩股市之最新營收年增率 (YoY) 與單季 EPS，作為高速無限制數據源
    """
    stock_id = str(stock_id).strip()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    info = {
        "revenue_yoy": None,
        "revenue_month": "",
        "eps": None,
        "eps_quarter": "",
        "is_fallback": False
    }

    # 1. 爬取最新月營收與年增率 (YoY)
    try:
        r_rev = requests.get(f"https://tw.stock.yahoo.com/quote/{stock_id}/revenue", headers=headers, timeout=6)
        if r_rev.status_code == 200:
            s_rev = bs4.BeautifulSoup(r_rev.text, 'html.parser')
            rows = [li for li in s_rev.find_all('li') if re.search(r'202\d/\d\d', li.text)]
            if rows:
                texts = [c.text.strip() for c in rows[0].find_all(['span', 'div']) if c.text.strip()]
                m = re.search(r'(202\d/\d\d)', texts[0])
                if m:
                    info['revenue_month'] = m.group(1)
                pcts = [x.replace('%', '').strip() for x in texts if x.strip().endswith('%') and len(x.strip()) <= 10]
                # pcts[0] 是 MoM(月增率), pcts[1] 是 YoY(年增率)
                if len(pcts) >= 2:
                    try:
                        info['revenue_yoy'] = float(pcts[1])
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️ Yahoo 營收爬蟲跳過: {e}")

    # 2. 爬取最新單季 EPS
    try:
        r_eps = requests.get(f"https://tw.stock.yahoo.com/quote/{stock_id}/eps", headers=headers, timeout=6)
        if r_eps.status_code == 200:
            s_eps = bs4.BeautifulSoup(r_eps.text, 'html.parser')
            rows = [li for li in s_eps.find_all('li') if re.search(r'202\d\s*Q\d', li.text)]
            if rows:
                texts = [c.text.strip() for c in rows[0].find_all(['span', 'div']) if c.text.strip()]
                m = re.search(r'(202\d\s*Q\d)', texts[0])
                if m:
                    info['eps_quarter'] = m.group(1)
                nums = [x for x in texts if re.match(r'^-?\d+(\.\d+)?$', x) and len(x) <= 8]
                if nums:
                    info['eps'] = float(nums[0])
    except Exception as e:
        print(f"⚠️ Yahoo EPS 爬蟲跳過: {e}")

    # 3. 若仍缺失，使用 yfinance 作為無限制容錯備援
    if info['eps'] is None or info['revenue_yoy'] is None:
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{stock_id}.TW")
            inf = ticker.info
            if not inf:
                ticker = yf.Ticker(f"{stock_id}.TWO")
                inf = ticker.info
            if info['eps'] is None and inf.get('trailingEps') is not None:
                info['eps'] = round(float(inf['trailingEps']), 2)
                info['eps_quarter'] = "近四季TTM"
            if info['revenue_yoy'] is None and inf.get('revenueGrowth') is not None:
                info['revenue_yoy'] = round(float(inf['revenueGrowth']) * 100, 2)
                info['revenue_month'] = "最新期"
        except Exception:
            pass

    return info

def check_fundamental_filters(stock_id, dl=None):
    """
    第一層漏斗：基本面精準掃描 (全爬蟲架構)
    1. 營收成長動能 (YoY >= 10%)
    2. 真實獲利能力 (最新單季 EPS > 0)
    回傳: (is_pass, reason_text, info_dict)
    """
    stock_id = str(stock_id).strip()
    info = scrape_yahoo_fundamentals(stock_id)

    # 綜合條件審查 (YoY >= 10% 且 EPS > 0)
    yoy_ok = (info["revenue_yoy"] is not None and info["revenue_yoy"] >= 10.0)
    eps_ok = (info["eps"] is not None and info["eps"] > 0)

    if yoy_ok and eps_ok:
        fallback_str = " (月初容錯評估)" if info["is_fallback"] else ""
        return True, f"✅ 營收 YoY {info['revenue_yoy']}% ({info['revenue_month']}) | 單季 EPS {info['eps']} 元{fallback_str}", info
    else:
        reasons = []
        if info["revenue_yoy"] is None:
            reasons.append("營收期數不足")
        elif not yoy_ok:
            reasons.append(f"營收動能不足(YoY: {info['revenue_yoy']}%)")

        if info["eps"] is None:
            reasons.append("EPS待公布")
        elif not eps_ok:
            reasons.append(f"未實現獲利(EPS: {info['eps']})")

        return False, " | ".join(reasons), info