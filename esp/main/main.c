#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "nvs_flash.h"
#include "nvs.h"

#include "esp_log.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"

#include "esp_http_server.h"
#include "esp_http_client.h"
#include "esp_spiffs.h"

#include "driver/gpio.h"
#include "driver/spi_master.h"

#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"

#include "lwip/sockets.h"
#include "lwip/inet.h"

#define TAG "esp-weather"

// LCD pinout
#define PIN_NUM_MOSI  6
#define PIN_NUM_CLK   4
#define PIN_NUM_CS    -1
#define PIN_NUM_DC    5
#define PIN_NUM_RST   1
#define PIN_NUM_BKLT  18

#define LCD_HOST      SPI2_HOST
#define LCD_H_RES     240
#define LCD_V_RES     240

#define STRIP_LINES   20
#define SCREEN_COUNT  3
#define SCREEN_BYTES  (LCD_H_RES * LCD_V_RES * 2)

#define WIFI_CONNECT_TIMEOUT_MS 20000

// Config AP
#define AP_SSID       "ESPWX"
#define AP_PASS       "12345678"

#define BASE_URL      "https://lecztomek.github.io/esp-weather"

#define MAX_SCAN_APS 20

static esp_lcd_panel_handle_t panel_handle = NULL;

static EventGroupHandle_t wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1

static int wifi_retry_count = 0;
static const int wifi_max_retries = 20;

static uint16_t linebuf[LCD_H_RES * STRIP_LINES];

static esp_netif_t *sta_netif = NULL;
static esp_netif_t *ap_netif = NULL;

static wifi_ap_record_t scan_records[MAX_SCAN_APS];
static uint16_t scan_count = 0;


// -----------------------------------------------------------------------------
// LCD
// -----------------------------------------------------------------------------

static uint16_t rgb565_swapped(uint8_t r, uint8_t g, uint8_t b)
{
    uint16_t v = ((r & 0xF8) << 8) |
                 ((g & 0xFC) << 3) |
                 (b >> 3);

    return ((v & 0x00FF) << 8) | ((v & 0xFF00) >> 8);
}

static void backlight_on(void)
{
    gpio_config_t cfg = {
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = 1ULL << PIN_NUM_BKLT,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    ESP_ERROR_CHECK(gpio_config(&cfg));

    // GPIO18 LOW = backlight ON
    gpio_set_level(PIN_NUM_BKLT, 0);
}

static void lcd_init(void)
{
    backlight_on();

    spi_bus_config_t buscfg = {
        .sclk_io_num = PIN_NUM_CLK,
        .mosi_io_num = PIN_NUM_MOSI,
        .miso_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = LCD_H_RES * STRIP_LINES * sizeof(uint16_t),
    };

    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_handle_t io_handle = NULL;

    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num = PIN_NUM_DC,
        .cs_gpio_num = PIN_NUM_CS,
        .pclk_hz = 20 * 1000 * 1000,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .spi_mode = 3,
        .trans_queue_depth = 10,
    };

    ESP_ERROR_CHECK(
        esp_lcd_new_panel_io_spi(
            (esp_lcd_spi_bus_handle_t)LCD_HOST,
            &io_config,
            &io_handle
        )
    );

    esp_lcd_panel_dev_config_t panel_config = {
        .reset_gpio_num = PIN_NUM_RST,
        .rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 16,
    };

    ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(io_handle, &panel_config, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));

    vTaskDelay(pdMS_TO_TICKS(100));

    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));

    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_handle, true));
    ESP_ERROR_CHECK(esp_lcd_panel_mirror(panel_handle, false, false));
    ESP_ERROR_CHECK(esp_lcd_panel_swap_xy(panel_handle, false));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));
}

static void lcd_fill(uint16_t color)
{
    for (int i = 0; i < LCD_H_RES * STRIP_LINES; i++) {
        linebuf[i] = color;
    }

    for (int y = 0; y < LCD_V_RES; y += STRIP_LINES) {
        int lines = STRIP_LINES;

        if (y + lines > LCD_V_RES) {
            lines = LCD_V_RES - y;
        }

        esp_lcd_panel_draw_bitmap(
            panel_handle,
            0,
            y,
            LCD_H_RES,
            y + lines,
            linebuf
        );
    }
}

