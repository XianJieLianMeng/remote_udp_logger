#pragma once

#include <string>

class RemoteUdpLogger {
public:
    // Optional. Call before Initialize() if the project has a stable IMEI/device id.
    static void SetDeviceId(const std::string& device_id);

    // Optional. Overrides CONFIG_REMOTE_UDP_LOGGER_TARGET if called before Initialize().
    static void SetTarget(const std::string& ip_port);

    // Hooks ESP_LOG output and mirrors future log lines to UDP.
    static void Initialize();

    static bool IsInitialized();
};
