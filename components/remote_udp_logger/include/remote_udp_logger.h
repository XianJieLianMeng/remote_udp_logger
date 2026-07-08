#pragma once

#include <cstdint>
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

    // Number of UDP send failures since boot. UDP is fire-and-forget, so this
    // is the only signal that the target is unreachable (also reported to the
    // local console once per 100 failures).
    static uint32_t GetSendFailureCount();
};
