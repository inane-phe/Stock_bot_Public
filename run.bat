@echo off
chcp 65001 >nul
title 台股量化多因子選股戰情室 Web
cd /d "%~dp0"

echo ========================================================
echo   正在啟動【台股量化多因子選股戰情室】Web 服務...
echo   模式：100% 純網路爬蟲 / 零 API 上限 / 隨搜隨掃
echo ========================================================
echo.

if exist "report.html" (
    echo [清理] 刪除舊的 HTML 報告 report.html
    del /f /q "report.html" >nul 2>&1
)

if exist "scanned_cache.json" (
    echo [歷史安全備份] 自動封存前次掃描分析結果至歷史紀錄庫...
    python history_tracker.py --auto-backup >nul 2>&1
    echo [清理] 清空暫存快取資料 scanned_cache.json
    del /f /q "scanned_cache.json" >nul 2>&1
)

echo [就緒] 已完成歷史封存與快取清理，準備全新加載！
echo.
echo 本機網址： http://localhost:5000
echo.

start "" "http://localhost:5000"
python app.py

if errorlevel 1 (
    echo.
    echo [ERROR] 服務異常中斷，請檢查上方錯誤訊息。
    pause
)