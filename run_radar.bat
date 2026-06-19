@echo off
chcp 65001 > nul
echo ==============================
echo  持仓ETF雷达 - Portfolio Radar
echo ==============================
echo.

REM 设置星耀环境变量
set AD_USERNAME=10500164719
set AD_PASSWORD=SHANshan252112
set AD_HOST=101.230.159.234
set AD_PORT=8600

REM 重定向 tgw 证书路径到用户目录（避免 C:\Users\Public\Documents 权限问题）
set USERPROFILE=%USERPROFILE%
set MDGA_PATH=%USERPROFILE%\.mdga_file
if not exist "%MDGA_PATH%" mkdir "%MDGA_PATH%"
if not exist "%MDGA_PATH%\log" mkdir "%MDGA_PATH%\log"
set TGW_CERT_PATH=%MDGA_PATH%

echo 正在运行持仓雷达...
echo.

REM 运行脚本（自动查找 Python）
set PYTHON_EXE=
where py >nul 2>&1 && set PYTHON_EXE=py -3
if "%PYTHON_EXE%"=="" where python >nul 2>&1 && set PYTHON_EXE=python
if "%PYTHON_EXE%"=="" where "C:\Users\Niki_Spatial\.workbuddy\binaries\python\envs\default\Scripts\python.exe" >nul 2>&1 && set PYTHON_EXE="C:\Users\Niki_Spatial\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

if "%PYTHON_EXE%"=="" (
    echo [错误] 找不到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

cd /d "%~dp0"
%PYTHON_EXE% run_portfolio_radar.py

echo.
echo 完成！按任意键打开报告...
pause >nul

REM 打开生成的 HTML 报告
if exist "data\portfolio_radar.html" (
    start "" "data\portfolio_radar.html"
) else (
    echo [提示] 报告未生成，请检查错误信息
    pause
)
