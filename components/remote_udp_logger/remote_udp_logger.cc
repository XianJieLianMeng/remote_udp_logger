#include "remote_udp_logger.h"

#include <esp_err.h>
#include <esp_log.h>
#include <esp_netif.h>

#if CONFIG_REMOTE_UDP_LOGGER_ENABLE

#include <arpa/inet.h>
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <unistd.h>

namespace {

constexpr const char* kTag = "RemoteUdpLogger";
constexpr const char* kUnknownDeviceId = "unknown";

class RemoteUdpLoggerImpl {
public:
    static void SetDeviceId(const std::string& device_id) {
        if (!initialized_ && !device_id.empty()) {
            device_id_ = device_id;
        }
    }

    static void SetTarget(const std::string& ip_port) {
        if (!initialized_ && !ip_port.empty()) {
            target_override_ = ip_port;
        }
    }

    static void Initialize() {
        if (initialized_) {
            return;
        }

        esp_err_t netif_ret = esp_netif_init();
        if (netif_ret != ESP_OK && netif_ret != ESP_ERR_INVALID_STATE) {
            ESP_LOGE(kTag, "Failed to initialize esp-netif: %s", esp_err_to_name(netif_ret));
            return;
        }

        InitializeDeviceId();
        InitializeSocket();

        previous_vprintf_ = esp_log_set_vprintf(&RemoteVprintf);
        initialized_ = true;
    }

    static bool IsInitialized() {
        return initialized_;
    }

    static uint32_t GetSendFailureCount() {
        return send_failure_count_;
    }

private:
    static int RemoteVprintf(const char* fmt, va_list args) {
        va_list console_args;
        va_copy(console_args, args);
        const int ret =
            previous_vprintf_ != nullptr ? previous_vprintf_(fmt, console_args) : vprintf(fmt, console_args);
        va_end(console_args);

        if (udp_sockfd_ < 0 || !target_addr_valid_) {
            return ret;
        }

        char line_buffer[CONFIG_REMOTE_UDP_LOGGER_LINE_BUFFER_SIZE];
        va_list remote_args;
        va_copy(remote_args, args);
        const int formatted = vsnprintf(line_buffer, sizeof(line_buffer), fmt, remote_args);
        va_end(remote_args);

        if (formatted <= 0) {
            return ret;
        }

        const size_t line_len = static_cast<size_t>(
            formatted < static_cast<int>(sizeof(line_buffer)) ? formatted : sizeof(line_buffer) - 1);

#if CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID
        char packet_buffer[CONFIG_REMOTE_UDP_LOGGER_PACKET_BUFFER_SIZE];
        const char* device_id = device_id_.empty() ? kUnknownDeviceId : device_id_.c_str();
        const uint32_t seq = next_sequence_++;
        const int packet_len = snprintf(packet_buffer, sizeof(packet_buffer),
                                        "[imei=%s seq=%lu] %.*s", device_id,
                                        static_cast<unsigned long>(seq),
                                        static_cast<int>(line_len), line_buffer);
        if (packet_len <= 0) {
            return ret;
        }
        const size_t send_len = static_cast<size_t>(
            packet_len < static_cast<int>(sizeof(packet_buffer)) ? packet_len : sizeof(packet_buffer) - 1);
        const char* send_buffer = packet_buffer;
#else
        const size_t send_len = line_len;
        const char* send_buffer = line_buffer;
#endif

        const ssize_t sent = sendto(udp_sockfd_, send_buffer, send_len, 0,
                                    reinterpret_cast<const struct sockaddr*>(&target_addr_),
                                    sizeof(target_addr_));
        if (sent < 0) {
            ++send_failure_count_;
            // Plain printf: going through ESP_LOG here would recurse back into
            // this vprintf hook.
            if (send_failure_count_ == 1 || send_failure_count_ % 100 == 0) {
                printf("W %s: UDP log send failed %lu times, last errno=%d\n", kTag,
                       static_cast<unsigned long>(send_failure_count_), errno);
            }
        }
        return ret;
    }

