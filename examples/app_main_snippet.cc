#include "remote_udp_logger.h"

extern "C" void app_main(void) {
    // Use a stable id if your product has one, for example IMEI or BLE MAC without separators.
    RemoteUdpLogger::SetDeviceId("90e5b1aeca9a");

    // Optional. If omitted, CONFIG_REMOTE_UDP_LOGGER_TARGET is used.
    // RemoteUdpLogger::SetTarget("255.255.255.255:8001");

    // Call as early as possible. Only logs after this call are mirrored to UDP.
    RemoteUdpLogger::Initialize();

    // Continue normal project initialization here.
}