static void display_file(const char *path)
{
    FILE *f = fopen(path, "rb");

    if (!f) {
        ESP_LOGW(TAG, "Cannot open %s", path);
        lcd_fill(rgb565_swapped(20, 30, 45));
        return;
    }

    ESP_LOGI(TAG, "Displaying %s", path);

    for (int y = 0; y < LCD_V_RES; y += STRIP_LINES) {
        int lines = STRIP_LINES;

        if (y + lines > LCD_V_RES) {
            lines = LCD_V_RES - y;
        }

        size_t need = LCD_H_RES * lines * sizeof(uint16_t);
        size_t got = fread(linebuf, 1, need, f);

        if (got != need) {
            ESP_LOGE(TAG, "Short read from %s: got=%u need=%u", path, (unsigned)got, (unsigned)need);
            break;
        }

        esp_lcd_panel_draw_bitmap(
            panel_handle,
            0,
            y,
            LCD_H_RES,
            y + lines,
            linebuf
        );
    }

    fclose(f);
}


// -----------------------------------------------------------------------------
// SPIFFS
// -----------------------------------------------------------------------------

static void spiffs_init(void)
{
    esp_vfs_spiffs_conf_t conf = {
        .base_path = "/spiffs",
        .partition_label = "storage",
        .max_files = 8,
        .format_if_mount_failed = true,
    };

    ESP_ERROR_CHECK(esp_vfs_spiffs_register(&conf));

    size_t total = 0;
    size_t used = 0;

    ESP_ERROR_CHECK(esp_spiffs_info("storage", &total, &used));

    ESP_LOGI(TAG, "SPIFFS total=%u used=%u", (unsigned)total, (unsigned)used);
}

static bool file_exists_and_size_ok(const char *path)
{
    struct stat st;

    if (stat(path, &st) != 0) {
        return false;
    }

    return st.st_size == SCREEN_BYTES;
}


// -----------------------------------------------------------------------------
// NVS WiFi config
// -----------------------------------------------------------------------------

static bool nvs_load_wifi(char *ssid, size_t ssid_len, char *pass, size_t pass_len)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("wifi_cfg", NVS_READONLY, &nvs);

    if (err != ESP_OK) {
        return false;
    }

    size_t s_len = ssid_len;
    size_t p_len = pass_len;

    err = nvs_get_str(nvs, "ssid", ssid, &s_len);
    if (err != ESP_OK) {
        nvs_close(nvs);
        return false;
    }

    err = nvs_get_str(nvs, "pass", pass, &p_len);
    if (err != ESP_OK) {
        pass[0] = '\0';
    }

    nvs_close(nvs);

    return strlen(ssid) > 0;
}

static esp_err_t nvs_save_wifi(const char *ssid, const char *pass)
{
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("wifi_cfg", NVS_READWRITE, &nvs);

    if (err != ESP_OK) {
        return err;
    }

    ESP_ERROR_CHECK(nvs_set_str(nvs, "ssid", ssid));
    ESP_ERROR_CHECK(nvs_set_str(nvs, "pass", pass));
    ESP_ERROR_CHECK(nvs_commit(nvs));

    nvs_close(nvs);

    return ESP_OK;
}


// -----------------------------------------------------------------------------
// WiFi
// -----------------------------------------------------------------------------

static void ensure_sta_netif(void)
{
    if (!sta_netif) {
        sta_netif = esp_netif_create_default_wifi_sta();
    }
}

static void ensure_ap_netif(void)
{
    if (!ap_netif) {
        ap_netif = esp_netif_create_default_wifi_ap();
    }
}

static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data
)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *disc = (wifi_event_sta_disconnected_t *)event_data;

        ESP_LOGW(
            TAG,
            "WiFi disconnected, reason=%d, retry %d/%d",
            disc->reason,
            wifi_retry_count,
            wifi_max_retries
        );

        if (wifi_retry_count < wifi_max_retries) {
            wifi_retry_count++;
            esp_wifi_connect();
        } else {
            xEventGroupSetBits(wifi_event_group, WIFI_FAIL_BIT);
        }
    }

    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));

        wifi_retry_count = 0;
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_base_init(void)
{
    wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());

    esp_err_t err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT,
        ESP_EVENT_ANY_ID,
        &wifi_event_handler,
        NULL,
        NULL
    ));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT,
        IP_EVENT_STA_GOT_IP,
        &wifi_event_handler,
        NULL,
        NULL
    ));
}

