# 台股顏值投資法股票判斷引擎 — Agent 專案實作計畫

> 文件用途：提供 Agent 在完善既有台股量化專案時使用的工程規格與判斷條件，使系統能對台灣上市櫃個股與 ETF 執行「顏值投資法」分析，並產生「是否符合策略購入條件」的結構化判斷。
>
> 重要定位：本模組是規則式投資研究與篩選引擎，不是保證獲利、預測股價或自動下單系統。任何「值得購入」結果都必須表述為「符合本策略條件」，不得表述為必然上漲或必然成為十倍股。

## 1. 專案目標

在既有台股多因子選股專案中加入可被 Agent 呼叫的：

```text
Beauty Investment Analyzer
```

輸入台股代號與歷史市場資料後，完成：

1. 資料完整性與除權息調整檢查。
2. 價格曲線「顏值」分析。
3. 碎步上漲與趨勢延續分析。
4. 52 週高點距離與突破分析。
5. 回撤品質、波動與價格結構分析。
6. 動能持續性與撈底後重新轉強分析。
7. 台股交易制度與流動性風險檢查。
8. 整合既有專案的基本面、技術面、籌碼面與新聞面判斷。
9. 產生 `QUALIFIED`、`WATCHLIST`、`NOT_QUALIFIED`、`INSUFFICIENT_DATA`。
10. 產生 Agent 可讀 JSON 與人類可讀報告。

本系統不回答「一定會漲嗎」，只回答：

> 「這檔台股目前是否符合顏值與多因子共振條件？」

## 2. 台股標的與代號規格

### 2.1 支援範圍

優先支援：

| 資產類型 | 台股代號範例 | 資料後綴 | 判斷模組 |
|---|---:|---|---|
| 上市股票 | `2330` | `.TW` | 價格、基本面、籌碼、新聞 |
| 上櫃股票 | `3443` | `.TWO` | 價格、基本面、籌碼、新聞 |
| 台股 ETF | `0050` | `.TW` | 價格、流動性；基本面與法人買超僅輔助 |

標準化輸入規則：

1. 支援純四位數代號、`2330.TW`、`2330.TWO` 與繁體中文簡稱。
2. 輸入一律轉換成內部 `stock_id`，例如 `3008`。
3. 對外顯示時保留台股名稱、上市／上櫃別與資料日期。
4. 上櫃股票應先嘗試 `.TWO`，上市股票應先嘗試 `.TW`；無法確認市場時依現有專案邏輯雙向容錯。
5. 興櫃、權證、特別股、可轉債不納入第一版顏值分析，除非另行建立風控參數。

### 2.2 資料來源

沿用既有專案架構：

```text
TWSE OpenAPI          上市股票基本資料
TPEx OpenAPI          上櫃股票基本資料
yfinance .TW/.TWO     日 K 線與調整後價格
Yahoo 奇摩股市         月營收、EPS、三大法人買賣超
Google News RSS       繁體中文新聞情緒
```

新增資料欄位時不得破壞既有 API 結果。

## 3. 台股資料規格與清理

### 3.1 最低必要資料

日線至少需要：

```text
date
open
high
low
close
volume
turnover_ntd
```

若資料源沒有 `turnover_ntd`，可用下列方式估算：

```text
turnover_ntd = sum(close * volume)
```

台股普通股普通交易的一張為 1,000 股。程式內部若使用股數，必須明確命名 `volume_shares`；若使用台股慣用張數，必須明確命名 `volume_lots`。

台股一個交易日曆年約 240 至 250 個交易日。第一版統一使用：

```text
year_window = 240
minimum_trading_days = 240
preferred_history_days = 720
```

少於 240 個有效交易日時：

```text
status = INSUFFICIENT_DATA
```

不得用不完整資料假裝完成 52 週分析。

### 3.2 除權息與拆股調整

台股現金股利、股票股利與減資會造成原始價格跳空。長期報酬、趨勢、回撤與 52 週高點必須使用調整後價格：

```text
adjusted_close
adjusted_open
adjusted_high
adjusted_low
```

若使用 yfinance，應明確要求自動調整價格，或在資料層自行計算 adjustment factor。不得將除息缺口誤判成崩跌，也不得將還原後的歷史高點誤判成當時可成交價。

輸出報告必須標註：

```text
price_basis = adjusted_close
adjustment_source = yfinance / custom / unknown
```

### 3.3 資料品質檢查

