#include <stdio.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"
#include "driver/spi_master.h"

#include "esp_log.h"
#include "esp_err.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_panel_ops.h"

#include "image_rgb565.h"

#define TAG "image-display"

// Pinout wyciągnięty z fabrycznego firmware
#define PIN_NUM_MOSI  6
#define PIN_NUM_CLK   4
#define PIN_NUM_CS    -1
#define PIN_NUM_DC    5
#define PIN_NUM_RST   1
#define PIN_NUM_BKLT  18

#define LCD_HOST      SPI2_HOST
#define LCD_H_RES     240
#define LCD_V_RES     240

static esp_lcd_panel_handle_t panel_handle = NULL;

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

    // GPIO18 LOW = podświetlenie ON
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
        .max_transfer_sz = LCD_H_RES * 80 * sizeof(uint16_t),
    };

    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_handle_t io_handle = NULL;

    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num = PIN_NUM_DC,
        .cs_gpio_num = PIN_NUM_CS,
        .pclk_hz = 20 * 1000 * 1000,

        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,

        // Fabryczny firmware używa SPI mode 3
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

static void draw_image(void)
{
    esp_lcd_panel_draw_bitmap(
        panel_handle,
        0,
        0,
        LCD_H_RES,
        LCD_V_RES,
        image_rgb565
    );
}

void app_main(void)
{
    printf("\n\n=== IMAGE DISPLAY ===\n");

    lcd_init();

    draw_image();

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
