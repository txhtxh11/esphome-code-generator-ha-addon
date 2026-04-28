"""ESPHome Code Generator - Web UI for generating YAML configurations.

This module adds a new page to the ESPHome Dashboard that allows users
to visually configure sensors, switches, lights, etc. and generate
the corresponding YAML configuration file.

Usage: This file replaces the original web_server.py's make_app() to add
the /generate route and CodeGeneratorHandler.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import tornado.web

_LOGGER = logging.getLogger(__name__)

# Template for generating basic ESPHome YAML
DEVICE_TEMPLATE = """esphome:
  name: {name}
  friendly_name: {friendly_name}

{platform_section}

# Enable logging
logger:

# Enable Home Assistant API
api:
  encryption:
    key: "{api_key}"

ota:
  - platform: esphome
    password: "{ota_password}"

wifi:
  ssid: "{wifi_ssid}"
  password: "{wifi_password}"

  # Enable fallback hotspot (captive portal) in case wifi connection fails
  ap:
    ssid: "{fallback_name}"
    password: "{fallback_psk}"

captive_portal:

# Device specific configuration
{substitutions}

{sensor_block}

{binary_sensor_block}

{switch_block}

{light_block}

{output_block}

{text_sensor_block}

{button_block}

{number_block}

{select_block}

{cover_block}

{climate_block}

{fan_block}

