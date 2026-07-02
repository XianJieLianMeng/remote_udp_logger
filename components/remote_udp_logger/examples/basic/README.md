# Remote UDP Logger 基础示例

这个示例会连接 Wi-Fi，初始化 `remote_udp_logger`，设置一个演示用设备 ID，并每秒打印一行日志。

先配置 Wi-Fi：

```powershell
idf.py menuconfig
```

然后设置：

```text
Remote UDP Logger Basic Example -> Wi-Fi SSID
Remote UDP Logger Basic Example -> Wi-Fi password
```

编译并烧录：

```powershell
idf.py set-target esp32s3
idf.py build flash monitor
```

在电脑上运行桌面查看器，或启动任何监听 UDP `8001` 的接收器。

预期 UDP 日志格式：

```text
[imei=example-001] I (...) basic: Remote UDP log tick ...
```
