ngrok http 5000
CHANNEL_ACCESS_TOKEN = "<your LINE Channel Access Token>"
CHANNEL_SECRET = "<your LINE Channel Secret>"

FINMIND_TOKEN = "<your FinMind API Token>"

token = "<your FinMind API Token>"

dl = DataLoader()
dl.login_by_token(api_token=FINMIND_TOKEN)



量化篩選的優化建議
為了避免程式在每個月的 1 日到 10 日之間「誤殺」還沒公布最新營收的優質標的，建議可以在篩選腳本（例如 Python）裡加上簡單的容錯邏輯：

1. 加入動態月份 Fallback 機制
在判斷當月營收是否符合條件時，檢查當前日期與資料是否存在：

如果今天是在 10 號以前，且最新的單月營收為 NaN，程式邏輯自動 退回採用上一期（5月份） 的 YoY 數據來評估。

一旦過了 10 號如果仍為 NaN，再真正判定為「異常/資料缺失」並剔除。
