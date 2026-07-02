idf_component_register(
    SRCS "main.cc"
    INCLUDE_DIRS "."
    REQUIRES remote_udp_logger esp_wifi nvs_flash esp_event esp_netif
)