static bool wifi_connect_saved(void)
{
    char ssid[64] = {0};
    char pass[128] = {0};

    if (!nvs_load_wifi(ssid, sizeof(ssid), pass, sizeof(pass))) {
        ESP_LOGW(TAG, "No saved WiFi credentials");
        return false;
    }

    ESP_LOGI(TAG, "Trying saved WiFi: %s", ssid);

    ensure_sta_netif();

    wifi_config_t wifi_config = {0};

    strncpy((char *)wifi_config.sta.ssid, ssid, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, pass, sizeof(wifi_config.sta.password) - 1);

    wifi_config.sta.threshold.authmode = WIFI_AUTH_OPEN;
    wifi_config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;

    wifi_retry_count = 0;
    xEventGroupClearBits(wifi_event_group, WIFI_CONNECTED_BIT | WIFI_FAIL_BIT);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(WIFI_CONNECT_TIMEOUT_MS)
    );

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "Connected to WiFi");
        return true;
    }

    ESP_LOGW(TAG, "Could not connect to saved WiFi");

    esp_wifi_stop();
    vTaskDelay(pdMS_TO_TICKS(500));

    return false;
}


// -----------------------------------------------------------------------------
// Config portal helpers
// -----------------------------------------------------------------------------

static void url_decode_inplace(char *s)
{
    char *src = s;
    char *dst = s;

    while (*src) {
        if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else if (*src == '%' && src[1] && src[2]) {
            char hex[3] = {src[1], src[2], 0};
            *dst++ = (char)strtol(hex, NULL, 16);
            src += 3;
        } else {
            *dst++ = *src++;
        }
    }

    *dst = 0;
}

static void html_escape(const char *src, char *dst, size_t dst_len)
{
    size_t j = 0;

    for (size_t i = 0; src[i] && j + 1 < dst_len; i++) {
        const char *rep = NULL;

        switch (src[i]) {
            case '&': rep = "&amp;"; break;
            case '<': rep = "&lt;"; break;
            case '>': rep = "&gt;"; break;
            case '"': rep = "&quot;"; break;
            case '\'': rep = "&#39;"; break;
            default:
                dst[j++] = src[i];
                continue;
        }

        size_t rep_len = strlen(rep);
        if (j + rep_len >= dst_len) {
            break;
        }

        memcpy(dst + j, rep, rep_len);
        j += rep_len;
    }

    dst[j] = 0;
}

static void scan_wifi_networks(void)
{
    ESP_LOGI(TAG, "Scanning WiFi networks for config portal...");

    memset(scan_records, 0, sizeof(scan_records));
    scan_count = 0;

    wifi_scan_config_t scan_config = {
        .ssid = NULL,
        .bssid = NULL,
        .channel = 0,
        .show_hidden = false,
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
        .scan_time.active.min = 100,
        .scan_time.active.max = 500,
    };

    esp_err_t err = esp_wifi_scan_start(&scan_config, true);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "WiFi scan failed: %s", esp_err_to_name(err));
        return;
    }

    uint16_t ap_num = 0;
    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_num(&ap_num));

    scan_count = ap_num;
    if (scan_count > MAX_SCAN_APS) {
        scan_count = MAX_SCAN_APS;
    }

    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_records(&scan_count, scan_records));

    ESP_LOGI(TAG, "Found %d networks", scan_count);

    for (int i = 0; i < scan_count; i++) {
        ESP_LOGI(
            TAG,
            "%d: SSID='%s' RSSI=%d CH=%d AUTH=%d",
            i + 1,
            scan_records[i].ssid,
            scan_records[i].rssi,
            scan_records[i].primary,
            scan_records[i].authmode
        );
    }
}


// -----------------------------------------------------------------------------
// Captive DNS
// -----------------------------------------------------------------------------

