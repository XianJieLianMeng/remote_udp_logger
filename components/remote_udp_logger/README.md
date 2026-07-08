# Remote UDP Logger

[中文说明](README_CN.md)

`remote_udp_logger` mirrors ESP-IDF `ESP_LOGx` output to UDP, so you can watch
device logs on a PC while the device runs on battery with no USB serial cable
attached.

Each UDP line can carry a stable device id and a monotonic sequence number:

```text
[imei=90e5b1aeca9a seq=42] I (2642238) Charge: voltage: 3984, current: 0
```

The companion desktop viewer shows the sender `IP:port`, filters logs by
device id / level / feature, and warns when the sequence number jumps
(possible packet loss).

## Features

- Mirrors `ESP_LOGI` / `ESP_LOGW` / `ESP_LOGE` (and all other levels) to UDP.
- Leaves the local serial console output untouched.
- LAN broadcast target supported: limited broadcast `255.255.255.255:8001` or
  subnet-directed broadcast such as `192.168.1.255:8001` — the host tool needs
  no pairing or fixed IP.
- Unicast to a specific PC supported, e.g. `192.168.1.23:8001`.
- Optional `[imei=<id> seq=<n>]` prefix for multi-device debugging and packet
  loss detection.
- Runtime overrides before `Initialize()`: `SetDeviceId()` and `SetTarget()`.
- Send-failure diagnostics: failures are counted, reported to the local
  console once per 100 occurrences, and queryable via
  `RemoteUdpLogger::GetSendFailureCount()`.

## Getting started

Add the dependency to your project:

```shell
idf.py add-dependency "x-bell/remote_udp_logger"
```

Enable it in `menuconfig` (or `sdkconfig.defaults`):

```text
CONFIG_REMOTE_UDP_LOGGER_ENABLE=y
CONFIG_REMOTE_UDP_LOGGER_TARGET="255.255.255.255:8001"
CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID=y
```

Initialize it early in `app_main()`, after the network stack is available:

```cpp
#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");   // optional
    RemoteUdpLogger::Initialize();

    ESP_LOGI("app", "This log is also mirrored to UDP");
}
```

Only logs produced after `RemoteUdpLogger::Initialize()` are mirrored. UDP is
connectionless: lines logged before Wi-Fi is up are silently lost.

See [examples/basic](examples/basic) for a complete Wi-Fi station project.

## Host-side viewer

A Windows viewer suite (CLI receiver, Qt GUI, browser viewer, UDP-to-TCP
bridge) ships with the plugin repository under `host_tool/`. It is not part of
the managed component. To run the GUI from source:

```powershell
python -m pip install -r host_tool/requirements.txt
python host_tool/udp_log_gui.py --udp-host 0.0.0.0 --udp-port 8001 --auto-start
```

Only one host tool can listen on a UDP port at a time.

## Notes and limitations

- The PC listens on UDP `8001` by default; the device's source port is
  assigned by its network stack.
- Broadcast may be filtered by routers or Windows Firewall. If broadcast is
  unreliable, switch the target to the PC's fixed IP.
- Transport is plain-text UDP with no authentication or encryption, and no
  buffering or retransmission. This component is meant for development and
  diagnostics; do not broadcast sensitive logs in production builds.

## License

MIT — see [LICENSE](LICENSE).
