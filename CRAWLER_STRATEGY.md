# 爬蟲策略評估與決策

## 結論

**保留現有 requests / BeautifulSoup / OpenAPI / RSS / yfinance 架構作為主要爬蟲路徑；不將 crawl4ai 導入主流程，也不加入 requirements.txt。**

本機檢查到的 crawl4ai 版本為 `0.9.4`。它的主要入口 `AsyncWebCrawler` 預設使用 `AsyncPlaywrightCrawlerStrategy`，也就是瀏覽器式擷取。這對動態網頁有幫助，但不符合本專案以台股官方 OpenAPI、RSS、yfinance 和少量固定 Yahoo 頁面為主的批次掃描需求。

## 評估範圍

本專案目前的爬取來源如下：

| 來源 | 目前做法 | 資料性質 |
|---|---|---|
| TWSE OpenAPI | `app.py` 使用 `requests` + JSON | 結構化官方資料 |
| TPEx OpenAPI | `app.py` 使用 `requests` + JSON | 結構化官方資料 |
| Yahoo 奇摩股市 | `strategy_fundamentals.py`、`strategy_chips.py` 使用 `requests` + BeautifulSoup | 半結構化 HTML |
| Google News RSS | `strategy_news.py` 使用 `urllib` + XML parser | 結構化 RSS |
| yfinance | `strategy_indicators.py` 與各備援路徑 | 結構化歷史 K 線 |

Web 批次掃描由 `app.py` 的 `ThreadPoolExecutor(max_workers=4)` 控制，單一請求 timeout 約 4 至 6 秒。這個設計適合台股上市櫃母體掃描，也讓單一股票失敗時不會阻斷整批結果。

## 本機 crawl4ai 檢查結果

以下結論以 `C:\Users\ls990\Documents\github tool\crawl4ai` 的原始碼為準：

1. `crawl4ai/__version__.py` 顯示版本為 `0.9.4`。
2. `crawl4ai/async_webcrawler.py` 的 `AsyncWebCrawler` 預設建立 `AsyncPlaywrightCrawlerStrategy`。
3. `crawl4ai/async_crawler_strategy.py` 定義 Playwright 瀏覽器生命周期、page/context、session、等待條件與擷取流程。
4. `pyproject.toml` 依賴包含 `playwright`、`patchright`、`aiohttp`、`httpx`、`litellm`、`nltk`、`shapely` 等大量套件；`requirements.txt` 也包含瀏覽器相關依賴。
5. `AsyncWebCrawler.arun_many()` 提供批量 URL 排程，並可搭配 dispatcher、rate limiter 與 semaphore，但底層仍是瀏覽器或重型 HTTP pipeline。

## 比較

| 面向 | 現有架構 | crawl4ai 0.9.4 |
|---|---|---|
| 執行成本 | 低；輕量 HTTP 請求與 SDK 呼叫 | 高；預設 Playwright / patchright 瀏覽器策略 |
| 適合資料 | JSON、RSS、yfinance、固定 HTML | 動態網頁、需要清稿或 AI 摘要的長文 |
| 欄位精度 | 可針對台股月營收、EPS、法人張數寫穩定 parser | 偏向文字 / Markdown 擷取，數值欄位需二次驗證 |
| 批次掃描 | 4 workers 的輕量併發適合上千檔台股 | 有 `arun_many()` 與 dispatcher，但瀏覽器啟動、記憶體與頁面回收成本較高 |
| 部署需求 | 目前 `requirements.txt` 已足夠 | 需要安裝 crawl4ai 與瀏覽器相依，部署體積和啟動時間增加 |
| 失效排除 | 哪個 URL、selector、欄位失敗較容易定位 | 抽取規則包在 crawler 設定或 AI pipeline 較深 |
| 反爬處理 | 較保守，多數來源是官方 OpenAPI / RSS | 瀏覽器指紋、等待、session、stealth 能力較強 |
| 台股適配 | 已依 `.TW` / `.TWO`、法人張數、中文新聞調整 | 通用 crawler 仍需要自訂 schema 或 extractor 才能保證台股欄位 |