static void dns_server_task(void *arg)
{
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);

    if (sock < 0) {
        ESP_LOGE(TAG, "DNS socket failed: errno=%d", errno);
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in server_addr = {
        .sin_family = AF_INET,
        .sin_port = htons(53),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };

    if (bind(sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        ESP_LOGE(TAG, "DNS bind failed: errno=%d", errno);
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Captive DNS started on UDP 53");

    uint8_t rx[512];
    uint8_t tx[512];

    while (1) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);

        int len = recvfrom(
            sock,
            rx,
            sizeof(rx),
            0,
            (struct sockaddr *)&client_addr,
            &client_len
        );

        if (len < 12) {
            continue;
        }

        memset(tx, 0, sizeof(tx));
        memcpy(tx, rx, len);

        // DNS header
        // ID copied
        tx[2] = 0x81; // response, recursion desired/available
        tx[3] = 0x80; // no error

        // QDCOUNT copied from query
        // ANCOUNT = 1
        tx[6] = 0x00;
        tx[7] = 0x01;

        // NSCOUNT = 0, ARCOUNT = 0
        tx[8] = 0x00;
        tx[9] = 0x00;
        tx[10] = 0x00;
        tx[11] = 0x00;

        int pos = len;

        if (pos + 16 > (int)sizeof(tx)) {
            continue;
        }

        // Answer: name pointer to offset 12
        tx[pos++] = 0xC0;
        tx[pos++] = 0x0C;

        // TYPE A
        tx[pos++] = 0x00;
        tx[pos++] = 0x01;

        // CLASS IN
        tx[pos++] = 0x00;
        tx[pos++] = 0x01;

        // TTL 60
        tx[pos++] = 0x00;
        tx[pos++] = 0x00;
        tx[pos++] = 0x00;
        tx[pos++] = 0x3C;

        // RDLENGTH 4
        tx[pos++] = 0x00;
        tx[pos++] = 0x04;

        // 192.168.4.1
        tx[pos++] = 192;
        tx[pos++] = 168;
        tx[pos++] = 4;
        tx[pos++] = 1;

        sendto(
            sock,
            tx,
            pos,
            0,
            (struct sockaddr *)&client_addr,
            client_len
        );
    }
}


// -----------------------------------------------------------------------------
// Config portal HTTP server
// -----------------------------------------------------------------------------

static esp_err_t root_get_handler(httpd_req_t *req)
{
    scan_wifi_networks();

    httpd_resp_set_type(req, "text/html; charset=utf-8");

    httpd_resp_sendstr_chunk(req,
        "<!doctype html>"
        "<html lang='pl'>"
        "<head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>ESP Weather Setup</title>"
        "<style>"
        "body{font-family:sans-serif;background:#eef2f7;padding:24px;color:#111827;}"
        ".card{max-width:420px;margin:auto;background:white;padding:22px;border-radius:18px;box-shadow:0 8px 30px #0002;}"
        "select,input{width:100%;font-size:18px;padding:12px;margin:8px 0 14px;border:1px solid #cbd5e1;border-radius:10px;box-sizing:border-box;}"
        "button{width:100%;font-size:18px;padding:12px;background:#245496;color:white;border:0;border-radius:10px;}"
        ".muted{color:#6b7280;font-size:14px;}"
        "a{color:#245496;}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='card'>"
        "<h1>ESP Weather</h1>"
        "<p>Wybierz siec WiFi i wpisz haslo.</p>"
        "<form action='/save' method='get'>"
        "<label>Siec WiFi</label>"
        "<select name='ssid' required>"
    );

    if (scan_count == 0) {
        httpd_resp_sendstr_chunk(req, "<option value=''>Nie znaleziono sieci</option>");
    } else {
        for (int i = 0; i < scan_count; i++) {
            char ssid_html[96];
            char option[256];

            html_escape((const char *)scan_records[i].ssid, ssid_html, sizeof(ssid_html));

            snprintf(
                option,
                sizeof(option),
                "<option value=\"%s\">%s (%d dBm)</option>",
                ssid_html,
                ssid_html,
                scan_records[i].rssi
            );

            httpd_resp_sendstr_chunk(req, option);
        }
    }

    httpd_resp_sendstr_chunk(req,
        "</select>"
        "<label>Haslo</label>"
        "<input name='pass' type='password'>"
        "<button type='submit'>Zapisz i polacz</button>"
        "</form>"
        "<p class='muted'><a href='/'>Odswiez liste sieci</a></p>"
        "<p class='muted'>AP: ESPWX<br>Haslo: 12345678</p>"
        "</div>"
        "</body>"
        "</html>"
    );

    httpd_resp_sendstr_chunk(req, NULL);

    return ESP_OK;
}