必須檢查：

1. 日期排序與重複日期。
2. 缺失值、零值或負值。
3. 成交量與成交金額是否可對齊。
4. 長時間停止交易或資料缺漏。
5. 除權息、拆股、減資造成的異常跳空。
6. 台股漲跌停造成的上下影線壓縮。
7. 新上市股票歷史長度不足。
8. 上市轉上櫃、更名、代號變更造成的資料拼接問題。

品質不足時：

```text
data_quality.status = FAILED
```

禁止直接產生策略合格結果。

## 4. 台股交易制度風控

### 4.1 漲跌停判斷

台股普通股單日漲跌幅限制為前一日收盤價上下 10%。系統應產生：

```text
is_limit_up
is_limit_down
limit_up_pressure
limit_down_risk
```

建議初始判斷：

```text
daily_return >= +0.097  → is_limit_up = true
daily_return <= -0.097  → is_limit_down = true
```

注意：漲停日可能無法買進，跌停日可能無法賣出。突破訊號發生在漲停時，只能標記為 `WATCHLIST` 或加註流動性風險，不得自動視為可立即購入。

### 4.2 流動性門檻

使用 20 日平均成交金額，而不是只用成交股數：

```text
avg_turnover_20d
```

建議初始規則：

```yaml
liquidity:
  minimum_avg_turnover_20d_ntd: 50000000
  minimum_price: 5
  reject_sub_lot_only_volume: true
```

低於門檻時加入：

```text
LOW_LIQUIDITY
```

並將 `risk_block` 設為 `true`。

### 4.3 台股公布時程容錯

台股月營收多數於每月 10 日前公布，財報則有法定申報時程。基本面判斷必須保留 `data_period` 與公布日期邏輯：

1. 每月 10 日前最新月營收缺失時，先使用上一期 YoY 評估，並標記 `is_fallback = true`。
2. 每月 10 日後仍缺最新月營收，標記 `REVENUE_MISSING`。
3. 季 EPS 在申報期限前未更新時，允許使用上一季 EPS，但必須標記期別。
4. 不得把「尚未公布」直接等同於「基本面失敗」，也不得在沒有期別資訊時假裝它是最新資料。

## 5. 既有專案判斷條件

本節是顏值分數以外的專案共振條件，必須保留在可設定檔中。

### 5.1 基本面條件

沿用現有 `strategy_fundamentals.py`：

```text
latest_monthly_revenue_yoy >= 10%
AND
latest_quarterly_eps > 0
```

輸出至少包含：

```json
{
  "revenue_yoy": 12.3,
  "revenue_month": "2026-08",
  "eps": 2.45,
  "eps_quarter": "2026 Q2",
  "is_fallback": false,
  "fund_pass": true
}
```

例外處理：

| 情境 | 處理 |
|---|---|
| 月營收缺失但未過 10 日 | 使用上一期並標記 fallback |
| 最新季 EPS 未公布 | 可使用上一季，標記期別 |
| ETF 或債券型 ETF | `fund_pass = NOT_APPLICABLE`，不阻擋價格結構評分 |
| 金融控股、原物料、航運等週期股 | 仍可計算，但報告必須提示景氣循環風險 |

### 5.2 技術面條件

沿用現有 `strategy_indicators.py`：

```text
布林通道(20, 2)
MACD(12, 26, 9)
SMA5
SMA20
SMA60
RSI14
```

買進條件：

```text
bb_bandwidth <= 12%
AND/OR
close >= 0.985 * BBU20
AND
(MACD histogram 翻正 OR MACD histogram > 0 且持續擴張)
AND
close >= SMA20
```

工程公式：

```text
is_bb_compressed = bandwidth <= 0.12
is_bb_breakout   = close >= upper_band * 0.985
is_macd_turn_positive = hist_prev <= 0 AND hist_now > 0
is_macd_bullish_expanding = hist_now > 0 AND hist_now > hist_prev

tech_is_buy =
    (is_macd_turn_positive
     OR (is_macd_bullish_expanding AND is_bb_breakout))
  AND
    close >= SMA20
```

賣出警訊：

```text
MACD histogram 由正轉負
OR
close < SMA20
```

加強顯示但不單獨作為買進條件：

```text
close > SMA5 > SMA20 > SMA60
```

### 5.3 籌碼面條件

沿用現有 `strategy_chips.py`，資料以台股法人買賣超「張」為單位：