## 工程判斷

對 TWSE / TPEx OpenAPI、Google News RSS 和 yfinance 來說，直接使用現有輕量路徑明顯較優。這些來源已經是結構化資料；改用 crawl4ai 只會把 JSON、XML 或 SDK 資料再包進瀏覽器流程，增加延遲、記憶體和維運成本，卻沒有提高資料精度。

Yahoo 頁面是現有架構中相對脆弱的部分，因為 selector 可能隨前端更新失效。但 crawl4ai 的解法是渲染整頁再抽取，適合作為單一資料源備援，不適合作為所有台股資料的主路徑。對本專案而言，精確的 `revenue_yoy`、`eps`、法人買賣超張數和五日加總，比取得整頁 Markdown 更重要。

## 執行驗證限制

這次未執行同一批台股 URL 的 live benchmark。原因是專案環境未安裝 `crawl4ai`，且受沙箱限制無法穩定啟動本機 crawl4ai venv 與系統 Python。因此本文件採用原始碼、依賴宣告與現有工作負載做架構比較。

若之後要補實測，建議只取 20 到 50 檔相同標的，分別記錄：

1. 成功率。
2. 關鍵欄位完整率：營收 YoY、EPS、法人五日買賣超、最新收盤價。
3. 總耗時與平均單檔耗時。
4. CPU / RSS 記憶體峰值。
5. parser 欄位錯誤數。
6. 重試與備援觸發次數。

## 決策理由

1. 專案要批次掃描上千檔台股，輕量 HTTP 請求比瀏覽器式 crawler 更適合。
2. 核心資料大多已有 JSON、RSS 或 SDK，不需要 AI 式網頁理解。
3. 基本面與籌碼面欄位必須保留精確數值，客製 parser 比 AI 抽取更可控。
4. 本機 crawl4ai `0.9.4` 的依賴與瀏覽器架構會明顯增加安裝、啟動與部署負擔。
5. `requirements.txt` 目前只有 Flask、pandas、pandas_ta、yfinance、beautifulsoup4、requests、gunicorn；維持精簡依賴比較容易部署。

## 後續使用原則

只有在下列情境才考慮 crawl4ai：

1. 某個資料源改為高度動態渲染，且找不到公開 API。
2. 需要擷取長篇公告、法說會逐字稿或非固定格式文件。
3. 現有 Yahoo parser 已持續失效，且無其他官方 OpenAPI 可替代。

屆時應作為單一資料源的 fallback，而不是取代全部爬蟲。建議使用獨立的 optional requirements 或 feature flag，並確保關閉 flag 時主程式仍可掃描。

## 不導入 crawl4ai 但可借用的工程能力

1. 共用 `requests.Session`，減少重複連線成本。
2. 對暫時性 HTTP 錯誤加入有限次數 retry 與 backoff。
3. 批次掃描保留明確 rate limiting，避免對 Yahoo 或官方 API 造成壓力。
4. 每個資料源記錄成功、缺漏、備援與 parser 失敗狀態。
5. 移除不必要的 `verify=False`，改為正確處理 TLS 驗證。

## 最終保留範圍

保留：

- TWSE / TPEx OpenAPI 直連。
- Yahoo HTML 的精準欄位 parser。
- Google News RSS。
- yfinance `.TW` / `.TWO` K 線與備援。
- 目前 4 workers 的批次節奏。

不保留：

- crawl4ai 作為主爬蟲。
- crawl4ai 相關依賴進入主 requirements。
- 以瀏覽器渲染取得原本已有官方 JSON 的資料。

所有爬蟲仍必須保留 timeout、User-Agent、缺漏複檢、欄位型別驗證與請求頻率控制。
