@echo off
setlocal
cd /d "%~dp0"
set UDP_HOST=0.0.0.0
set UDP_PORT=8001

python udp_log_gui.py --udp-host %UDP_HOST% --udp-port %UDP_PORT% --auto-start
