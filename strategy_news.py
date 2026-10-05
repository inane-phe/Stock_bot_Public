# -*- coding: utf-8 -*-
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import datetime

# 正向與負向題材關鍵字庫
POSITIVE_KEYWORDS = [
    '創高', '大增', '暴衝', '成長', '擴產', '滿載', '漲停', '買超',
    '法說報喜', '調升', '翻倍', '大單', '進補', '躍進', '優於預期',
    '火熱', '利多', '突破', '轉盈', '看旺', '擴大資本支出', 'AI商機'
]

NEGATIVE_KEYWORDS = [
    '衰退', '暴跌', '跌停', '虧損', '賣超', '下修', '調降', '延遲',
    '警訊', '違約', '低於預期', '砍單', '保守', '重挫', '利空', '破底',
    '裁員', '侵權', '轉虧', '存貨跌價'
]

def fetch_stock_news(stock_id, stock_name, max_items=5):
    """
    爬取 Google News RSS 即時個股新聞並進行情緒分析
    回傳: {
        'sentiment_score': int,
        'sentiment_label': str,
        'news_list': list of dict,
        'positive_hits': list,
        'negative_hits': list
    }
    """
    result = {
        'sentiment_score': 0,
        'sentiment_label': '⚪ 題材平穩',
        'news_list': [],
        'positive_hits': [],
        'negative_hits': []
    }

    try:
        # 搜尋關鍵字：如 "2330 台積電"
        query_str = f"{stock_id} {stock_name}".strip()
        encoded_query = urllib.parse.quote(query_str)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

        req = urllib.request.Request(
            rss_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )

        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall('./channel/item')[:max_items]

        pos_count = 0
        neg_count = 0

        for item in items:
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            source = item.find('source').text if item.find('source') is not None else "財經新聞"

            # 清理時間字串
            if pub_date and len(pub_date) > 16:
                pub_date = pub_date[:16]

            # 關鍵字情緒分析
            matched_pos = [k for k in POSITIVE_KEYWORDS if k in title]
            matched_neg = [k for k in NEGATIVE_KEYWORDS if k in title]

            pos_count += len(matched_pos)
            neg_count += len(matched_neg)
            result['positive_hits'].extend(matched_pos)
            result['negative_hits'].extend(matched_neg)

            result['news_list'].append({
                'title': title,
                'link': link,
                'source': source,
                'date': pub_date
            })

        # 去重關鍵字
        result['positive_hits'] = list(set(result['positive_hits']))
        result['negative_hits'] = list(set(result['negative_hits']))

        # 評定多空情緒標籤
        score = pos_count - neg_count
        result['sentiment_score'] = score

        if score >= 2 or (pos_count > 0 and neg_count == 0):
            result['sentiment_label'] = '🔥 題材偏多'
        elif score <= -2 or (neg_count > 0 and pos_count == 0):
            result['sentiment_label'] = '⚠️ 題材偏空'
        else:
            result['sentiment_label'] = '⚪ 題材平穩'

    except Exception as e:
        result['sentiment_label'] = f'新聞連線受限'

    return result

if __name__ == '__main__':
    res = fetch_stock_news('2330', '台積電')
    print('情緒:', res['sentiment_label'])
    for n in res['news_list']:
        print(f"- [{n['source']}] {n['title']}")