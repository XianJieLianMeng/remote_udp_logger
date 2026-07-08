# Remote UDP Logger 插件接入说明

## 1. 插件用途

这个插件用于“设备接电池运行、不插 USB，也能看 ESP 日志”的场景。

它包含两部分：

- ESP 端组件：把 `ESP_LOGI/W/E` 等日志镜像发送到 UDP。
- 电脑端工具：接收 UDP 日志，显示设备 `IP:源端口`，并按 `imei` / 设备 ID 筛选日志。

默认发送目标：

```text
255.255.255.255:8001
```

这表示设备把日志广播到同一局域网的 `8001` 端口。

---

## 2. 目录结构

```text
remote_udp_logger
├─ plugin.json
├─ components
│  └─ remote_udp_logger
│     ├─ CMakeLists.txt
│     ├─ Kconfig
│     ├─ idf_component.yml
│     ├─ README.md
│     ├─ LICENSE
│     ├─ include
│     │  └─ remote_udp_logger.h
│     ├─ remote_udp_logger.cc
│     └─ examples
├─ host_tool
│  ├─ udp_log_gui.py
│  ├─ udp_log_receiver.py
│  ├─ requirements.txt
│  ├─ start_udp_log_gui.bat
│  └─ build_windows_package.bat
├─ examples
│  ├─ app_main_snippet.cc
│  └─ sdkconfig.defaults
└─ docs
   └─ integration-guide.md
```

---

## 3. ESP-IDF 项目接入

### 3.1 复制组件

把：

```text
plugins/remote_udp_logger/components/remote_udp_logger
```

复制到目标 ESP-IDF 项目的：

```text
components/remote_udp_logger
```

最终结构类似：

```text
your_esp_project
├─ main
├─ components
│  └─ remote_udp_logger
│     ├─ CMakeLists.txt
│     ├─ Kconfig
│     ├─ include
│     │  └─ remote_udp_logger.h
│     └─ remote_udp_logger.cc
└─ sdkconfig.defaults
```

也可以用插件自带脚本安装：

```powershell
powershell -ExecutionPolicy Bypass -File plugins\remote_udp_logger\install_esp_component.ps1 -ProjectRoot D:\path\to\your_esp_project
```

如果目标项目里已经存在 `components\remote_udp_logger`，需要确认可以覆盖后再加 `-Force`。

### 3.2 打开配置

在 `sdkconfig.defaults` 加入：

```text
CONFIG_REMOTE_UDP_LOGGER_ENABLE=y
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"
CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y
CONFIG_REMOTE_UDP_LOGGER_DEVICE_ID="unknown"
```

也可以用 `idf.py menuconfig` 配置：

```text
Remote UDP Logger Plugin
```

### 3.3 初始化代码

在 `app_main()` 或项目启动入口里加入：

```cpp
#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");
    RemoteUdpLogger::Initialize();

    // Continue normal project initialization here.
}
```

建议 `RemoteUdpLogger::Initialize()` 尽量靠前调用，因为只有调用之后产生的日志才会被镜像到 UDP。

如果你的项目已经有 IMEI 获取接口，建议这样接：

```cpp
RemoteUdpLogger::SetDeviceId(GetYourDeviceImei());
RemoteUdpLogger::Initialize();
```

当前 Xbell 项目可以使用：

```cpp
#include "business_device_identity.h"
#include "remote_udp_logger.h"

RemoteUdpLogger::SetDeviceId(BusinessDeviceIdentity::GetBleBindingImei());
RemoteUdpLogger::Initialize();
```

### 3.4 设备 ID / IMEI 的作用

开启 `CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y` 后，UDP 日志会变成：

```text
[imei=90e5b1aeca9a seq=42] I (2642238) Charge: voltage: ...
```

桌面工具会解析这个 `imei` 和递增 `seq`，自动生成设备下拉框，并在序号跳变时提示可能丢包：

```text
90e5b1aeca9a @ 192.168.1.50:49152
W [udp.seq] event=gap imei=90e5b1aeca9a source=192.168.1.50:49152 expected=12 actual=15 missing=3
```

这样多台设备同时广播日志时，也能只看指定设备。

### 3.5 广播和单播

广播模式：

```text
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"
```

特点：

- 同一局域网内多台电脑都能接收
- 适合调试和多人协作
- 可能被部分路由器或防火墙限制

单播模式：

```text
CONFIG_REMOTE_UDP_LOGGER_TARGET="192.168.1.23:8001"
```

特点：

- 只发给指定电脑
- 更稳定
- 换电脑时需要改目标 IP 并重新刷固件，或者在代码里调用 `RemoteUdpLogger::SetTarget()`

运行时覆盖目标地址：

```cpp
RemoteUdpLogger::SetTarget("192.168.1.23:8001");
RemoteUdpLogger::Initialize();
```

---

## 4. 电脑端工具使用

### 4.1 直接运行源码

安装依赖：

```powershell
cd plugins\remote_udp_logger\host_tool
python -m pip install -r requirements.txt
```

启动 GUI：

```powershell
python udp_log_gui.py --udp-host 0.0.0.0 --udp-port 8001 --auto-start
```

或者双击：

```text
start_udp_log_gui.bat
```

### 4.2 打 Windows 绿色包

在 Windows 上运行：

```powershell
cd plugins\remote_udp_logger\host_tool
build_windows_package.bat
```

生成：

```text
host_tool/dist/UdpLogViewer_package.zip
```

发给别人时推荐发这个 zip。

对方解压后直接双击：

```text
UdpLogViewer.exe
```