```text
foreign_net_5d
trust_net_5d
dealer_net_5d
total_net_5d
trust_consecutive_buy
is_accumulating
```

初始規則：

```text
外資 5 日淨買超 > 500 張      → foreign_accumulating
外資 5 日淨賣超 < -500 張     → foreign_distributing
投信 5 日淨買超 > 100 張      → trust_accumulating
投信最近 2 日皆買超           → trust_consecutive_buy
最近 5 日中至少 3 日三大法人合計買超
AND
三大法人 5 日合計淨買超 > 200 張
                             → is_accumulating
```

專案層的籌碼偏多定義：

```text
chip_favorable =
    is_accumulating
 OR trust_consecutive_buy
 OR total_net_5d > 0
```

若三大法人資料全部為 0，必須先視為缺漏並複檢。複檢後仍為 0，才標記 `CHIP_DATA_NOT_AVAILABLE`；不得自動視為買超。

### 5.4 新聞情緒條件

沿用現有 `strategy_news.py`：

1. 使用台股代號與繁體中文簡稱搜尋 Google News RSS。
2. 最多取 5 筆最新標題。
3. 使用既有中文多空關鍵字計算 `sentiment_score = positive_hits - negative_hits`。
4. 輸出偏多、偏空、平穩或資料受限。

專案層只要求：

```text
news_not_bearish = sentiment_score >= -1
```

新聞偏空不必然否決顏值分數，但會阻止最高層級的 `QUALIFIED`。重大事件關鍵字如違約、下市、財報重編、主管機關處分，應額外加入 `news_risk_flag`。

### 5.5 既有專案共振買點

Web 版 `app.py` 目前使用四層共振：

```text
fund_pass
AND tech_is_buy
AND chip_favorable
AND news_not_bearish
→ is_strong_buy = true
```

離線 `main.py` 目前缺少新聞層。之後整合時，兩個入口應共用同一個 decision engine，避免 Web 版與離線版結果不一致。

## 6. 顏值價格結構評分

顏值分數只衡量價格行為，範圍為 0 到 100。

```text
beauty_score = 0 ~ 100
```

建議初始權重：

| 模組 | 權重 |
|---|---:|
| 趨勢一致性 | 25 |
| 碎步上漲 | 20 |
| 52 週高點結構 | 20 |
| 回撤品質 | 15 |
| 動能 | 15 |
| 波動品質 | 5 |
| 合計 | 100 |

所有權重與門檻必須放在設定檔，不得硬編碼。

### 6.1 週期定義

台股版建議週期：

```yaml
periods:
  short: 20
  medium: 60
  long: 120
  year: 240
```

計算：

```text
return_20d
return_60d
return_120d
return_240d

SMA20
SMA60
SMA120
SMA240
```

既有技術面仍可保留 `SMA5`，但顏值趨勢判斷應以 20 / 60 / 120 / 240 為主，避免直接沿用美股 50 / 100 / 200 日造成語意混淆。

### 6.2 趨勢一致性

建議條件：

```text
close > SMA20
SMA20 > SMA60
SMA60 > SMA120
return_240d > 0
```

每成立一項可得 6.25 分，最高 25 分。

最低趨勢確認條件：

```text
trend_confirmed =
    close > SMA20
  AND SMA20 > SMA60
  AND return_120d > 0
```

### 6.3 碎步上漲

碎步上漲不能只用「最近一年漲很多」代替，必須分析：

1. Higher High。
2. Higher Low。
3. 回撤幅度。
4. 回撤時間。
5. 趨勢恢復速度。

使用 swing point 或 ZigZag 建立有效波峰與波谷：

```text
HH_ratio = valid_higher_highs / total_swing_highs
HL_ratio = valid_higher_lows / total_swing_lows

stair_step_raw =
    HH_ratio * 40
  + HL_ratio * 40
  + recovery_score * 20
```

最後 normalize 到 0 至 20 分。

台股漲跌停會讓部分漲勢集中在漲停日。Swing 偵測應使用收盤價或調整後收盤價，不得只用盤中最高價，否則容易被漲停尖峰誤導。

### 6.4 回撤品質

計算：

```text
MDD_20
MDD_60
MDD_120
MDD_240
recovery_days
```

健康回撤：

```text
上漲 → 小幅回撤 → 未破壞主要趨勢 → 重新上漲
```

趨勢破壞：

```text
深度回撤 → 跌破 SMA20 / SMA60 → 反彈失敗 → Lower High
```

