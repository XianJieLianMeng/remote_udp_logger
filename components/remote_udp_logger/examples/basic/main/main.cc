#include <cstring>

#include <esp_event.h>
#include <esp_log.h>
#include <esp_netif.h>
#include <esp_wifi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/event_groups.h>
#include <freertos/task.h>
#include <nvs_flash.h>

#include "remote_udp_logger.h"

namespace {

constexpr const char* kTag = "basic";
constexpr EventBits_t kWifiConnectedBit = BIT0;
constexpr EventBits_t kWifiFailBit = BIT1;

EventGroupHandle_t wifi_event_group;
int wifi_retry_count = 0;

void WifiEventHandler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (wifi_retry_count < CONFIG_EXAMPLE_WIFI_MAXIMUM_RETRY) {
            esp_wifi_connect();
            wifi_retry_count++;
            ESP_LOGI(kTag, "Retrying Wi-Fi connection");
        } else {
            xEventGroupSetBits(wifi_event_group, kWifiFailBit);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t* event = static_cast<const ip_event_got_ip_t*>(event_data);
        ESP_LOGI(kTag, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        wifi_retry_count = 0;
        xEventGroupSetBits(wifi_event_group, kWifiConnectedBit);
    }
}

void InitializeNvs() {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
}

bool ConnectWifi() {
    if (std::strlen(CONFIG_EXAMPLE_WIFI_SSID) == 0) {
        ESP_LOGW(kTag, "CONFIG_EXAMPLE_WIFI_SSID is empty. Configure Wi-Fi before expecting UDP logs.");
        return false;
    }

    wifi_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t wifi_event_handler;
    esp_event_handler_instance_t ip_event_handler;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &WifiEventHandler, nullptr, &wifi_event_handler));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &WifiEventHandler, nullptr, &ip_event_handler));

    wifi_config_t wifi_config = {};
    std::strncpy(reinterpret_cast<char*>(wifi_config.sta.ssid), CONFIG_EXAMPLE_WIFI_SSID,
                 sizeof(wifi_config.sta.ssid) - 1);
    std::strncpy(reinterpret_cast<char*>(wifi_config.sta.password), CONFIG_EXAMPLE_WIFI_PASSWORD,
                 sizeof(wifi_config.sta.password) - 1);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    const EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group, kWifiConnectedBit | kWifiFailBit, pdFALSE, pdFALSE, pdMS_TO_TICKS(15000));

    if ((bits & kWifiConnectedBit) != 0) {
        return true;
    }

    ESP_LOGW(kTag, "Wi-Fi connection failed or timed out");
    return false;
}

}  // namespace

extern "C" void app_main(void) {
    InitializeNvs();
    ConnectWifi();

    RemoteUdpLogger::SetDeviceId("example-001");
    RemoteUdpLogger::Initialize();

    uint32_t count = 0;
    while (true) {
        ESP_LOGI(kTag, "Remote UDP log tick %lu", static_cast<unsigned long>(count++));
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
