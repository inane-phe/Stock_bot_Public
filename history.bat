@echo off
chcp 65001 >nul
title 🎯 台股量化多因子選股戰情室 - 歷史紀錄與回顧檢驗
cd /d "%~dp0"

:: 檢查是否有傳入命令列參數 (如: history.bat save / verify / open / scan)
if "%~1"=="save" goto do_save
if "%~1"=="verify" goto do_verify
if "%~1"=="open" goto do_open
if "%~1"=="scan" goto do_scan

:menu
cls
echo ======================================================================
echo   🎯【台股量化多因子選股戰情室】歷史分析紀錄與回顧檢驗工具
echo   功能：自動存檔 / 離線 HTML / Excel CSV / 即時回測比對歷史勝率
echo ======================================================================
echo.
echo   [1] 💾 立即封存當前戰情室結果為歷史紀錄 (產出 HTML / CSV / JSON)
echo   [2] ⚡ 執行核心母體全新掃描並自動存檔 (含主要營業項目)
echo   [3] 📂 開啟歷次歷史紀錄總覽 (開啟網頁總表 index.html 與資料夾)
echo   [4] 🎯 歷史回顧檢驗：比對最新即時股價，檢查當時分析正確性 (勝率回測)
echo   [5] 🌐 啟動 Web 戰情室服務 (http://localhost:5000)
echo   [0] 🚪 離開
echo.
echo ======================================================================
set /p choice="請選擇欲執行的操作項目 [0-5]: "

if "%choice%"=="1" goto do_save
if "%choice%"=="2" goto do_scan
if "%choice%"=="3" goto do_open
if "%choice%"=="4" goto do_verify
if "%choice%"=="5" goto do_web
if "%choice%"=="0" goto do_exit

echo [無效選項] 請輸入 0 到 5 之間的數字。
timeout /t 2 >nul
goto menu

:do_save
echo.
echo ======================================================================
echo   [處理中] 正在將當前選股分析結果封存至歷史紀錄庫...
echo ======================================================================
python history_tracker.py --save
echo.
echo   歷史紀錄已成功存入 history/ 資料夾！
echo   包含：獨立離線 HTML 報告、帶有營業項目的 Excel CSV、完整 JSON
echo.
if not "%~1"=="" exit /b 0
pause
goto menu

:do_scan
echo.
echo ======================================================================
echo   [掃描中] 正在執行核心母體量化掃描並準備自動存檔...
echo ======================================================================
python main.py
echo.
echo   [存檔中] 正在將本次掃描結果封存為歷史紀錄...
python history_tracker.py --save
echo.
echo   掃描與歷史封存已順利完成！
if not "%~1"=="" exit /b 0
pause
goto menu

:do_open
echo.
echo ======================================================================
echo   正在開啟歷次歷史紀錄總表 (history/index.html) 與資料夾...
echo ======================================================================
python history_tracker.py --open
explorer "history"
echo.
if not "%~1"=="" exit /b 0
pause
goto menu

:do_verify
echo.
echo ======================================================================
echo   [回測檢驗] 正在連線台灣股市最新即時報價，檢驗歷史分析正確率...
echo ======================================================================
python history_tracker.py --verify
echo.
echo   檢驗完成！已同步更新 CSV 試算表並產出回測報告。
echo.
if not "%~1"=="" exit /b 0
pause
goto menu

:do_web
echo.
echo 正在啟動 Web 戰情室服務...
start "" "http://localhost:5000"
python app.py
pause
goto menu

:do_exit
echo.
echo 感謝使用，祝投資順利！
exit /b 0
