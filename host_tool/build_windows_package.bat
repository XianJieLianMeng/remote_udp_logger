@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem host_tool files are generated copies; refresh from <repo>/scripts when available.
python sync_from_scripts.py
if errorlevel 1 (
  echo Failed to sync host tools from scripts directory.
  exit /b 1
)

set PACKAGE_DIR=dist\UdpLogViewer_package
set PACKAGE_ZIP=dist\UdpLogViewer_package.zip
set APP_DIR=dist\UdpLogViewer

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name UdpLogViewer ^
  udp_log_gui.py

if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)

if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"

rem PyInstaller 6 onedir layout is UdpLogViewer.exe + _internal\ side by side.
rem Copy that content to the package root so users double-click the exe
rem directly after unzipping - no launcher bat needed.
xcopy /e /i /y "%APP_DIR%" "%PACKAGE_DIR%" >nul
copy /y "..\docs\integration-guide.md" "%PACKAGE_DIR%\RemoteUdpLogger_IntegrationGuide.md" >nul

(
  echo Remote UDP Log Viewer 使用说明
  echo ==============================
  echo.
  echo 快速开始
  echo --------
  echo 1. 先完整解压 zip 包
  echo 2. 双击 UdpLogViewer.exe
  echo 3. UDP 监听地址保持 0.0.0.0，端口保持 8001
  echo 4. 点击 开始接收
  echo 5. 设备连接 Wi-Fi 后，日志会显示在窗口中：错误红色、警告橙色、丢包提示紫色
  echo 6. 多台设备同时发送时，在设备下拉框里按 IMEI/设备 ID 选择目标设备
  echo 7. 点击 导出日志 可导出本次会话完整日志
  echo 8. 界面默认中文，右上角可切换 English
  echo.
  echo 日志留存
  echo --------
  echo 工具收到日志后会立即写入本机会话文件，默认目录为 %%USERPROFILE%%\RemoteUdpLogs。
  echo 工具启动时自动清理最旧会话文件，默认保留最近 100 个。
  echo 界面显示区只保留最近一段日志用于性能优化，导出时读取完整会话文件。
  echo 当前传输协议是 UDP，工具端能保证已收到日志尽快落盘；网络层严格不丢需要 TCP/ACK 或设备端缓存补传。
  echo.
  echo Windows 阻止运行时
  echo ------------------
  echo 这是未签名的调试工具，Windows SmartScreen 可能会提示风险。
  echo 临时处理：右键 zip 或 EXE，打开"属性"，勾选"解除锁定"后再运行。
  echo 长期建议：使用可信代码签名证书给 EXE 签名。
  echo.
  echo 详细说明
  echo --------
  echo 参见：RemoteUdpLogger_IntegrationGuide.md
) > "%PACKAGE_DIR%\README.txt"

powershell -NoProfile -Command "Get-ChildItem -Path '%CD%\%PACKAGE_DIR%' -Recurse -File | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash, $_.Path.Substring(('%CD%\%PACKAGE_DIR%\').Length) } | Set-Content -Encoding ASCII '%CD%\%PACKAGE_DIR%\SHA256SUMS.txt'"

if exist "dist\udp_log_gui_config.json" del /f /q "dist\udp_log_gui_config.json"
if exist "UdpLogViewer.spec" del /f /q "UdpLogViewer.spec"

if exist "%PACKAGE_ZIP%" del /f /q "%PACKAGE_ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%CD%\%PACKAGE_DIR%\*' -DestinationPath '%CD%\%PACKAGE_ZIP%'"

if errorlevel 1 (
  echo.
  echo Packaging failed.
  exit /b 1
)

echo.
echo Build complete.
echo   App folder: %CD%\%APP_DIR%
echo   Package folder: %CD%\%PACKAGE_DIR%
echo   Package zip: %CD%\%PACKAGE_ZIP%
