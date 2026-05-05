#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_log.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#define TAG "wifi-scan"

static wifi_ap_record_t records[30];

void app_main(void)
{
    printf("\n\n=== WIFI SCAN TEST ===\n");

    esp_err_t ret = nvs_flash_init();

    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(ret);
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    while (1) {
        ESP_LOGI(TAG, "Scanning...");

        wifi_scan_config_t scan_config = {
            .ssid = NULL,
            .bssid = NULL,
            .channel = 0,
            .show_hidden = true,
            .scan_type = WIFI_SCAN_TYPE_ACTIVE,
            .scan_time.active.min = 100,
            .scan_time.active.max = 500,
        };

        esp_err_t err = esp_wifi_scan_start(&scan_config, true);

        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Scan start failed: %s", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(10000));
            continue;
        }

        uint16_t ap_count = 0;
        ESP_ERROR_CHECK(esp_wifi_scan_get_ap_num(&ap_count));

        ESP_LOGI(TAG, "Found %d networks", ap_count);

        uint16_t number = 30;
        ESP_ERROR_CHECK(esp_wifi_scan_get_ap_records(&number, records));

        for (int i = 0; i < number; i++) {
            ESP_LOGI(
                TAG,
                "%2d: SSID='%s' RSSI=%d CH=%d AUTH=%d",
                i + 1,
                records[i].ssid,
                records[i].rssi,
                records[i].primary,
                records[i].authmode
            );
        }

        ESP_LOGI(TAG, "Scan done, waiting...");
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