回撤較小且恢復較快者提高分數。

### 6.5 52 週高點與突破

台股一年視窗使用 240 個交易日。為避免未來資料污染，必須使用前一日的滾動高點：

```python
previous_240d_high = close.shift(1).rolling(240).max()
distance_to_high = (close - previous_240d_high) / previous_240d_high
breakout = close > previous_240d_high
```

分級：

```text
distance_to_high >= -5%       → NEAR_HIGH
close >= previous_240d_high   → AT_HIGH
breakout確認成功              → BREAKOUT
```

突破確認：

```yaml
breakout:
  confirmation_days: 2
  turnover_ratio_to_20d_avg: 1.0
```

假突破：

```text
close > previous_240d_high
但 2 日內收盤跌回 previous_240d_high 之下
→ breakout_confirmed = false
```

突破當日若漲停且買不到合理成交量，只標記訊號，不得直接判定為可購入。

### 6.6 動能與波動

動能使用多週期，不依賴單一報酬：

```text
momentum_score =
    normalize(return_20d)  * 0.20
  + normalize(return_60d)  * 0.30
  + normalize(return_120d) * 0.30
  + normalize(return_240d) * 0.20
```

必須設定合理上下限，避免週期股或漲停連續行情壓垮分數。

波動品質計算：

```text
ATR%
realized_volatility_20d
downside_volatility_20d
```

台股單日漲跌幅上限為 10%，歷史波動閾值必須依台股重新校準，不得直接套用美股波動參數。

### 6.7 撈底後轉強

可識別模式：

```text
大幅回撤
→ 形成低點
→ Higher Low
→ 突破短期下降壓力
→ 重新站上 SMA20 / SMA60
→ MACD 或動能恢復
```

成立時：

```text
recovery_pattern = true
```

此類標的優先進入 `WATCHLIST`，不應直接視為已處於長期高顏值突破階段。

## 7. 風險排除條件

即使 `beauty_score` 很高，仍必須執行風險過濾。

至少檢查：

| 風險 | 建議條件 |
|---|---|
| 資料不足 | 有效日線少於 240 日 |
| 資料品質失敗 | 缺值、重複、未調整除權息、異常跳空 |
| 流動性不足 | 20 日平均成交金額低於門檻 |
| 低價股風險 | 調整後價格低於 NT$5 且流動性不足 |
| 近期崩跌 | 20 日報酬 <= -30% |
| 跌停賣壓 | 出現跌停或接近跌停 |
| 趨勢破壞 | close < SMA60 且 SMA60 < SMA120 |
| 停止交易 | 長時間無成交或資料缺失 |
| 台股特殊處置 | 處置股、全額交割、注意股高風險狀態 |

建議初始阻擋條件：

```text
risk_block =
    data_quality.status != PASS
 OR avg_turnover_20d < minimum_avg_turnover_20d_ntd
 OR return_20d <= -0.30
 OR close < SMA60 AND SMA60 < SMA120
 OR is_suspended_or_special_treatment = true
```

未達阻擋程度的風險放入 `risk_flags`，供 Agent 解釋。

## 8. 最終分類邏輯

### 8.1 專案共振分數

```text
project_condition_score =
    1 if fund_pass else 0
  + 1 if tech_is_buy else 0
  + 1 if chip_favorable else 0
  + 1 if news_not_bearish else 0
```

ETF 或不適用的模組標記為 `NOT_APPLICABLE`，分類時改用專屬 profile，不硬算 0 分。

### 8.2 QUALIFIED

必須全部成立：

```text
beauty_score >= 80
AND data_quality.status = PASS
AND risk_block = false
AND trend_confirmed = true
AND fund_pass = true
AND tech_is_buy = true
AND chip_favorable = true
AND news_not_bearish = true
```

### 8.3 WATCHLIST

符合任一條件：

```text
beauty_score >= 65
AND beauty_score < 80
AND data_quality.status = PASS
AND risk_block = false
AND project_condition_score >= 2
```

或：

```text
beauty_score >= 80
AND data_quality.status = PASS
AND risk_block = false
AND project_condition_score = 3
AND missing_condition NOT IN ["data_quality", "risk"]
```

或：

```text
recovery_pattern = true
AND close >= SMA20
AND risk_block = false
```

### 8.4 NOT_QUALIFIED

```text
beauty_score < 65
OR project_condition_score <= 1
OR risk_block = true
```

