# Remote UDP Logger 插件

这个插件把两部分能力打包到一起：

- `components/remote_udp_logger`：ESP-IDF 组件，用于把 `ESP_LOGx` 输出镜像发送到 UDP。
- `host_tool`：Windows 桌面查看器，用于接收 UDP 日志，显示来源 `IP:端口`，按设备 ID / IMEI、级别和 feature 过滤日志，并导出本次会话日志。

默认 UDP 目标：

```text
255.255.255.255:8001
```

典型接入流程：

1. 把 `components/remote_udp_logger` 复制到 ESP-IDF 项目的 `components/remote_udp_logger`。
2. 打开配置项 `CONFIG_REMOTE_UDP_LOGGER_ENABLE=y`。
3. 调用 `RemoteUdpLogger::SetDeviceId(<imei>)` 设置设备标识。
4. 在启动早期调用 `RemoteUdpLogger::Initialize()`。
5. 运行 `host_tool` 里的桌面查看器。

桌面查看器收到日志后会立即写入本机会话文件，默认目录：

```text
~/XbellUdpLogs/
```

点击 `Export Logs` 可以导出完整会话日志；选择 `.jsonl` 文件类型可导出字段化 JSON Lines。界面显示区只保留最近一段日志用于性能优化，但普通日志导出不依赖界面显示缓存。

工具会解析 `[imei=... seq=...]`、XBell 完整/短格式和 ESP-IDF 原生日志格式，提取 `level`、`feature`、`source`、`script`、`sequence` 等字段用于筛选；如果序号跳变，会显示本地 `udp.seq` gap 提示。命令行接收器也支持：

```powershell
python host_tool\udp_log_receiver.py --level W --feature device_msg --compact
python host_tool\udp_log_receiver.py --imei 90e5b1aeca9a --feature eval
python host_tool\udp_log_receiver.py --level E --jsonl
```

注意：当前插件使用 UDP，工具端能保证“收到后尽快落盘”，不能保证网络层严格不丢。需要严格不丢时，应在后续版本增加 TCP/ACK 或设备端缓存补传。

详细说明：

- [插件接入说明](docs/integration-guide.md)
- [ESP Component Registry 发布说明](docs/publishing.md)

可选安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File install_esp_component.ps1 -ProjectRoot D:\path\to\your_esp_project
```
