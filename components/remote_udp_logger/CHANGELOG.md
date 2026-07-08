# Changelog

All notable changes to the `remote_udp_logger` component are documented here.
Versioning follows [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-07-08

- Enable `SO_BROADCAST` for subnet-directed broadcast targets such as
  `192.168.1.255` (previously only the literal `255.255.255.255` worked).
- Count UDP send failures and report them on the local console once per 100
  failures; new `RemoteUdpLogger::GetSendFailureCount()` diagnostic API.

## [0.1.0] - 2026-07-08

Initial release.

- Mirror ESP-IDF `ESP_LOGx` output to UDP via `esp_log_set_vprintf()`,
  without affecting the local serial console.
- Kconfig options: enable switch, target `IP:PORT` (LAN broadcast
  `255.255.255.255:8001` by default), optional `[imei=<id> seq=<n>]` line
  prefix, configurable line/packet buffer sizes.
- Runtime overrides before `Initialize()`: `SetDeviceId()`, `SetTarget()`.
- Monotonic per-line `seq` counter so host tools can detect packet loss.
- `examples/basic`: Wi-Fi station + logger bring-up demo.
- Companion Windows host tools (CLI receiver / Qt GUI / browser viewer /
  UDP-to-TCP bridge) shipped in the plugin's `host_tool/` directory
  (not part of the managed component).

Known limitations (by design, see README):

- Plain-text UDP, no authentication or encryption — development and
  diagnostics use only; do not broadcast sensitive logs in production.
- Fire-and-forget: no buffering or retransmission; lines logged before the
  network is up are lost.
