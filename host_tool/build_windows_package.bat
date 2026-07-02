@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set PACKAGE_DIR=dist\XbellUdpLogViewer_package
set PACKAGE_ZIP=dist\XbellUdpLogViewer_package.zip
set APP_DIR=dist\XbellUdpLogViewer
set LEGACY_ONEFILE=dist\XbellUdpLogViewer.exe

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name XbellUdpLogViewer ^
  udp_log_gui.py

if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)

if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"

xcopy /e /i /y "%APP_DIR%" "%PACKAGE_DIR%\XbellUdpLogViewer" >nul
copy /y "..\docs\integration-guide.md" "%PACKAGE_DIR%\RemoteUdpLogger_IntegrationGuide.md" >nul

(
  echo @echo off
  echo cd /d "%%~dp0XbellUdpLogViewer"
  echo start "" "XbellUdpLogViewer.exe"
) > "%PACKAGE_DIR%\Start_XbellUdpLogViewer.bat"

(
  echo Xbell UDP Log Viewer 使用说明
  echo =============================
  echo.
  echo 快速开始
  echo --------
  echo 1. 先完整解压 zip 包
  echo 2. 双击 Start_XbellUdpLogViewer.bat
  echo 3. UDP Host 保持 0.0.0.0
  echo 4. UDP Port 保持 8001
  echo 5. 点击 Start
  echo 6. 设备只接电池供电，并等待它连接 Wi-Fi
  echo 7. 点击 Export Logs 可导出本次会话完整日志
  echo.
  echo 日志留存
  echo --------
  echo 工具收到日志后会立即写入本机会话文件，默认目录为 %%USERPROFILE%%\XbellUdpLogs。
  echo 界面显示区只保留最近一段日志用于性能优化，导出时读取完整会话文件。
  echo 当前传输协议是 UDP，工具端能保证已收到日志尽快落盘；网络层严格不丢需要后续 TCP/ACK 或设备端缓存补传。
  echo.
  echo 设备选择
  echo --------
  echo 使用该插件的固件会给 UDP 日志加上 IMEI/设备 ID 前缀。
  echo 工具会自动列出设备，并支持按 IMEI/设备 ID 过滤日志。
  echo.
  echo Windows 阻止运行时
  echo ------------------
  echo 这是未签名的内部调试工具，Windows SmartScreen 可能会提示风险。
  echo 长期方案：使用可信代码签名证书给 EXE 签名。
  echo 临时方案：右键 zip 或 EXE，打开“属性”，勾选“解除锁定”后再运行。
  echo.
  echo 详细说明
  echo --------
  echo 参见：RemoteUdpLogger_IntegrationGuide.md
) > "%PACKAGE_DIR%\README.txt"

powershell -NoProfile -Command "Get-ChildItem -Path '%CD%\%PACKAGE_DIR%' -Recurse -File | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash, $_.Path.Substring(('%CD%\%PACKAGE_DIR%\').Length) } | Set-Content -Encoding ASCII '%CD%\%PACKAGE_DIR%\SHA256SUMS.txt'"

if exist "%LEGACY_ONEFILE%" del /f /q "%LEGACY_ONEFILE%"
if exist "dist\udp_log_gui_config.json" del /f /q "dist\udp_log_gui_config.json"
if exist "XbellUdpLogViewer.spec" del /f /q "XbellUdpLogViewer.spec"

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
