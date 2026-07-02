# Remote UDP Logger

`remote_udp_logger` 会把 ESP-IDF 的 `ESP_LOGx` 输出镜像发送到 UDP。这样设备只接电池、不连接 USB 串口时，也能在电脑上查看运行日志。

它可以给每行 UDP 日志加上稳定的设备 ID / IMEI 前缀：

```text
[imei=90e5b1aeca9a seq=42] I (2642238) Charge: voltage: 3984, current: 0
```

配套桌面查看器可以显示发送方 `IP:端口`，按设备 ID、级别和 feature 过滤日志，并在 UDP 序号跳变时提示可能丢包。

## 功能

- 把 `ESP_LOGI`、`ESP_LOGW`、`ESP_LOGE` 等 ESP-IDF 日志镜像到 UDP。
- 不影响原有串口日志输出。
- 支持局域网广播，例如 `255.255.255.255:8001`。
- 支持发送到指定电脑，例如 `192.168.1.23:8001`。
- 支持可选设备 ID 与递增 `seq` 前缀，方便多设备调试和丢包判断。
- 支持通过 `RemoteUdpLogger::SetTarget()` 在运行时覆盖目标地址。

## 基本用法

打开组件配置：

```text
CONFIG_REMOTE_UDP_LOGGER_ENABLE=y
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"
CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y
CONFIG_REMOTE_UDP_LOGGER_DEVICE_ID="unknown"
```

在 `app_main()` 早期初始化：

```cpp
#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");
    RemoteUdpLogger::Initialize();

    ESP_LOGI("app", "This log is also mirrored to UDP");
}
```

只有 `RemoteUdpLogger::Initialize()` 之后产生的日志才会被镜像到 UDP。

## 桌面查看器

配套 Windows 查看器位于：

```text
plugins/remote_udp_logger/host_tool
```

从源码运行：

```powershell
cd plugins\remote_udp_logger\host_tool
python -m pip install -r requirements.txt
python udp_log_gui.py --udp-host 0.0.0.0 --udp-port 8001 --auto-start
```

构建 Windows 绿色包：

```powershell
cd plugins\remote_udp_logger\host_tool
build_windows_package.bat
```

## 注意事项

- 电脑默认监听 UDP `8001`。
- 查看器显示的设备源端口不是 `8001`，而是设备网络栈分配的 UDP 源端口。
- 广播可能被路由器或 Windows 防火墙拦截。如果广播不稳定，建议改成发送到电脑固定 IP。
- 这个组件主要用于开发和诊断，不建议在正式生产环境广播敏感日志。