### 4.3 Windows 拦截处理

这个工具默认没有代码签名，Windows SmartScreen 或 Defender 可能提示未知发布者。

临时处理：

1. 右键 `UdpLogViewer_package.zip`
2. 选择 `属性`
3. 如果看到 `解除锁定` / `Unblock`，勾选它
4. 重新解压
5. 双击 `UdpLogViewer.exe`

长期对外分发建议：

- 用公司代码签名证书签名
- 或购买 OV/EV Code Signing 证书
- 打包后用 `signtool` 对 `UdpLogViewer.exe` 签名

---

## 5. 桌面工具界面字段

- `UDP Host`：本机监听地址，通常保持 `0.0.0.0`。
- `UDP Port`：本机监听端口，默认 `8001`。
- `Device Target`：方便复制给设备侧配置的目标地址，默认 `255.255.255.255:8001`。
- `Detected PC target`：工具自动检测到的本机 `IP:端口`，适合单播配置。
- `All Devices` 下拉框：按 `imei` / 设备 ID 过滤日志。
- `All Levels` 下拉框：按 `E/W/I/D/V` 过滤日志。
- `Feature`：按 XBell feature 或 ESP-IDF tag 过滤日志，例如 `device_msg.eval`、`Charge`。
- `Show Source`：每行显示 `[imei=xxx source=设备IP:源端口 seq=n]`。
- `Filter`：按正文、来源、IMEI、feature 或源码文件关键字过滤日志，例如 `Charge`、`wifi`、`battery`。
- `Export Logs`：导出本次会话收到的完整日志。
- `.jsonl` 导出：保存字段化记录，包含 `imei/source/sequence/level/timestamp/script/feature/message/text`。

设备的 `IP:源端口` 是接收 UDP 包时自动拿到的。源端口不是 `8001`，它是设备发送 UDP 包时系统分配的端口，可能会变化。

### 5.1 日志留存与导出

桌面工具收到日志后会立即写入本机会话文件，默认目录：

```text
~/RemoteUdpLogs/
```

界面显示区为了性能只保留最近一段日志；`Export Logs` 导出的是完整会话文件，不是只导出当前界面可见行。

当前传输层是 UDP。工具端能保证“收到后尽快落盘”，减少因为窗口关闭、界面缓存上限导致的丢失；但 UDP 本身没有 ACK 和重传，网络层严格不丢需要后续增加 TCP/ACK 或设备端缓存补传。

### 5.2 命令行筛选

命令行接收器适合快速联调或把日志接到其他工具：

```powershell
python udp_log_receiver.py --host 0.0.0.0 --port 8001 --level W --feature device_msg --compact
python udp_log_receiver.py --imei 90e5b1aeca9a --feature eval
python udp_log_receiver.py --level E --jsonl
```

参数说明：

- `--imei`：只显示指定设备 ID / IMEI。
- `--level`：只显示指定级别，取值 `E/W/I/D/V`。
- `--feature`：只显示 feature / ESP-IDF tag 包含关键字的日志。
- `--compact`：命令行输出短格式，完整日志仍写入会话文件。
- `--jsonl`：命令行输出 JSON Lines，便于接入脚本和分析工具。

---

## 6. 当前 Xbell 项目中的对应关系

当前项目里已经有一份内置实现：

- ESP 端：[main/remote_logger.cc](../../../main/remote_logger.cc)
- ESP 入口：[main/main.cc](../../../main/main.cc)
- 桌面工具：[scripts/udp_log_gui.py](../../../scripts/udp_log_gui.py)
- 打包脚本：[scripts/build_udp_log_gui_exe.bat](../../../scripts/build_udp_log_gui_exe.bat)

如果要切到插件组件模式，可以按下面思路迁移：

1. 把 `plugins/remote_udp_logger/components/remote_udp_logger` 复制到 `components/remote_udp_logger`
2. 删除或停用 `main/remote_logger.cc` / `main/remote_logger.h`
3. 把 `main/main.cc` 的 `RemoteLogger::Initialize()` 替换成 `RemoteUdpLogger::Initialize()`
4. 在初始化前调用 `RemoteUdpLogger::SetDeviceId(BusinessDeviceIdentity::GetBleBindingImei())`
5. 在 `sdkconfig.defaults` 里启用 `CONFIG_REMOTE_UDP_LOGGER_ENABLE=y`

当前项目已经能工作，不强制迁移。这个插件目录主要是给其他项目复用和交付。

---

## 7. 常见问题

### 7.1 看不到日志

优先检查：

- 设备是否已经连上 Wi-Fi
- 电脑和设备是否在同一局域网
- Windows 防火墙是否允许 UDP `8001`
- 是否已经有另一个程序占用了 UDP `8001`
- 设备固件里的目标地址是否和电脑监听地址一致

### 7.2 能看到日志，但没有 IMEI 下拉

通常说明设备端没有带 `[imei=xxx seq=n]` 这类设备前缀。

检查：

- `CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y`
- 调用了 `RemoteUdpLogger::SetDeviceId()`
- 固件确实刷入了新版本

旧固件仍然能看日志，但不能按 IMEI 精确筛选。

### 7.3 多台设备日志混在一起

确认每台设备传入的 device id / IMEI 不同，然后在桌面工具的设备下拉框里选择对应设备。

### 7.4 端口号为什么不是 8001

`8001` 是电脑监听端口。

工具显示的 `source=192.168.1.50:49152` 里的 `49152` 是设备发送 UDP 包时的源端口，不固定，这是正常现象。
