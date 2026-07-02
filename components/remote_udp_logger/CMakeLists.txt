idf_component_register(
    SRCS "remote_udp_logger.cc"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_netif lwip
)
