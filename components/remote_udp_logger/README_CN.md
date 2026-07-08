# Remote UDP Logger（中文说明）

[English README](README.md)

`remote_udp_logger` 会把 ESP-IDF 的 `ESP_LOGx` 输出镜像发送到 UDP。这样设备只接
电池、不连接 USB 串口时，也能在电脑上查看运行日志。

它可以给每行 UDP 日志加上稳定的设备 ID 和递增序号：

```text
[imei=90e5b1aeca9a seq=42] I (2642238) Charge: voltage: 3984, current: 0
```

配套桌面查看器可以显示发送方 `IP:端口`，按设备 ID、级别和 feature 过滤日志，并在
UDP 序号跳变时提示可能丢包。

## 功能

- 把 `ESP_LOGI`、`ESP_LOGW`、`ESP_LOGE` 等 ESP-IDF 日志镜像到 UDP。
- 不影响原有串口日志输出。
- 支持局域网广播：受限广播 `255.255.255.255:8001` 或子网定向广播
  `192.168.1.255:8001`，电脑端无需配对或固定 IP。
- 支持发送到指定电脑，例如 `192.168.1.23:8001`。
- 支持可选设备 ID 与递增 `seq` 前缀，方便多设备调试和丢包判断。
- 支持在 `Initialize()` 前通过 `SetDeviceId()` / `SetTarget()` 运行时覆盖。
- 发送失败可诊断：失败计数、每 100 次在本机串口提示一次，
  并可通过 `RemoteUdpLogger::GetSendFailureCount()` 查询。

## 快速开始

添加依赖：

```shell
idf.py add-dependency "x-bell/remote_udp_logger"
```

打开组件配置：

```text
CONFIG_REMOTE_UDP_LOGGER_ENABLE=y
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"
CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y
```

在 `app_main()` 早期、网络栈可用后初始化：

```cpp
#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");   // 可选
    RemoteUdpLogger::Initialize();

    ESP_LOGI("app", "This log is also mirrored to UDP");
}
```

只有 `RemoteUdpLogger::Initialize()` 之后产生的日志才会被镜像到 UDP；Wi-Fi 连上
之前的日志会静默丢失（UDP 无连接）。

完整可编译示例见 [examples/basic](examples/basic)。

## 桌面查看器

配套 Windows 查看器（CLI 接收器、Qt GUI、浏览器查看器、UDP 转 TCP 桥）位于插件
仓库的 `host_tool/` 目录，不随组件包发布。从源码运行 GUI：

```powershell
python -m pip install -r host_tool/requirements.txt
python host_tool/udp_log_gui.py --udp-host 0.0.0.0 --udp-port 8001 --auto-start
```

同一 UDP 端口同时只能开一个查看工具。

## 注意事项

- 电脑默认监听 UDP `8001`；查看器显示的设备源端口由设备网络栈分配。
- 广播可能被路由器或 Windows 防火墙拦截。如果广播不稳定，建议改成发送到电脑固定 IP。
- 传输为明文 UDP，无认证、无加密、无缓存重传。本组件用于开发和诊断，
  不要在正式生产固件里广播敏感日志。

## 许可证

MIT，见 [LICENSE](LICENSE)。