static esp_err_t save_get_handler(httpd_req_t *req)
{
    char query[256] = {0};
    char ssid[64] = {0};
    char pass[128] = {0};

    int qlen = httpd_req_get_url_query_len(req) + 1;

    if (qlen <= 1 || qlen > sizeof(query)) {
        httpd_resp_sendstr(req, "Brak danych");
        return ESP_OK;
    }

    if (httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK) {
        httpd_resp_sendstr(req, "Nie mozna odczytac danych");
        return ESP_OK;
    }

    httpd_query_key_value(query, "ssid", ssid, sizeof(ssid));
    httpd_query_key_value(query, "pass", pass, sizeof(pass));

    url_decode_inplace(ssid);
    url_decode_inplace(pass);

    if (strlen(ssid) == 0) {
        httpd_resp_sendstr(req, "SSID jest puste");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Saving WiFi SSID: %s", ssid);
    ESP_ERROR_CHECK(nvs_save_wifi(ssid, pass));

    const char *html =
        "<!doctype html>"
        "<html lang='pl'>"
        "<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body style='font-family:sans-serif;padding:24px'>"
        "<h1>Zapisano WiFi</h1>"
        "<p>ESP zaraz sie zrestartuje i sprobuje polaczyc z siecia.</p>"
        "</body></html>";

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_send(req, html, HTTPD_RESP_USE_STRLEN);

    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();

    return ESP_OK;
}

static httpd_handle_t start_config_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.uri_match_fn = httpd_uri_match_wildcard;

    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server");
        return NULL;
    }

    httpd_uri_t save_uri = {
        .uri = "/save",
        .method = HTTP_GET,
        .handler = save_get_handler,
        .user_ctx = NULL,
    };

    httpd_uri_t root_uri = {
        .uri = "/*",
        .method = HTTP_GET,
        .handler = root_get_handler,
        .user_ctx = NULL,
    };

    httpd_register_uri_handler(server, &save_uri);
    httpd_register_uri_handler(server, &root_uri);

    return server;
}

static void start_config_ap(void)
{
    ESP_LOGI(TAG, "Starting config AP");

    ensure_ap_netif();
    ensure_sta_netif();

    wifi_config_t ap_config = {0};

    strncpy((char *)ap_config.ap.ssid, AP_SSID, sizeof(ap_config.ap.ssid) - 1);
    strncpy((char *)ap_config.ap.password, AP_PASS, sizeof(ap_config.ap.password) - 1);

    ap_config.ap.ssid_len = strlen(AP_SSID);
    ap_config.ap.channel = 6;
    ap_config.ap.max_connection = 4;
    ap_config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    ap_config.ap.ssid_hidden = 0;
    ap_config.ap.beacon_interval = 100;
    ap_config.ap.pmf_cfg.required = false;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    xTaskCreate(dns_server_task, "dns_server", 4096, NULL, 5, NULL);

    start_config_server();

    ESP_LOGI(TAG, "AP started");
    ESP_LOGI(TAG, "SSID: %s", AP_SSID);
    ESP_LOGI(TAG, "PASS: %s", AP_PASS);
    ESP_LOGI(TAG, "Open: http://192.168.4.1/");
}


// -----------------------------------------------------------------------------
// Download
// -----------------------------------------------------------------------------