### 8.5 INSUFFICIENT_DATA

```text
trading_days < 240
OR data_quality.status = FAILED
```

### 8.6 門檻屬性

80 / 65 是工程初始參數，不是書中原始標準，也不是投資建議閾值。必須允許透過 configuration 調整。

## 9. 輸出結構

### 9.1 Agent Tool Schema

```json
{
  "name": "analyze_taiwan_beauty_investment",
  "description": "Analyze a Taiwan-listed stock or ETF using a configurable price-action beauty strategy and multi-factor Taiwan market rules.",
  "input_schema": {
    "type": "object",
    "properties": {
      "stock_id": {
        "type": "string",
        "description": "台股四位數代號、代號加 .TW/.TWO，或繁體中文簡稱"
      },
      "as_of_date": {
        "type": "string"
      },
      "asset_type": {
        "type": "string",
        "enum": ["stock", "etf", "auto"]
      },
      "config_profile": {
        "type": "string"
      }
    },
    "required": ["stock_id"]
  }
}
```

### 9.2 API Response Schema

```json
{
  "stock_id": "2330",
  "stock_name": "台積電",
  "market": "TWSE",
  "asset_type": "stock",
  "as_of_date": "2026-10-05",
  "status": "QUALIFIED",
  "beauty_score": 86.4,
  "components": {
    "trend": 24.0,
    "stair_step": 17.8,
    "high_52w": 18.9,
    "drawdown": 12.1,
    "momentum": 10.8,
    "volatility": 2.8
  },
  "signals": {
    "trend_confirmed": true,
    "near_52w_high": true,
    "breakout_52w_high": false,
    "stair_step_uptrend": true,
    "recovery_pattern": false,
    "fund_pass": true,
    "tech_is_buy": true,
    "chip_favorable": true,
    "news_not_bearish": true
  },
  "project_condition_score": 4,
  "risk_flags": [],
  "risk_block": false,
  "data_quality": {
    "status": "PASS",
    "trading_days": 720,
    "price_basis": "adjusted_close"
  },
  "explanation": {
    "positive": [],
    "negative": [],
    "summary": ""
  }
}
```

欄位命名相容規則：

1. `52w` 對外顯示可維持「52 週高點」，程式欄位可使用 `high_240d`。
2. 籌碼單位必須明確使用 `lots` 或 `張`。
3. 所有金額以新台幣 `NTD` 表示。
4. 所有策略結果必須帶 `as_of_date`。

## 10. Agent 行為規則

當使用者問「這支股票值得買嗎」，Agent 必須轉換成：

> 「這檔台股目前是否符合顏值投資法與專案多因子共振條件？」

Agent 必須依序：

1. 解析台股代號。
2. 取得市場資料。
3. 驗證資料完整性與除權息調整。
4. 計算顏值與技術指標。
5. 計算基本面、籌碼面與新聞面。
6. 執行台股風控。
7. 計算分數與分類。
8. 只根據 deterministic engine 的 JSON 解釋結果。

禁止 Agent 目測圖表後直接輸入分數，也禁止跳過資料驗證直接說「值得買」。

回應必須包含：

```text
股票：{stock_id} {stock_name}
市場：TWSE / TPEx
資料日期：{as_of_date}
策略狀態：QUALIFIED / WATCHLIST / NOT_QUALIFIED
顏值分數：{score}/100
基本面：{月營收 YoY / EPS / fallback}
技術面：{布林、MACD、均線}
籌碼面：{法人五日買賣超 / 連買 / 吸籌}
新聞面：{情緒分數與原因}
風險：{risk_flags}
策略判斷：{qualification_explanation}
```

最後必須註明：

> 以上為基於歷史資料與可設定規則的策略篩選結果，不代表未來報酬，也不構成投資保證。

## 11. 配置範例

建立：

```text
config/beauty_investment_tw.yaml
```

建議：

