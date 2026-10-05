# -*- coding: utf-8 -*-
"""
strategy_chips.py
籌碼分析引擎 - 全網路爬蟲架構 (免 FinMind API / 零連線上限限制)
數據源：Yahoo 奇摩股市法人逐日買賣超 (外資、投信、自營商買賣張數、連續買賣超、外資持股比)
"""
import pandas as pd
import datetime
import requests
import bs4
import re

class ChipsEngine:
    def __init__(self, token=None):
        # 免 Token，完全以高速網路爬蟲驅動
        pass

    def scrape_yahoo_chips(self, stock_id, allow_recheck=True):
        """
        爬取 Yahoo 奇摩股市法人逐日買賣超 (高穩定結構化子節點解析 + 缺漏自動複檢)
        """
        stock_id = str(stock_id).strip()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        result = {
            "foreign_net_5d": 0,
            "trust_net_5d": 0,
            "dealer_net_5d": 0,
            "total_net_5d": 0,
            "trust_consecutive_buy": False,
            "foreign_status": "中性",
            "trust_status": "中性",
            "accumulation_ratio": 1.0,
            "is_accumulating": False,
            "block_price": None,
            "block_shares": 0,
            "chip_signals": [],
            "status_summary": "籌碼面溫和中性",
            "is_rechecked": False
        }

        def parse_clean_num(val):
            if not val:
                return 0.0
            s = str(val).replace(',', '').replace('%', '').strip()
            if s in ['--', '-', 'N/A', '']:
                return 0.0
            try:
                return float(s)
            except Exception:
                return 0.0

        def parse_soup(soup):
            parsed = []
            for li in soup.find_all('li'):
                # 策略 1: 優先抓取 Yahoo 官方 table-row 容器之直接子節點 (精準 8 欄對齊)
                table_row = li.find('div', class_='table-row')
                cols = table_row.find_all('div', recursive=False) if table_row else []
                if len(cols) >= 5:
                    d_str = cols[0].text.strip()
                    dm = re.search(r'(202\d/\d\d/\d\d)', d_str)
                    if dm:
                        parsed.append({
                            'date': dm.group(1),
                            'foreign': parse_clean_num(cols[1].text),
                            'trust': parse_clean_num(cols[2].text),
                            'dealer': parse_clean_num(cols[3].text),
                            'total': parse_clean_num(cols[4].text)
                        })
                        continue

                # 策略 2: 備援直接子節點掃描
                text_all = li.text
                if '202' in text_all:
                    dm = re.search(r'(202\d/\d\d/\d\d)', text_all)
                    if dm:
                        cell_divs = [c for c in li.find_all('div') if c.find('div') is None and c.text.strip()]
                        if len(cell_divs) >= 5:
                            nums = []
                            for cd in cell_divs[1:6]:
                                t = cd.text.strip()
                                if '%' not in t:
                                    nums.append(parse_clean_num(t))
                            if len(nums) >= 4:
                                parsed.append({
                                    'date': dm.group(1),
                                    'foreign': nums[0],
                                    'trust': nums[1],
                                    'dealer': nums[2],
                                    'total': nums[3] if len(nums) > 3 else (nums[0] + nums[1] + nums[2])
                                })
            return parsed

        # 1. 首次嘗試主網址
        urls_to_try = [f"https://tw.stock.yahoo.com/quote/{stock_id}/institutional-trading"]
        if allow_recheck:
            urls_to_try.extend([
                f"https://tw.stock.yahoo.com/quote/{stock_id}.TWO/institutional-trading",
                f"https://tw.stock.yahoo.com/quote/{stock_id}.TW/institutional-trading"
            ])

        parsed_days = []
        for try_idx, url in enumerate(urls_to_try):
            try:
                r = requests.get(url, headers=headers, timeout=6)
                if r.status_code == 200:
                    soup = bs4.BeautifulSoup(r.text, 'html.parser')
                    parsed_days = parse_soup(soup)
                    if parsed_days:
                        if try_idx > 0:
                            result["is_rechecked"] = True
                        break
            except Exception as e:
                pass

        if parsed_days:
            five_days = parsed_days[:5]
            f_net = round(sum(d['foreign'] for d in five_days), 1)
            t_net = round(sum(d['trust'] for d in five_days), 1)
            d_net = round(sum(d['dealer'] for d in five_days), 1)
            tot_net = round(sum(d['total'] for d in five_days), 1)

            result["foreign_net_5d"] = f_net
            result["trust_net_5d"] = t_net
            result["dealer_net_5d"] = d_net
            result["total_net_5d"] = tot_net

            # 投信連買判斷 (最近 2 個交易日皆買超)
            if len(five_days) >= 2 and all(d['trust'] > 0 for d in five_days[:2]):
                result["trust_consecutive_buy"] = True
                result["chip_signals"].append("🟢 投信連買作帳吸籌中")

            # 外資動態
            if f_net > 500:
                result["foreign_status"] = "大幅加碼"
                result["chip_signals"].append(f"🟢 外資5日加碼 {f_net} 張")
            elif f_net < -500:
                result["foreign_status"] = "調節賣超"
                result["chip_signals"].append(f"🔴 外資5日調節 {f_net} 張")

            # 投信動態
            if t_net > 100:
                result["trust_status"] = "加碼進駐"
                result["chip_signals"].append(f"🟢 投信5日買超 {t_net} 張")

            # 主力法人連續吸籌判斷
            pos_days = sum(1 for d in five_days if d['total'] > 0)
            if pos_days >= 3 and tot_net > 200:
                result["is_accumulating"] = True
                result["chip_signals"].append(f"🔥 法人連續加碼 (5日累計淨買 {tot_net} 張)")

            # 狀態總結
            if result["trust_consecutive_buy"] or result["is_accumulating"] or (tot_net > 500):
                result["status_summary"] = "🔥 大戶籌碼集中偏多"
            elif tot_net < -500:
                result["status_summary"] = "⚠️ 大戶調節偏空"
            else:
                result["status_summary"] = "⚪ 籌碼面溫和中性"

        return result

    def analyze_chips(self, stock_id, days=5, allow_recheck=True):
        """
        執行籌碼面分析 (支援缺漏自動複檢)
        """
        return self.scrape_yahoo_chips(stock_id, allow_recheck=allow_recheck)

    def get_broker_trading(self, stock_id, target_date=None):
        """相容舊介面"""
        analysis = self.analyze_chips(stock_id)
        report = {
            "外資5日累計": f"{analysis['foreign_net_5d']:+.1f} 張",
            "投信5日累計": f"{analysis['trust_net_5d']:+.1f} 張",
            "自營5日累計": f"{analysis['dealer_net_5d']:+.1f} 張",
            "三大法人合計": f"{analysis['total_net_5d']:+.1f} 張"
        }
        return pd.Series(report)