static esp_err_t download_file(const char *url, const char *final_path)
{
    char tmp_path[96];
    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", final_path);

    ESP_LOGI(TAG, "Downloading %s", url);

    unlink(tmp_path);

    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 30000,
        .cert_pem = NULL,
        .skip_cert_common_name_check = true,
        .use_global_ca_store = false,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);

    if (!client) {
        ESP_LOGE(TAG, "HTTP client init failed");
        return ESP_FAIL;
    }

    esp_http_client_set_header(client, "User-Agent", "esp-weather");

    FILE *f = fopen(tmp_path, "wb");

    if (!f) {
        ESP_LOGE(TAG, "Cannot open tmp file: %s", tmp_path);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    esp_err_t err = esp_http_client_open(client, 0);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP open failed: %s", esp_err_to_name(err));
        fclose(f);
        unlink(tmp_path);
        esp_http_client_cleanup(client);
        return err;
    }

    int content_length = esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);

    ESP_LOGI(TAG, "HTTP status=%d content_length=%d", status, content_length);

    if (status != 200) {
        ESP_LOGE(TAG, "Bad HTTP status: %d", status);
        fclose(f);
        unlink(tmp_path);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return ESP_FAIL;
    }

    char buf[1024];
    int total = 0;

    while (1) {
        int len = esp_http_client_read(client, buf, sizeof(buf));

        if (len < 0) {
            ESP_LOGE(TAG, "HTTP read failed");
            fclose(f);
            unlink(tmp_path);
            esp_http_client_close(client);
            esp_http_client_cleanup(client);
            return ESP_FAIL;
        }

        if (len == 0) {
            break;
        }

        size_t written = fwrite(buf, 1, len, f);

        if (written != len) {
            ESP_LOGE(TAG, "File write failed");
            fclose(f);
            unlink(tmp_path);
            esp_http_client_close(client);
            esp_http_client_cleanup(client);
            return ESP_FAIL;
        }

        total += len;
    }

    fclose(f);

    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    ESP_LOGI(TAG, "Downloaded %d bytes, status=%d", total, status);

    if (status != 200) {
        ESP_LOGE(TAG, "Bad HTTP status: %d", status);
        unlink(tmp_path);
        return ESP_FAIL;
    }

    if (total != SCREEN_BYTES) {
        ESP_LOGE(TAG, "Wrong file size: %d, expected %d", total, SCREEN_BYTES);
        unlink(tmp_path);
        return ESP_FAIL;
    }

    unlink(final_path);

    if (rename(tmp_path, final_path) != 0) {
        ESP_LOGE(TAG, "Rename failed: %s -> %s", tmp_path, final_path);
        unlink(tmp_path);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Saved %s", final_path);

    return ESP_OK;
}

static void download_all_screens(void)
{
    for (int i = 0; i < SCREEN_COUNT; i++) {
        char url[160];
        char path[64];

        snprintf(url, sizeof(url), BASE_URL "/screen_%d.rgb565", i);
        snprintf(path, sizeof(path), "/spiffs/screen_%d.rgb565", i);

        esp_err_t err = download_file(url, path);

        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Download failed for screen %d: %s", i, esp_err_to_name(err));
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void download_task(void *arg)
{
    while (1) {
        EventBits_t bits = xEventGroupGetBits(wifi_event_group);

        if (bits & WIFI_CONNECTED_BIT) {
            download_all_screens();
        } else {
            ESP_LOGW(TAG, "No WiFi, skipping download");
        }

        vTaskDelay(pdMS_TO_TICKS(60 * 60 * 1000));
    }
}


// -----------------------------------------------------------------------------
// Display loop
// -----------------------------------------------------------------------------

static void display_task(void *arg)
{
    int screen = 0;

    while (1) {
        char path[64];

        snprintf(path, sizeof(path), "/spiffs/screen_%d.rgb565", screen);

        if (file_exists_and_size_ok(path)) {
            display_file(path);
        } else {
            ESP_LOGW(TAG, "Missing screen file: %s", path);
            lcd_fill(rgb565_swapped(20, 30, 45));
        }

        screen = (screen + 1) % SCREEN_COUNT;

        vTaskDelay(pdMS_TO_TICKS(15000));
    }
}


// -----------------------------------------------------------------------------
// app_main
// -----------------------------------------------------------------------------

void app_main(void)
{
    printf("\n\n=== ESP WEATHER DISPLAY ===\n");

    esp_err_t ret = nvs_flash_init();

    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(ret);
    }

    lcd_init();
    lcd_fill(rgb565_swapped(20, 30, 45));

    spiffs_init();

    wifi_base_init();

    bool connected = wifi_connect_saved();

    if (!connected) {
        start_config_ap();

        while (1) {
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }

    xTaskCreate(display_task, "display_task", 4096, NULL, 5, NULL);
    xTaskCreate(download_task, "download_task", 16384, NULL, 4, NULL);
}