```yaml
data:
  minimum_trading_days: 240
  preferred_history_days: 720
  price_basis: adjusted_close

periods:
  short: 20
  medium: 60
  long: 120
  year: 240

score:
  qualified: 80
  watchlist: 65

weights:
  trend: 25
  stair_step: 20
  high_52w: 20
  drawdown: 15
  momentum: 15
  volatility: 5

technical:
  bb_length: 20
  bb_std: 2
  bb_compressed_bandwidth: 0.12
  bb_breakout_tolerance: 0.985
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9

fundamental:
  revenue_yoy_min: 0.10
  quarterly_eps_min: 0
  revenue_fallback_until_day: 10

chips:
  days: 5
  foreign_strong_net_lots: 500
  trust_strong_net_lots: 100
  total_accumulate_net_lots: 200
  minimum_positive_days: 3

news:
  max_items: 5
  not_bearish_min_score: -1

breakout:
  confirmation_days: 2
  turnover_ratio_to_20d_avg: 1.0

liquidity:
  minimum_avg_turnover_20d_ntd: 50000000
  minimum_price: 5

risk:
  severe_drawdown_20d: -0.30
  limit_move_buffer: 0.097

data_quality:
  allow_missing_days: false
```

所有 threshold 必須可依上市股票、上櫃股票、ETF、高價股、低價股與週期股建立 profile。

## 12. 回測與測試要求

### 12.1 回測

不得只測「現在看起來漂亮的股票」。必須支援歷史時間點重算：

```text
T 日收盤前可得資料 → T 日訊號 → T+1 或之後可成交價驗證
```

台股回測需特別處理：

1. 除權息還原。
2. 漲跌停無法成交。
3. 停牌與處置股票。
4. 上市櫃轉換與代號變更。
5. 手續費、證券交易稅與最低手續費。
6. 現存與已下市標的，降低 survivorship bias。

至少輸出：

```text
CAGR
Annualized Volatility
Maximum Drawdown
Sharpe Ratio
Win Rate
Number of Trades
Average Holding Period
Turnover
Profit Factor
Qualified Signal Count
False Breakout Count
Average Forward 20D / 60D / 120D Return
```

這些是研究結果，不得轉寫成未來報酬保證。

### 12.2 必要測試

至少建立：

1. 完美上升、低波動、接近 52 週高點，預期高 `beauty_score`。
2. 暴漲暴跌，預期波動懲罰。
3. 長期下降與 Lower High，預期 `NOT_QUALIFIED`。
4. 剛突破前 240 日高點，預期 `breakout = true`。
5. 突破後兩日跌回，預期 `breakout_confirmed = false`。
6. 少於 240 日資料，預期 `INSUFFICIENT_DATA`。
7. T 日結果不因 T+1 之後資料改變，驗證 look-ahead bias。
8. 除權息日不應被誤判為崩跌。
9. 跌停日不得產生 `QUALIFIED`。
10. 台股月營收未公布時應 fallback，並保留 `is_fallback`。
11. 上櫃 `.TWO` 資料可取得並正確標記市場。
12. ETF profile 不應被個股 EPS 或法人買超條件誤殺。

## 13. Definition of Done

本功能完成前，以下條件必須全部成立：

```text
[ ] 可輸入台股四位數代號或中文簡稱
[ ] 支援上市 .TW 與上櫃 .TWO 資料容錯
[ ] 可取得至少 240 個有效交易日資料
[ ] 使用調整後價格處理除權息
[ ] 資料品質檢查完成
[ ] 台股漲跌停與流動性風控完成
[ ] 趨勢、碎步上漲、52 週高點、回撤、動能、波動可計算
[ ] Beauty Score = 0~100
[ ] 基本面條件可解釋
[ ] 技術面 MACD / 布林 / SMA20 條件可解釋
[ ] 籌碼面三大法人張數條件可解釋
[ ] 新聞情緒條件可解釋
[ ] QUALIFIED / WATCHLIST / NOT_QUALIFIED 規則固定
[ ] JSON Schema 固定且包含 as_of_date
[ ] Agent 可解釋每一個扣分與風險
[ ] Unit tests 通過
[ ] Look-ahead bias test 通過
[ ] 結果不會把「符合策略」誤寫成「保證上漲」
```

## 14. 最終決策摘要

```text
台股資料
    ↓
代號解析與市場別確認
    ↓
除權息調整與資料品質檢查
    ↓
顏值價格結構分數
    ↓
基本面 + 技術面 + 籌碼面 + 新聞面
    ↓
台股漲跌停 / 流動性 / 停牌 / 處置風控
    ↓
QUALIFIED / WATCHLIST / NOT_QUALIFIED / INSUFFICIENT_DATA
```

本模組的真正功能，不是替使用者決定買哪一張股票，而是把主觀的「這張圖看起來很漂亮」轉換成適合台股交易制度、可重複測試、可回測、可解釋的多因子判斷系統。