{display_block}
"""


PLATFORM_CONFIGS = {
    "ESP8266": "esp8266:\n  board: {board}",
    "ESP32": "esp32:\n  board: {board}\n  framework:\n    type: esp-idf",
    "RP2040": "rp2040:\n  board: {board}",
    "BK72XX": "bk72xx:\n  board: {board}",
    "LN882X": "ln882x:\n  board: {board}",
    "RTL87XX": "rtl87xx:\n  board: {board}",
}

SENSOR_TYPES = {
    # (type_key, display_name, unit, icon)
    "dht": {"name": "DHT11/DHT22 (温湿度)", "components": ["temperature", "humidity"]},
    "dallas": {"name": "DS18B20 (温度传感器)", "components": ["temperature"]},
    "bmp180": {"name": "BMP180 (气压/温度)", "components": ["temperature", "pressure"]},
    "bme280": {"name": "BME280 (温湿度/气压)", "components": ["temperature", "pressure", "humidity"]},
    "bme680": {"name": "BME680 (温湿气压/VOC)", "components": ["temperature", "pressure", "humidity", "gas_resistance"]},
    "sht3xd": {"name": "SHT3x (温湿度)", "components": ["temperature", "humidity"]},
    "ds18b20_onewire": {"name": "DS18B20 (单总线, 多路)", "components": ["temperature*"]},
    "hcsr04": {"name": "HC-SR04 (超声波距离)", "components": ["distance"]},
    "ultrasonic": {"name": "超声波传感器 (距离)", "components": ["distance"]},
    "pmsx003": {"name": "PMSx003 (颗粒物/PM)", "components": ["pm_1_0", "pm_2_5", "pm_10_0"]},
    "mhz19": {"name": "MH-Z19 (CO2)", "components": ["co2", "temperature"]},
    "scd4x": {"name": "SCD4x (CO2/温湿度)", "components": ["co2", "temperature", "humidity"]},
    "ina219": {"name": "INA219 (电流/电压/功率)", "components": ["bus_voltage", "shunt_voltage", "current", "power"]},
    "ina3221": {"name": "INA3221 (三通道电流)", "components": ["current_1", "current_2", "current_3"]},
    "max31855": {"name": "MAX31855 (热电偶温度)", "components": ["temperature"]},
    "max6675": {"name": "MAX6675 (热电偶温度)", "components": ["temperature"]},
    "ads1115": {"name": "ADS1115 (ADC/电压)", "components": ["voltage*"]},
    "adc": {"name": "内置 ADC (模拟输入)", "components": ["voltage*"]},
    "hlw8012": {"name": "HLW8012 (电量测量)", "components": ["voltage", "current", "power"]},
    "apds9960": {"name": "APDS9960 (颜色/手势)", "components": ["r", "g", "b", "c"]},
    "tcs34725": {"name": "TCS34725 (颜色传感器)", "components": ["r", "g", "b", "c"]},
    "vl53l0x": {"name": "VL53L0X (激光测距)", "components": ["distance"]},
    "rc522": {"name": "RC522 (RFID读卡器)", "components": ["tag*"]},
    "mpu6050": {"name": "MPU6050 (6轴陀螺仪)", "components": ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]},
}

BINARY_SENSOR_TYPES = {
    "gpio": {"name": "GPIO 按键/开关", "config": "binary_sensor:\n  - platform: gpio\n    pin: GPIO{pin}\n    name: \"{name}\"\n    device_class: {device_class}"},
    "pulse_counter": {"name": "脉冲计数器", "config": "binary_sensor:\n  - platform: gpio\n    pin: GPIO{pin}\n    name: \"{name}\"\n    filters:\n      - delayed_on_off: 50ms"},
    "status": {"name": "ESPHome 连接状态", "config": "binary_sensor:\n  - platform: status\n    name: \"{name}\""},
}

SWITCH_TYPES = {
    "gpio": {"name": "GPIO 开关", "config": "switch:\n  - platform: gpio\n    name: \"{name}\"\n    pin: GPIO{pin}\n    restore_mode: {restore}"},
    "relay": {"name": "继电器", "config": "switch:\n  - platform: gpio\n    name: \"{name}\"\n    pin: GPIO{pin}\n    id: relay_{id}\n    restore_mode: {restore}"},
    "output": {"name": "Output 开关(Light等)", "config": "switch:\n  - platform: output\n    name: \"{name}\"\n    output_id: {output_id}\n    restore_mode: {restore}"},
}

LIGHT_TYPES = {
    "binary": {"name": "单色开关灯", "config": "light:\n  - platform: binary\n    name: \"{name}\"\n    output: light_output_{id}"},
    "monochromatic": {"name": "暖白调光灯", "config": "light:\n  - platform: monochromatic\n    name: \"{name}\"\n    output: light_output_{id}\n    gamma_correct: 2.8\n    default_transition_length: 1s"},
    "rgb": {"name": "RGB 彩灯", "config": "light:\n  - platform: rgb\n    name: \"{name}\"\n    red: light_output_{id}_r\n    green: light_output_{id}_g\n    blue: light_output_{id}_b\n    gamma_correct: 2.8\n    default_transition_length: 0.5s"},
    "rgbw": {"name": "RGBW 彩灯(含白)", "config": "light:\n  - platform: rgbw\n    name: \"{name}\"\n    red: light_output_{id}_r\n    green: light_output_{id}_g\n    blue: light_output_{id}_b\n    white: light_output_{id}_w\n    gamma_correct: 2.8\n    default_transition_length: 0.5s"},
    "neopixel": {"name": "WS2812/NeoPixel 灯带", "config": "light:\n  - platform: neopixelbus\n    name: \"{name}\"\n    type: GRB\n    variant: WS2812\n    pin: GPIO{pin}\n    num_leds: {num_leds}\n    method: esp32_rmt\n    gamma_correct: 2.8\n    default_transition_length: 0.5s"},
}


def _gen_sensor_yaml(sensor_configs: list[dict]) -> str:
    """Generate YAML for sensor components."""
    if not sensor_configs:
        return ""

    parts = ["# Sensors", "sensor:"]

    # Group by sensor type for proper generation
    for cfg in sensor_configs:
        s_type = cfg["type"]
        s_name = cfg.get("name", s_type)
        s_pin = cfg.get("pin", "")

        if s_type == "dht":
            parts.append(f"  - platform: dht")
            parts.append(f"    pin: GPIO{s_pin}")
            parts.append(f"    model: DHT22")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    humidity:")
            parts.append(f"      name: \"{s_name} Humidity\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "dallas":
            parts.append(f"  - platform: dallas_temp")
            parts.append(f"    address: {cfg.get('address', '0x0000000000000000')}")
            parts.append(f"    name: \"{s_name} Temperature\"")

        elif s_type == "bmp180":
            parts.append(f"  - platform: bmp180")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    pressure:")
            parts.append(f"      name: \"{s_name} Pressure\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "bme280":
            parts.append(f"  - platform: bme280")
            parts.append(f"    address: 0x76")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    pressure:")
            parts.append(f"      name: \"{s_name} Pressure\"")
            parts.append(f"    humidity:")
            parts.append(f"      name: \"{s_name} Humidity\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "bme680":
            parts.append(f"  - platform: bme680")
            parts.append(f"    address: 0x76")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    pressure:")
            parts.append(f"      name: \"{s_name} Pressure\"")
            parts.append(f"    humidity:")
            parts.append(f"      name: \"{s_name} Humidity\"")
            parts.append(f"    gas_resistance:")
            parts.append(f"      name: \"{s_name} Gas Resistance\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "sht3xd":
            parts.append(f"  - platform: sht3xd")
            parts.append(f"    address: 0x44")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    humidity:")
            parts.append(f"      name: \"{s_name} Humidity\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "ds18b20_onewire":
            parts.append(f"  # One wire bus for DS18B20")
            parts.append(f"  - platform: dallas_temp")
            if s_pin:
                parts.append(f"    pin: GPIO{s_pin}")
            parts.append(f"    name: \"{s_name} Temperature\"")

        elif s_type == "hcsr04" or s_type == "ultrasonic":
            parts.append(f"  - platform: ultrasonic")
            parts.append(f"    trigger_pin: GPIO{cfg.get('trigger_pin', s_pin)}")
            parts.append(f"    echo_pin: GPIO{cfg.get('echo_pin', '')}")
            parts.append(f"    name: \"{s_name} Distance\"")
            parts.append(f"    update_interval: 10s")

        elif s_type == "pmsx003":
            parts.append(f"  - platform: pmsx003")
            parts.append(f"    type: PMS5003")
            parts.append(f"    uart_id: uart_{s_name.lower().replace(' ', '_')}")
            parts.append(f"    pm_1_0:")
            parts.append(f"      name: \"{s_name} PM1.0\"")
            parts.append(f"    pm_2_5:")
            parts.append(f"      name: \"{s_name} PM2.5\"")
            parts.append(f"    pm_10_0:")
            parts.append(f"      name: \"{s_name} PM10.0\"")

        elif s_type == "mhz19":
            parts.append(f"  - platform: mhz19")
            parts.append(f"    uart_id: uart_{s_name.lower().replace(' ', '_')}")
            parts.append(f"    co2:")
            parts.append(f"      name: \"{s_name} CO2\"")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")

        elif s_type == "scd4x":
            parts.append(f"  - platform: scd4x")
            parts.append(f"    co2:")
            parts.append(f"      name: \"{s_name} CO2\"")
            parts.append(f"    temperature:")
            parts.append(f"      name: \"{s_name} Temperature\"")
            parts.append(f"    humidity:")
            parts.append(f"      name: \"{s_name} Humidity\"")
            parts.append(f"    update_interval: 60s")

        elif s_type == "ina219":
            parts.append(f"  - platform: ina219")
            parts.append(f"    address: 0x40")
            parts.append(f"    shunt_resistance: 0.1 ohm")
            parts.append(f"    bus_voltage:")
            parts.append(f"      name: \"{s_name} Bus Voltage\"")
            parts.append(f"    shunt_voltage:")
            parts.append(f"      name: \"{s_name} Shunt Voltage\"")
            parts.append(f"    current:")
            parts.append(f"      name: \"{s_name} Current\"")
            parts.append(f"    power:")
            parts.append(f"      name: \"{s_name} Power\"")

        elif s_type == "ina3221":
            parts.append(f"  - platform: ina3221")
            parts.append(f"    address: 0x40")
            for ch in range(1, 4):
                parts.append(f"    channel_{ch}:")
                parts.append(f"      name: \"{s_name} Channel {ch} Current\"")

        elif s_type == "max31855":
            parts.append(f"  - platform: max31855")
            parts.append(f"    cs_pin: GPIO{cfg.get('cs_pin', s_pin)}")
            parts.append(f"    name: \"{s_name} Temperature\"")

        elif s_type == "max6675":
            parts.append(f"  - platform: max6675")
            parts.append(f"    cs_pin: GPIO{cfg.get('cs_pin', s_pin)}")
            parts.append(f"    name: \"{s_name} Temperature\"")

        elif s_type == "ads1115":
            parts.append(f"  - platform: ads1115")
            parts.append(f"    address: 0x48")
            parts.append(f"    multiplexer: {cfg.get('multiplexer', 'A0_GND')}")
            parts.append(f"    gain: 4.096")
            parts.append(f"    name: \"{s_name} Voltage\"")

        elif s_type == "adc":
            parts.append(f"  - platform: adc")
            parts.append(f"    pin: GPIO{s_pin}")
            parts.append(f"    name: \"{s_name} Voltage\"")

        elif s_type == "hlw8012":
            parts.append(f"  - platform: hlw8012")
            parts.append(f"    sel_pin: GPIO{cfg.get('sel_pin', '')}")
            parts.append(f"    cf_pin: GPIO{cfg.get('cf_pin', '')}")
            parts.append(f"    cf1_pin: GPIO{cfg.get('cf1_pin', '')}")
            parts.append(f"    voltage:")
            parts.append(f"      name: \"{s_name} Voltage\"")
            parts.append(f"    current:")
            parts.append(f"      name: \"{s_name} Current\"")
            parts.append(f"    power:")
            parts.append(f"      name: \"{s_name} Power\"")

        elif s_type == "apds9960":
            parts.append(f"  - platform: apds9960")
            parts.append(f"    address: 0x39")
            parts.append(f"    update_interval: 10s")
            parts.append(f"    red:")
            parts.append(f"      name: \"{s_name} Red\"")
            parts.append(f"    green:")
            parts.append(f"      name: \"{s_name} Green\"")
            parts.append(f"    blue:")
            parts.append(f"      name: \"{s_name} Blue\"")
            parts.append(f"    clear:")
            parts.append(f"      name: \"{s_name} Clear\"")

        elif s_type == "tcs34725":
            parts.append(f"  - platform: tcs34725")
            parts.append(f"    address: 0x29")
            parts.append(f"    update_interval: 10s")
            parts.append(f"    red:")
            parts.append(f"      name: \"{s_name} Red\"")
            parts.append(f"    green:")
            parts.append(f"      name: \"{s_name} Green\"")
            parts.append(f"    blue:")
            parts.append(f"      name: \"{s_name} Blue\"")
            parts.append(f"    clear:")
            parts.append(f"      name: \"{s_name} Clear\"")

        elif s_type == "vl53l0x":
            parts.append(f"  - platform: vl53l0x")
            parts.append(f"    name: \"{s_name} Distance\"")
            parts.append(f"    update_interval: 10s")

        elif s_type == "rc522":
            parts.append(f"  # RC522 requires SPI bus configuration")
            parts.append(f"  - platform: rc522")
            parts.append(f"    cs_pin: GPIO{cfg.get('cs_pin', '5')}")
            parts.append(f"    on_tag:")
            parts.append(f"      then:")
            parts.append(f"        - homeassistant.tag_scanned: !lambda 'return x;'")

        elif s_type == "mpu6050":
            parts.append(f"  - platform: mpu6050")
            parts.append(f"    address: 0x68")
            parts.append(f"    update_interval: 10s")
            parts.append(f"    accel_x:")
            parts.append(f"      name: \"{s_name} Accel X\"")
            parts.append(f"    accel_y:")
            parts.append(f"      name: \"{s_name} Accel Y\"")
            parts.append(f"    accel_z:")
            parts.append(f"      name: \"{s_name} Accel Z\"")
            parts.append(f"    gyro_x:")
            parts.append(f"      name: \"{s_name} Gyro X\"")
            parts.append(f"    gyro_y:")
            parts.append(f"      name: \"{s_name} Gyro Y\"")
            parts.append(f"    gyro_z:")
            parts.append(f"      name: \"{s_name} Gyro Z\"")

    return "\n".join(parts) + "\n"


def _gen_binary_sensor_yaml(configs: list[dict]) -> str:
    if not configs:
        return ""
    parts = ["# Binary Sensors", "binary_sensor:"]
    for cfg in configs:
        b_type = cfg["type"]
        b_name = cfg.get("name", "Sensor")
        b_pin = cfg.get("pin", "")
        if b_type == "gpio":
            parts.append(f"  - platform: gpio")
            parts.append(f"    pin: GPIO{b_pin}")
            parts.append(f"    name: \"{b_name}\"")
            if cfg.get("device_class"):
                parts.append(f"    device_class: {cfg['device_class']}")
        elif b_type == "status":
            parts.append(f"  - platform: status")
            parts.append(f"    name: \"{b_name}\"")
    return "\n".join(parts) + "\n"


def _gen_switch_yaml(configs: list[dict]) -> str:
    if not configs:
        return ""
    parts = ["# Switches", "switch:"]
    for cfg in configs:
        s_type = cfg["type"]
        s_name = cfg.get("name", "Switch")
        s_pin = cfg.get("pin", "")
        s_restore = cfg.get("restore_mode", "RESTORE_DEFAULT_OFF")
        if s_type == "gpio" or s_type == "relay":
            parts.append(f"  - platform: gpio")
            parts.append(f"    name: \"{s_name}\"")
            parts.append(f"    pin: GPIO{s_pin}")
            parts.append(f"    restore_mode: {s_restore}")
            if s_type == "relay":
                parts.append(f"    id: relay_{cfg.get('id', '1')}")
        elif s_type == "output":
            parts.append(f"  - platform: output")
            parts.append(f"    name: \"{s_name}\"")
            parts.append(f"    output_id: {cfg.get('output_id', 'output_1')}")
            parts.append(f"    restore_mode: {s_restore}")
    return "\n".join(parts) + "\n"


def _gen_light_yaml(configs: list[dict]) -> str:
    if not configs:
        return ""
    parts = ["# Lights"]
    # Outputs block (for lights that need PWM outputs)
    outputs = []
    for cfg in configs:
        l_type = cfg["type"]
        l_name = cfg.get("name", "Light")
        l_pin = cfg.get("pin", "")
        l_id = cfg.get("id", "1")

        if l_type == "binary":
            outputs.append(f"  - platform: gpio")
            outputs.append(f"    pin: GPIO{l_pin}")
            outputs.append(f"    id: light_output_{l_id}")
            parts.append(f"light:")
            parts.append(f"  - platform: binary")
            parts.append(f"    name: \"{l_name}\"")
            parts.append(f"    output: light_output_{l_id}")

        elif l_type == "monochromatic":
            outputs.append(f"  - platform: ledc")
            outputs.append(f"    pin: GPIO{l_pin}")
            outputs.append(f"    id: light_output_{l_id}")
            outputs.append(f"    frequency: 1000 Hz")
            parts.append(f"light:")
            parts.append(f"  - platform: monochromatic")
            parts.append(f"    name: \"{l_name}\"")
            parts.append(f"    output: light_output_{l_id}")

        elif l_type == "rgb":
            pins = cfg.get("pins", {}).get("rgb", [l_pin, "", ""])
            outputs.append(f"  - platform: ledc")
            outputs.append(f"    pin: GPIO{pins[0]}")
            outputs.append(f"    id: light_output_{l_id}_r")
            outputs.append(f"    frequency: 1000 Hz")
            outputs.append(f"  - platform: ledc")
            outputs.append(f"    pin: GPIO{pins[1]}")
            outputs.append(f"    id: light_output_{l_id}_g")
            outputs.append(f"    frequency: 1000 Hz")
            outputs.append(f"  - platform: ledc")
            outputs.append(f"    pin: GPIO{pins[2]}")
            outputs.append(f"    id: light_output_{l_id}_b")
            outputs.append(f"    frequency: 1000 Hz")
            parts.append(f"light:")
            parts.append(f"  - platform: rgb")
            parts.append(f"    name: \"{l_name}\"")
            parts.append(f"    red: light_output_{l_id}_r")
            parts.append(f"    green: light_output_{l_id}_g")
            parts.append(f"    blue: light_output_{l_id}_b")

        elif l_type == "rgbw":
            pins = cfg.get("pins", {}).get("rgbw", [l_pin, "", "", ""])
            for i, color in enumerate(["r", "g", "b", "w"]):
                outputs.append(f"  - platform: ledc")
                outputs.append(f"    pin: GPIO{pins[i]}")
                outputs.append(f"    id: light_output_{l_id}_{color}")
                outputs.append(f"    frequency: 1000 Hz")
            parts.append(f"light:")
            parts.append(f"  - platform: rgbw")
            parts.append(f"    name: \"{l_name}\"")
            parts.append(f"    red: light_output_{l_id}_r")
            parts.append(f"    green: light_output_{l_id}_g")
            parts.append(f"    blue: light_output_{l_id}_b")
            parts.append(f"    white: light_output_{l_id}_w")

        elif l_type == "neopixel":
            parts.append(f"light:")
            parts.append(f"  - platform: neopixelbus")
            parts.append(f"    name: \"{l_name}\"")
            parts.append(f"    type: GRB")
            parts.append(f"    variant: WS2812")
            parts.append(f"    pin: GPIO{l_pin}")
            parts.append(f"    num_leds: {cfg.get('num_leds', 30)}")
            parts.append(f"    method: esp32_rmt")

    result = ""
    if outputs:
        result = "# Outputs (PWM/LEDC)\noutput:\n" + "\n".join(outputs) + "\n\n"
    if len(parts) > 1:
        result += "\n".join(parts) + "\n"
    return result


def _gen_i2c_yaml(sensor_configs: list[dict]) -> str:
    """Generate I2C bus config if any sensor needs it."""
    i2c_sensors = {"bmp180", "bme280", "bme680", "sht3xd", "ads1115",
                   "ina219", "ina3221", "apds9960", "tcs34725",
                   "scd4x", "mpu6050"}
    needs_i2c = any(c["type"] in i2c_sensors for c in sensor_configs)
    if needs_i2c:
        return "i2c:\n  sda: GPIO21\n  scl: GPIO22\n  scan: true\n"
    return ""


def _gen_spi_yaml(sensor_configs: list[dict]) -> str:
    spi_sensors = {"max31855", "max6675", "rc522"}
    needs_spi = any(c["type"] in spi_sensors for c in sensor_configs)
    if needs_spi:
        return "spi:\n  clk_pin: GPIO18\n  miso_pin: GPIO19\n  mosi_pin: GPIO23\n"
    return ""


def _gen_uart_yaml(sensor_configs: list[dict]) -> str:
    uart_sensors = {"pmsx003", "mhz19"}
    uart_configs = [c for c in sensor_configs if c["type"] in uart_sensors]
    if not uart_configs:
        return ""
    parts = []
    for cfg in uart_configs:
        s_name = cfg.get("name", "uart")
        parts.append(f"uart:")
        parts.append(f"  id: uart_{s_name.lower().replace(' ', '_')}")
        parts.append(f"  tx_pin: GPIO{cfg.get('tx_pin', '17')}")
        parts.append(f"  rx_pin: GPIO{cfg.get('rx_pin', '16')}")
        parts.append(f"  baud_rate: {cfg.get('baud_rate', 9600)}")
    return "\n".join(parts) + "\n"


def generate_yaml(config: dict) -> str:
    """Generate full YAML config from user selections."""
    import secrets
    import string

    name = config.get("name", "my-device")
    friendly_name = config.get("friendly_name", name)
    platform = config.get("platform", "ESP32")
    board = config.get("board", "nodemcu-32s")
    wifi_ssid = config.get("wifi_ssid", "")
    wifi_password = config.get("wifi_password", "")

    letters = string.ascii_letters + string.digits
    fallback_name = f"{friendly_name} Fallback Hotspot"
    if len(fallback_name) > 32:
        fallback_name = friendly_name
    fallback_psk = "".join(secrets.choice(letters) for _ in range(12))

    api_key = config.get("api_key", base64.b64encode(secrets.token_bytes(32)).decode())
    ota_password = config.get("ota_password", secrets.token_hex(16))

    platform_section = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["ESP32"]).format(board=board)

    sensors = config.get("sensors", [])
    binary_sensors = config.get("binary_sensors", [])
    switches = config.get("switches", [])
    lights = config.get("lights", [])

    sensor_block = _gen_sensor_yaml(sensors)
    binary_sensor_block = _gen_binary_sensor_yaml(binary_sensors)
    switch_block = _gen_switch_yaml(switches)
    light_block = _gen_light_yaml(lights)
    output_block = ""
    # light_block may have already generated output block

    # Bus configs
    i2c_block = _gen_i2c_yaml(sensors)
    spi_block = _gen_spi_yaml(sensors)
    uart_block = _gen_uart_yaml(sensors)

    substitutions = config.get("substitutions", "")
    if substitutions:
        substitutions = f"substitutions:\n  {substitutions}"

    # Combine all
    parts = [
        f"esphome:\n  name: {name}\n  friendly_name: {friendly_name}\n",
        platform_section,
        "\n# Enable logging\nlogger:\n",
        f"\n# Enable Home Assistant API\napi:\n  encryption:\n    key: \"{api_key}\"\n",
        f"\nota:\n  - platform: esphome\n    password: \"{ota_password}\"\n",
    ]

    # WiFi section
    if wifi_ssid:
        parts.append(f"\nwifi:\n  ssid: \"{wifi_ssid}\"\n  password: \"{wifi_password}\"\n")
        parts.append(f"\n  # Enable fallback hotspot\n  ap:\n    ssid: \"{fallback_name}\"\n    password: \"{fallback_psk}\"\n\ncaptive_portal:\n")
    else:
        parts.append(f"\n# wifi:\n#   ssid: \"MySSID\"\n#   password: \"mypassword\"\n")

    if substitutions:
        parts.append(f"\n{substitutions}\n")

    # Bus configs
    if i2c_block:
        parts.append(f"\n{i2c_block}")
    if spi_block:
        parts.append(f"\n{spi_block}")
    if uart_block:
        parts.append(f"\n{uart_block}")

    if sensor_block:
        parts.append(f"\n{sensor_block}")
    if binary_sensor_block:
        parts.append(f"\n{binary_sensor_block}")
    if switch_block:
        parts.append(f"\n{switch_block}")
    if light_block:
        # Extract output part from light_block if it exists
        if "output:" in light_block:
            idx = light_block.index("output:")
            output_block = light_block[idx:]
            light_block = light_block[:idx]
            # Remove "Lights" header if output was extracted
        parts.append(f"\n{light_block}")
    if output_block:
        parts.append(f"\n{output_block}")

    return "".join(parts)


class CodeGeneratorHandler(tornado.web.RequestHandler):
    """Handler for the code generator page."""

    def get(self) -> None:
        """Serve the custom index.html page."""
        self.set_header("Content-Type", "text/html; charset=utf-8")
        # Look for index.html in multiple locations
        import os
        for path in [
            "/data/index.html",
            "/config/index.html",
            "/esphome/index.html",
            "/usr/local/lib/python3.12/site-packages/esphome_dashboard/index.html",
        ]:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    self.write(f.read())
                return
        self.write("<h1>index.html not found</h1>")

    def post(self) -> None:
        """Generate YAML from JSON config."""
        try:
            config = json.loads(self.request.body.decode())
        except json.JSONDecodeError:
            self.set_status(400)
            self.write(json.dumps({"error": "Invalid JSON"}))
            return

        try:
            yaml_output = generate_yaml(config)
            self.set_header("Content-Type", "text/yaml")
            self.set_header(
                "Content-Disposition",
                f'attachment; filename="{config.get("name", "device")}.yaml"',
            )
            self.write(yaml_output)
        except Exception as e:
            _LOGGER.exception("Failed to generate YAML")
            self.set_status(500)
            self.write(json.dumps({"error": str(e)}))