    static void InitializeDeviceId() {
#if CONFIG_REMOTE_UDP_LOGGER_INCLUDE_DEVICE_ID
        if (device_id_.empty()) {
            device_id_ = CONFIG_REMOTE_UDP_LOGGER_DEVICE_ID;
        }
        if (device_id_.empty()) {
            device_id_ = kUnknownDeviceId;
        }
#endif
    }

    static void InitializeSocket() {
        std::string target = target_override_.empty() ? std::string(CONFIG_REMOTE_UDP_LOGGER_TARGET) : target_override_;
        const size_t colon_pos = target.find(':');
        if (colon_pos == std::string::npos) {
            ESP_LOGW(kTag, "Invalid UDP target, expected IP:PORT: %s", target.c_str());
            return;
        }

        const std::string ip = target.substr(0, colon_pos);
        const std::string port_text = target.substr(colon_pos + 1);
        if (ip.empty() || port_text.empty()) {
            ESP_LOGW(kTag, "Invalid UDP target, empty IP or port: %s", target.c_str());
            return;
        }

        char* end = nullptr;
        const long port = strtol(port_text.c_str(), &end, 10);
        if (end == port_text.c_str() || end == nullptr || *end != '\0' || port <= 0 || port > 65535) {
            ESP_LOGW(kTag, "Invalid UDP target port: %s", target.c_str());
            return;
        }

        udp_sockfd_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
        if (udp_sockfd_ < 0) {
            ESP_LOGW(kTag, "Failed to create UDP socket");
            return;
        }

        memset(&target_addr_, 0, sizeof(target_addr_));
        target_addr_.sin_family = AF_INET;
        target_addr_.sin_port = htons(static_cast<uint16_t>(port));

        if (inet_pton(AF_INET, ip.c_str(), &target_addr_.sin_addr) != 1) {
            ESP_LOGW(kTag, "Invalid UDP target IP: %s", ip.c_str());
            close(udp_sockfd_);
            udp_sockfd_ = -1;
            return;
        }

        // Allow both the limited broadcast (255.255.255.255) and
        // subnet-directed broadcasts such as 192.168.1.255. SO_BROADCAST only
        // grants permission to send broadcast; it is harmless for a unicast
        // host address that merely ends in .255.
        if ((ntohl(target_addr_.sin_addr.s_addr) & 0xFF) == 0xFF) {
            const int enable_broadcast = 1;
            setsockopt(udp_sockfd_, SOL_SOCKET, SO_BROADCAST, &enable_broadcast, sizeof(enable_broadcast));
        }

        target_addr_valid_ = true;
    }

    inline static bool initialized_ = false;
    inline static int udp_sockfd_ = -1;
    inline static bool target_addr_valid_ = false;
    inline static struct sockaddr_in target_addr_ = {};
    inline static vprintf_like_t previous_vprintf_ = nullptr;
    inline static std::string device_id_;
    inline static std::string target_override_;
    inline static uint32_t next_sequence_ = 1;
    inline static uint32_t send_failure_count_ = 0;
};

}  // namespace

#endif  // CONFIG_REMOTE_UDP_LOGGER_ENABLE

void RemoteUdpLogger::SetDeviceId(const std::string& device_id) {
#if CONFIG_REMOTE_UDP_LOGGER_ENABLE
    RemoteUdpLoggerImpl::SetDeviceId(device_id);
#else
    (void)device_id;
#endif
}

void RemoteUdpLogger::SetTarget(const std::string& ip_port) {
#if CONFIG_REMOTE_UDP_LOGGER_ENABLE
    RemoteUdpLoggerImpl::SetTarget(ip_port);
#else
    (void)ip_port;
#endif
}

void RemoteUdpLogger::Initialize() {
#if CONFIG_REMOTE_UDP_LOGGER_ENABLE
    RemoteUdpLoggerImpl::Initialize();
#endif
}

bool RemoteUdpLogger::IsInitialized() {
#if CONFIG_REMOTE_UDP_LOGGER_ENABLE
    return RemoteUdpLoggerImpl::IsInitialized();
#else
    return false;
#endif
}

uint32_t RemoteUdpLogger::GetSendFailureCount() {
#if CONFIG_REMOTE_UDP_LOGGER_ENABLE
    return RemoteUdpLoggerImpl::GetSendFailureCount();
#else
    return 0;
#endif
}
