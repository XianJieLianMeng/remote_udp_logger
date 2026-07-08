# Remote UDP Logger

ESP32 无线日志组件：把 `ESP_LOGx` 输出镜像到 UDP，设备只接电池、不插 USB 串口，也能在电脑上实时看日志。

> Mirror ESP-IDF logs to UDP for wireless debugging. English docs: [component README](components/remote_udp_logger/README.md).

```text
┌──────────────┐   Wi-Fi / UDP:8001    ┌─────────────────────────────┐
│ ESP32 设备    │ ────────────────────► │ 电脑（GUI / 浏览器 / 命令行） │
│ ESP_LOGI(...) │  [imei=xx seq=42] ... │ 着色显示·过滤·丢包检测·导出   │
└──────────────┘                        └─────────────────────────────┘
```

## 三分钟上手

### 第 1 步：固件端接入组件

方式 A（推荐，从 ESP Component Registry 安装）：

```shell
idf.py add-dependency "xianjielianmeng/remote_udp_logger"
```

方式 B（离线）：把 `components/remote_udp_logger` 复制到你工程的 `components/` 目录。

打开配置（`idf.py menuconfig`，或直接写进 `sdkconfig.defaults`）：

```text
CONFIG_REMOTE_UDP_LOGGER_ENABLE=y
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"   # 默认广播，无需知道电脑 IP
CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y
```

在 `app_main()` 里、网络栈可用后初始化：

```cpp
#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");   // 可选：多设备时用于区分
    RemoteUdpLogger::Initialize();

    ESP_LOGI("app", "这行日志会同时出现在串口和电脑的无线日志工具里");
}
```

编译烧录，设备连上 Wi-Fi 即开始发送。完整可编译示例见
[components/remote_udp_logger/examples/basic](components/remote_udp_logger/examples/basic)。

### 第 2 步：电脑端看日志（三选一）

| 工具 | 适合场景 | 启动方式 |
| --- | --- | --- |
| 桌面 GUI（推荐） | 日常调试、多设备 | `pip install -r host_tool/requirements.txt` 后运行 `python host_tool/udp_log_gui.py`，或直接用 Release 里的绿色包 |
| 浏览器查看器 | 零依赖（仅需 Python） | `python host_tool/udp_log_web_viewer.py --open-browser` |
| 命令行 | 服务器 / 脚本 | `python host_tool/udp_log_receiver.py --level W` |

要求 Python ≥ 3.10；三个工具都监听 UDP 8001，同一时间只开一个。

### 第 3 步：你会看到什么

```text
[imei=90e5b1aeca9a source=192.168.1.5:52413 seq=41] I (2642238) Charge: voltage: 3984
[imei=90e5b1aeca9a source=192.168.1.5:52413 seq=42] E (2642350) app: something failed
W [udp.seq] event=gap imei=90e5b1aeca9a expected=43 actual=45 missing=2   ← 丢包提示
```

工具端能力：按级别着色（错误红/警告橙/丢包紫）、按设备（IMEI）/级别/feature/关键字过滤、
E/W/丢包实时计数、暂停显示（接收落盘不停）、导出 .log/.jsonl（可只导出选中设备）、
会话自动落盘到 `~/RemoteUdpLogs/`（自动保留最近 100 个会话文件）。
桌面 GUI 另有错误行跳转（F3/Shift+F3）、中英文界面切换（默认中文）。

## 收不到日志？按顺序查

1. 固件里 `CONFIG_REMOTE_UDP_LOGGER_ENABLE=y` 已打开并**重新烧录**
2. 设备和电脑在**同一局域网**，设备已连上 Wi-Fi
3. Windows 防火墙第一次运行时要**允许 Python 通过**（专用网络）
4. 提示端口 8001 被占用 → 关掉其他正在运行的日志工具
5. 路由器过滤广播 → 把 `CONFIG_REMOTE_UDP_LOGGER_TARGET` 改成电脑固定 IP，
   例如 `192.168.1.23:8001`（GUI 的"设备端目标"栏会帮你生成）

## 目录结构

```text
components/remote_udp_logger/   ESP-IDF 组件（发布到 Component Registry 的部分）
  ├─ examples/basic/            可独立编译的 Wi-Fi + 日志示例工程
  ├─ README.md / README_CN.md   组件文档（英/中）
  └─ CHANGELOG.md
host_tool/                      电脑端工具（GUI / Web / CLI / TCP 桥）
docs/                           接入指南与发布说明
```

## 边界与限制

- 传输是**明文 UDP**，无认证加密、无重传，定位是**内网开发调试**；
  量产固件请保持组件关闭，不要广播敏感日志。
- 每行日志带递增 `seq`，工具端据此提示丢包；需要严格不丢请改用固定 IP + 抓包复核。
- 发送失败会计数并每 100 次在本机串口提示一次，可用
  `RemoteUdpLogger::GetSendFailureCount()` 查询。

## 许可证

MIT，见 [LICENSE](LICENSE)。
