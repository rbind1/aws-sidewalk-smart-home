# Sidewalk Smart Home Node — Comprehensive Project Guide

**Course:** EN.601.616.01.SP26 · Embedded Systems & Wireless Internet of Things  
**Institution:** Johns Hopkins University  
**Instructor:** Dr. Renjie Zhao  
**Team:** Ryan Binder · Ethan Brown · Marwan Aldahmani  

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Hardware Details](#2-hardware-details)
3. [Software Environment](#3-software-environment)
4. [Reproducibility Guide](#4-reproducibility-guide)
5. [Testing and Measurement](#5-testing-and-measurement)
6. [Troubleshooting](#6-troubleshooting)
7. [Offline Mode](#7-offline-mode)
8. [Security Keys and Tokens](#8-security-keys-and-tokens)

---

## 1. Introduction

### 1.1 Problem Statement

Mainstream smart home sensors face a fundamental connectivity dilemma: Wi-Fi sensors drain batteries quickly and require routers in every corner of the home; proprietary protocols like Zigbee and Z-Wave need dedicated hubs; cellular modules add cost and SIM management overhead. None of these options are truly infrastructure-free.

Amazon Sidewalk is a shared, low-bandwidth wireless network that repurposes a small slice of internet bandwidth from existing Amazon Echo and Ring devices to provide free, low-power connectivity for IoT end devices. It operates in two modes — Bluetooth LE for indoor range and 900 MHz sub-GHz for long range — and is available across millions of US homes at no cost to the device manufacturer.

This project demonstrates how to connect the **Nordic Semiconductor nRF54L15 DK** to **AWS IoT Core** via Amazon Sidewalk BLE, and build a complete bidirectional smart home sensor node on top of that connectivity.

### 1.2 Target Application

A battery-powered smart room node placed on a nightstand, shelf, or windowsill that:

- Reads temperature and humidity every 30 seconds using a Bosch BME280 sensor
- Detects motion events via button press (or a PIR sensor if wired)
- Transmits sensor readings to AWS over Sidewalk BLE through a nearby Echo speaker
- Receives downlink commands from AWS to toggle an LED or relay (simulating a smart plug)
- Alerts the homeowner via SNS email when motion is detected or temperature exceeds a threshold
- Displays live data on a web dashboard accessible from any browser

### 1.3 High-Level Architecture

```
┌─────────────────────────┐
│     nRF54L15 DK         │
│  BME280 sensor (I2C)    │
│  Zephyr RTOS firmware   │
│  Sidewalk BLE stack     │
└────────────┬────────────┘
             │ BLE (Sidewalk protocol, encrypted)
             ▼
┌─────────────────────────┐
│  Amazon Echo (3rd gen+) │
│  Sidewalk BLE gateway   │
└────────────┬────────────┘
             │ HTTPS to AWS
             ▼
┌────────────────────────────────────────────────────────┐
│                  AWS Cloud (us-east-1)                 │
│                                                        │
│  IoT Wireless → MQTT topic → IoT Rule                  │
│                                   │                    │
│                              Lambda (decoder)          │
│                                   │                    │
│                              DynamoDB ← Lambda (API)   │
│                                            │           │
│                              API Gateway → S3 Dashboard│
│                                                        │
│  Downlink: AWS CLI → IoT Wireless → Echo → DK LED      │
└────────────────────────────────────────────────────────┘
```

### 1.4 Key Features and Performance Summary

| Feature / Metric | Value |
|-----------------|-------|
| Wireless protocol | Amazon Sidewalk BLE (link type 1) |
| Uplink latency (DK → MQTT broker) | ~3–5 seconds |
| Downlink latency (AWS CLI → LED toggle) | ~5–10 seconds |
| Indoor BLE range to Echo gateway | ~10–30 m (through walls) |
| Sensor: temperature accuracy | ±1.0 °C (BME280) |
| Sensor: humidity accuracy | ±3 % RH (BME280) |
| Uplink interval (nominal) | 30 seconds |
| Uplink interval (motion active) | 5 seconds |
| Payload size | 6 bytes binary |
| Cloud infrastructure cost | < $0.05 / day (dev workload) |
| Sidewalk availability | US only |
| Gateway requirement | Echo 4th gen+ or Ring Bridge PRO |

---

## 2. Hardware Details

### 2.1 Primary Board — Nordic Semiconductor nRF54L15 DK

Attributes:
Radio: Bluetooth LE 5.4, Bluetooth Mesh, 802.15.4 (Zigbee/Thread)
Interface: USB-C (power, UART, J-Link OB)
Onboard LEDs: 4 × RGB-capable GPIO LEDs (LED0–LED3)
Onboard buttons: 4 × tactile push buttons (SW0–SW3)
GPIO headers: P0, P1, P2 connectors
I2C peripheral used: TWIM21 on P1.11 (SCL) and P1.12 (SDA) 
Operating voltage: Configurable 1.8 V or 3.3 V via nPM PMIC 
Product page: https://www.nordicsemi.com/Products/Development-hardware/nRF54L15-DK 

> **Important:** The DK ships with VDD configured to 1.8 V by default. Before connecting any external sensor, set VDD to 3.3 V using nRF Connect for Desktop → Board Configurator. See [Section 4.1](#41-hardware-assembly).

### 2.2 Additional Peripherals

Components:
- Environmental sensor: Bosch BME280 (Adafruit breakout #2652), https://www.adafruit.com/product/2652 
- Sidewalk gateway: Amazon Echo (3rd generation) 
- USB-C cable 
- Jumper wires 
- BME280 breakout to DK P1 header 

### 2.3 Hardware Modifications

No board rework, custom PCBs, or enclosures are required. The project uses:

- The nRF54L15 DK in its stock form with no soldering
- The BME280 Adafruit breakout board which includes onboard 3.3 V regulation and I2C pull-up resistors — no external passive components needed
- Standard jumper wires between the breakout and the DK P1 header

**Wiring diagram (BME280 to nRF54L15 DK P1 header):**

```
BME280 breakout     nRF54L15 DK P1 header
───────────────     ──────────────────────
VIN / VCC    ──────  3.3 V  (P1 VDD)
GND          ──────  GND    (P1 GND)
SCL / SCK    ──────  P1.11  (TWIM21 SCL)
SDA          ──────  P1.12  (TWIM21 SDA)
CSB          ──────  3.3 V  (forces I2C mode, not SPI)
SDO / ADDR   ──────  GND    (I2C address 0x76)
                or   3.3 V  (I2C address 0x77)
```

> Match the SDO wiring to `BME280_I2C_ADDR` in `src/app_config.h` and the DTS node `bme280@76` or `bme280@77` in the board overlay. Both must agree.

**Live dashboard screenshot:**

![Sidewalk Smart Home Dashboard](docs/figures/dashboard.png)

*The dashboard shows live temperature (21.42 °C) and humidity (44.34 %) readings from the nRF54L15 DK, with downlink LED/relay controls and an activity log. Charts auto-refresh every 30 seconds from DynamoDB via API Gateway.*

### 2.4 Power Subsystem

The nRF54L15 DK is powered via USB-C for development and demonstration. Battery operation is not implemented in the current prototype but is the natural next step.

BLE connected idle  ~1–2 mA 
Deep sleep (System Off)  ~2 µA 
BME280 measurement active  ~0.7 mA (adds ~35 ms per 30 s cycle)
Average over 30 s uplink cycle ~0.3–0.5 mA estimated 


### 2.5 RF Specifications

- Protocol: Amazon Sidewalk over Bluetooth LE 
- BLE version: Bluetooth 5.4 (nRF54L15 native radio)
- Frequency band: 2.4 GHz
- Maximum TX power: +3 dBm (nRF54L15 BLE) 
- Antenna: PCB trace antenna (onboard, no external antenna needed) 
- Expected indoor range: 10–30 m line-of-sight to Echo gateway 
- Sidewalk encryption: AES-128-GCM (handled by Sidewalk stack) 
- Authentication: ECDH key exchange using MFG-provisioned credentials 
- Compliance notes: Sidewalk BLE uses standard BLE PHY — the nRF54L15 DK is FCC certified (IC: 2AKBP-NRF54L15DK) 


---

## 3. Software Environment

### 3.1 Firmware

#### IDE and Toolchain

- nRF Connect for Desktop: Latest stable (≥ 5.0) 
- Toolchain Manager:  Bundled with nRF Connect for Desktop 
- nRF Connect SDK: v2.6.x or later 
- Amazon Sidewalk Add-on 
- Zephyr RTOS 
- West (build tool) |
- nRF Command Line Tools

**Critical:** All `west build` commands must be run from the terminal opened inside Toolchain Manager, not from a system Command Prompt or PowerShell. The Toolchain Manager terminal pre-configures PATH, Python venv, and Zephyr environment variables.

#### SDK and RTOS

- **nRF Connect SDK** — a Zephyr-based SDK for Nordic SoCs. Includes drivers, BLE stack, sensor subsystem, GPIO, I2C, and the Partition Manager.
- **Zephyr RTOS** — real-time OS providing the scheduler, work queues, timers, and device driver model used by the application.
- **Amazon Sidewalk Add-on** — adds the Sidewalk PAL (Platform Abstraction Layer), Sidewalk API (`sid_api.h`), and the `sid_end_device` sample template.
### Development Machine

- **OS:** Windows
- **Shell:** PowerShell
- **Workspace:** `C:\ncs\sidewalk-addon`
- **Sample source:** `C:\ncs\sidewalk-addon\sidewalk\samples\sid_end_device`
- **Build directory:** `C:\ncs\sidewalk-addon\sidewalk\samples\sid_end_device\build`

### Firmware Stack

- nRF Connect SDK Sidewalk add-on workspace
- Zephyr RTOS
- Nordic nRF54L15 DK board target
- Amazon Sidewalk sample: `sid_end_device`

Working board target:

```powershell
nrf54l15dk/nrf54l15/cpuapp/ns
```

### AWS Components

- **AWS Region:** `us-east-1`
- **AWS IoT Wireless Device Type:** Sidewalk
- **Wireless device name:** `SidewalkDevice1`
- **Wireless device ID:** `49ead42e-0b05-4612-8a28-9e171a64067a`
- **Destination:** `SidewalkDestination`
- **Uplink topic:** `sidewalk/uplink`
- **IoT Rule:** `SidewalkUplinkRule`
- **Lambda:** `SidewalkUplinkDecoder`
- **CloudWatch Log Group:** `/aws/lambda/SidewalkUplinkDecoder`
- **Optional storage:** DynamoDB table configured by `TABLE_NAME`
- **Optional alerting:** SNS topic configured by `ALERT_TOPIC_ARN`

Do not commit AWS credentials, manufacturing blobs, private keys, access keys, or certificates.

## Repository Structure

Recommended final repository layout:

```text
.
├── firmware/
│   └── sid_end_device/
│       ├── src/
│       │   └── hello/
│       │       └── app.c
│       ├── boards/
│       │   └── nrf54l15dk_nrf54l15_cpuapp_ns.overlay
│       └── prj.conf
├── cloud/
│   └── lambda/
│       └── index.py
├── docs/
│   └── figures/
│       └── system_architecture.png
├── scripts/
│   └── decode_payload.ps1
├── README.md
├── intro.md
└── LICENSE
```

## Firmware Configuration

### `prj.conf`

Enable I2C, Zephyr sensor support, and the BME280 driver:

```conf
CONFIG_I2C=y
CONFIG_SENSOR=y
CONFIG_BME280=y
CONFIG_CBPRINTF_FP_SUPPORT=y
```

### Board Overlay

For SDA on `P1.12`, SCL on `P1.11`, and BME280 address `0x76`, add the BME280 to the nRF54L15 DK overlay:

```dts
&pinctrl {
    i2c21_default: i2c21_default {
        group1 {
            psels = <NRF_PSEL(TWIM_SDA, 1, 12)>,
                    <NRF_PSEL(TWIM_SCL, 1, 11)>;
            bias-pull-up;
        };
    };

    i2c21_sleep: i2c21_sleep {
        group1 {
            psels = <NRF_PSEL(TWIM_SDA, 1, 12)>,
                    <NRF_PSEL(TWIM_SCL, 1, 11)>;
            low-power-enable;
        };
    };
};

&i2c21 {
    compatible = "nordic,nrf-twim";
    status = "okay";
    pinctrl-0 = <&i2c21_default>;
    pinctrl-1 = <&i2c21_sleep>;
    pinctrl-names = "default", "sleep";
    clock-frequency = <I2C_BITRATE_STANDARD>;

    bme280: bme280@76 {
        compatible = "bosch,bme280";
        reg = <0x76>;
    };
};
```

## Firmware Behavior

The modified Sidewalk sample replaces the default `"hello"` button uplink with a BME280 JSON payload. On `DK_BTN1` short press, the firmware:

1. Checks that the BME280 device is ready.
2. Fetches a sample from the sensor.
3. Retries once after 100 ms if the driver returns `-EAGAIN`.
4. Reads temperature, pressure, and humidity channels.
5. Formats the values into JSON.
6. Sends the JSON payload through Sidewalk.

Successful payload example:

```json
{"sensor":"bme280","temp_c":23.400000,"pressure_kpa":99.873703,"humidity_pct":39.384765}
```

Sensor error payload example:

```json
{"sensor":"bme280","status":"error","err":-11}
```

## Payload Encoding

AWS IoT Wireless exposes the Sidewalk device payload in the event field:

```json
"PayloadData": "..."
```

In this project, the payload is encoded as:

```text
JSON string → hex string → base64 PayloadData
```

So decoding requires:

```text
PayloadData
→ base64 decode
→ hex decode
→ JSON parse
```

PowerShell decode example:

```powershell
$payload = "PASTE_PAYLOADDATA_HERE"

$hex = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String($payload)
)

$jsonBytes = for ($i = 0; $i -lt $hex.Length; $i += 2) {
    [Convert]::ToByte($hex.Substring($i, 2), 16)
}

[System.Text.Encoding]::UTF8.GetString($jsonBytes)
```

Expected output:

```json
{"sensor":"bme280","temp_c":23.400000,"pressure_kpa":99.873703,"humidity_pct":39.384765}
```

## Build and Flash

From the Sidewalk sample directory:

```powershell
cd C:\ncs\sidewalk-addon\sidewalk\samples\sid_end_device
```

Build:

```powershell
west build -b nrf54l15dk/nrf54l15/cpuapp/ns -p always .
```

Flash:

```powershell
west flash
```

Do not erase the board unless you intentionally want to redo provisioning. The device must retain its Sidewalk manufacturing/provisioning data.

## Running the Demo

### 1. Prepare the Echo Dot

Confirm the Echo Dot is:

- Powered on
- Connected to the internet
- Registered in the Alexa app
- Has Amazon Sidewalk enabled
- Physically near the nRF54L15 DK

The laptop does **not** need to be on the same Wi-Fi as the Echo Dot. The laptop only needs internet access to view AWS.

### 2. Open Serial Logs

Open a serial terminal for the nRF54L15 DK.

Expected startup logs include:

```text
Successfully parsed mfg data
registered = true
Time Sync Success
Status changed: ready
Link mode on BLE = {Cloud: True, Mobile: False}
```

Expected sensor startup log:

```text
Checking BME280 sensor
BME280 startup payload: {"sensor":"bme280",...}
```

### 3. Press Button 1

Press `DK_BTN1`.

Expected firmware logs:

```text
button pressed 1 short
BME280 temp: 23.400000 C
BME280 pressure: 99.873703 kPa
BME280 humidity: 39.384765 %
Send BME280 sensor message: {"sensor":"bme280","temp_c":23.400000,"pressure_kpa":99.873703,"humidity_pct":39.384765}
Message send success
```

### 4. Verify in AWS MQTT Test Client

In AWS IoT Core:

```text
MQTT test client → Subscribe to topic
```

Subscribe to:

```text
sidewalk/uplink
```

Press `DK_BTN1` again.

You should receive a message containing:

```json
"PayloadData": "..."
```

### 5. Verify in CloudWatch Logs

Open:

```text
CloudWatch → Log groups → /aws/lambda/SidewalkUplinkDecoder
```

Expected successful Lambda logs:

```text
Decoded JSON: {"sensor": "bme280", "temp_c": 23.24, "pressure_kpa": 99.888542, "humidity_pct": 40.701171}
Decoded: device=... sensor=bme280 temp=23.24C pressure=99.89kPa humidity=40.70% sidewalk_seq=...
DynamoDB item written
No SNS alert: 23.24C <= 30.00C threshold
```

Expected clean handling of intermittent sensor errors:

```text
Decoded JSON: {"sensor": "bme280", "status": "error", "err": -11}
BME280 read failed: device=... sensor=bme280 err=-11 sidewalk_seq=...
DynamoDB error item written
```

## AWS CLI Checks

List registered Sidewalk devices:

```powershell
aws iotwireless list-wireless-devices --wireless-device-type Sidewalk --region us-east-1
```

Important fields:

```json
{
  "Name": "SidewalkDevice1",
  "DestinationName": "SidewalkDestination",
  "LastUplinkReceivedAt": "...",
  "Sidewalk": {
    "Status": "REGISTERED"
  }
}
```

This confirms that AWS recognizes the device, that it is registered, and that AWS IoT Wireless recently received an uplink.

## Lambda Decoder

The Lambda function `SidewalkUplinkDecoder` decodes the current BME280 payload format, writes successful readings to DynamoDB, logs error payloads cleanly, and optionally publishes an SNS alert when temperature exceeds the configured threshold.

Required environment variables:

| Variable | Purpose |
|---|---|
| `TABLE_NAME` | DynamoDB table for readings |
| `ALERT_TOPIC_ARN` | SNS topic ARN for high-temperature alerts |
| `TEMP_THRESHOLD` | Temperature threshold in Celsius, default `30` |

The Lambda expects:

```text
PayloadData → base64 decode → hex decode → JSON parse
```

## Troubleshooting

### MQTT receives messages, but CloudWatch does not update

Check that `SidewalkUplinkRule` listens to the same topic as the Sidewalk destination:

```sql
SELECT *, timestamp() AS received_at FROM 'sidewalk/uplink'
```

If the rule listens to another topic, such as `sidewalk/home/sensor`, MQTT may receive messages on `sidewalk/uplink`, but the rule/Lambda path will not run.

### BME280 device is not ready

Possible causes:

- SDA/SCL pins do not match the overlay
- SDA/SCL are swapped
- Wrong I2C address: `0x76` vs `0x77`
- CSB is not tied high
- Sensor is not powered correctly
- Breakout board requires a higher VIN than VDDIO

### PayloadData looks unreadable

That is expected. AWS shows the Sidewalk payload in encoded form. Decode it using the PowerShell snippet above or let the Lambda decoder parse it.

### Lambda reports impossible values

This means the Lambda is probably still using the old 6-byte binary decoder. The new BME280 firmware sends JSON encoded as hex/base64, so the Lambda must use the JSON decoder.

### Intermittent `err=-11`

`err=-11` is likely `-EAGAIN`, meaning the BME280 sample was not ready. The firmware retries once after 100 ms. If it still fails, the device sends a clean error payload.

### BLE disconnect messages

Logs like this can be normal:

```text
BT Disconnected Reason: 0x16 = LOCALHOST_TERM_CONN
Status changed: not ready
```

Sidewalk may disconnect and reconnect as needed. The important confirmation is:

```text
Message send success
```

## 4. Reproducibility Guide

### 4.1 Hardware Assembly

**Step 1 — Set DK voltage to 3.3 V (do this before connecting any wires)**

1. Connect the nRF54L15 DK to your PC via USB-C.
2. Open nRF Connect for Desktop → Board Configurator.
3. Select your DK from the device list.
4. Set VDD (nPM VOUT1) to **3.3 V**.
5. Click **Write config**.
6. Disconnect and reconnect USB.

Failure to do this step causes the BME280 I2C lines to sit at 1.8 V, preventing the sensor from responding.

**Step 2 — Wire the BME280 breakout to the DK P1 header**

```
BME280 (Adafruit #2652)    nRF54L15 DK P1
───────────────────────    ──────────────
VIN                   ───  3.3 V (P1 VDD)
GND                   ───  GND   (P1 GND)
SCK / SCL             ───  P1.11 (TWIM21 SCL)
SDA                   ───  P1.12 (TWIM21 SDA)
CSB                   ───  3.3 V (forces I2C, not SPI)
SDO                   ───  GND   → address 0x76
                      or   3.3 V → address 0x77
```

Note the SDO wiring and update `BME280_I2C_ADDR` in `src/app_config.h` and `bme280@XX` in the board overlay to match.

**Step 3 — Verify Echo device**

1. Open the Amazon Alexa app.
2. Navigate to More → Settings → Account Settings → Amazon Sidewalk.
3. Confirm Sidewalk is **enabled**.
4. Confirm Echo model is **4th generation (2020) or later**.
5. Confirm all hardware is **physically in the United States**.

### 4.2 Environment Setup

**Firmware toolchain:**

```bash
# 1. Download and install nRF Connect for Desktop
#    https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-Desktop

# 2. Inside nRF Connect for Desktop:
#    Open Toolchain Manager → Install nRF Connect SDK v2.6.x or later

# 3. Install the Amazon Sidewalk Add-on:
#    nRF Connect for Desktop → Add-ons → Amazon Sidewalk → Install

# 4. Download and install nRF Command Line Tools (provides nrfjprog):
#    https://www.nordicsemi.com/Products/Development-tools/nRF-Command-Line-Tools

# 5. Verify nrfjprog is accessible (from any terminal):
nrfjprog --version
```

**AWS toolchain:**

```bash
# Install AWS CLI v2:
# https://aws.amazon.com/cli/

# Configure with us-east-1 (MANDATORY):
aws configure
# Region: us-east-1
# Output: json

# Install Python dependencies:
pip install boto3
pip install "botocore[crt]"

# Clone provisioning tool:
git clone https://github.com/aws-samples/aws-iot-core-for-amazon-sidewalk-sample-app
cd aws-iot-core-for-amazon-sidewalk-sample-app
pip install -r requirements.txt
```

### 4.3 Build Instructions

**Firmware:**

All commands must be run from the **Toolchain Manager terminal** (opened from inside nRF Connect for Desktop — not a system terminal).

```bash
# Navigate to the firmware application directory
cd path/to/sidewalk_smart_home

# Build for nRF54L15 DK
west build -b nrf54l15dk/nrf54l15/cpuapp

# Output: build/merged.hex
```

If the board target `nrf54l15dk/nrf54l15/cpuapp` is not found, the Sidewalk add-on may not yet include the nRF54L15. Post on devzone.nordicsemi.com with your SDK and add-on versions and ask for the correct board target string.

**AWS backend:**

```bash
# Validate the CloudFormation template (from the sidewalk-aws directory):
aws cloudformation validate-template \
    --template-body file://cloudformation/sidewalk-stack.yaml \
    --region us-east-1
```

### 4.4 Flashing and Provisioning

**CRITICAL ORDER: MFG credentials must be flashed before the application. Never reverse this.**

**Step 1 — Generate device credentials (run once per DK):**

```bash
cd aws-iot-core-for-amazon-sidewalk-sample-app

python EdgeDeviceProvisioning/provision_sidewalk_end_device.py \
    --hardware_platform NORDIC \
    --interactive
```

Outputs (inside `EdgeDeviceProvisioning/DeviceProfile_<id>/WirelessDevice_<id>/`):
- `Nordic_MFG.hex` — flash to DK in Step 2
- `WirelessDevice.json` — contains `"Id"` field (your WirelessDeviceId) — **keep this file**

**Step 2 — Flash MFG credentials:**

```bash
# Windows:
scripts\flash_mfg.bat "path\to\Nordic_MFG.hex"

# Or manually (from any terminal):
nrfjprog --sectorerase --program "path/to/Nordic_MFG.hex" --reset
```

>  **After this step, NEVER use:** `nrfjprog --recover`, `nrfjprog --chiperase`, or `west flash --recover`. All perform a chip erase that permanently destroys the provisioning credentials. Always use `--sectorerase` for all subsequent flashes.

**Step 3 — Deploy AWS backend:**

```bash
# Create IoT Wireless Destination (must run before CloudFormation):
python scripts/create_destination.py \
    --destination SidewalkSmartHomeDest \
    --topic sidewalk/home/sensor \
    --region us-east-1

# Deploy all AWS resources:
aws cloudformation deploy \
    --region us-east-1 \
    --template-file cloudformation/sidewalk-stack.yaml \
    --stack-name sidewalk-smart-home \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        SidewalkDestinationName=SidewalkSmartHomeDest \
        AlertEmail=your@email.com \
        TemperatureAlertThresholdC=30 \
        MqttUplinkTopic=sidewalk/home/sensor

# Confirm SNS email subscription (check inbox for AWS notification email and click link)
```

**Step 4 — Flash application firmware:**

```bash
# Windows (from any terminal — NOT the Toolchain Manager terminal):
nrfjprog --sectorerase --program build\merged.hex --reset

# Or using the build script (from Toolchain Manager terminal):
scripts\build_and_flash.bat flash
```

**Step 5 — Upload dashboard:**

```bash
# Get API endpoint from stack outputs:
aws cloudformation describe-stacks \
    --stack-name sidewalk-smart-home \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text

# Inject API URL and upload to S3 (replace YOUR_API_URL):
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
sed "s|__API_ENDPOINT__|YOUR_API_URL|g" dashboard/index.html > /tmp/dash.html
aws s3 cp /tmp/dash.html s3://sidewalk-dashboard-${ACCOUNT}/index.html \
    --content-type text/html --region us-east-1
```

### 4.5 Running the Demo

**Expected startup sequence:**

1. Power on the DK via USB-C.
2. Open a serial terminal at **115200 baud** on the DK's COM port.
3. Observe the startup log:

```
=== Sidewalk Smart Home Node starting ===
Board: nRF54L15 DK
Uplink interval: 30 seconds
LEDs initialised (4 total)
BME280 initialised successfully at I2C addr 0x77
Sidewalk started — waiting for registration...
```

4. LED 1 (blue) blinks fast during Sidewalk registration (~1–3 minutes).
5. LED 1 goes **solid** when the device is registered and connected.
6. Serial log confirms:
```
Sidewalk status: state=1
Sidewalk CONNECTED and READY
```

**Button reference:**

| Button | Short press | Long press (≥ 3 s) |
|--------|------------|-------------------|
| Button 1 | Toggle Sidewalk connection | Factory reset |
| Button 2 | Simulate motion event | Factory reset |
| Button 3 | Force immediate uplink | Factory reset |
| Button 4 | LED demo cycle | Factory reset |

**LED reference:**

| LED | Colour | Meaning |
|-----|--------|---------|
| LED 1 | Blue | Fast blink = registering. Solid = connected. |
| LED 2 | Green | Smart plug relay — ON or OFF. |
| LED 3 | Yellow | Flashes on each successful uplink TX. |
| LED 4 | Red | Error or connection loss. |

**Verify uplink is reaching AWS:**

```bash
# Subscribe to the MQTT topic in AWS Console:
# IoT Core → MQTT test client → Subscribe to: sidewalk/home/sensor

# Then press Button 3 on the DK.
# A JSON message should appear in the test client within ~5 seconds.

# Also check DynamoDB via CLI:
python scripts/test_sidewalk.py --device <WirelessDeviceId> latest
```

**Send a downlink command:**

```bash
# LED ON:
python scripts/test_sidewalk.py --device <WirelessDeviceId> downlink led_on

# LED OFF:
python scripts/test_sidewalk.py --device <WirelessDeviceId> downlink led_off

# Toggle:
python scripts/test_sidewalk.py --device <WirelessDeviceId> downlink led_toggle
```

LED 2 on the DK should respond within 5–10 seconds.

### 4.6 Testing and Measurement

**Simulate uplinks without hardware (for AWS-side testing):**

```bash
python scripts/test_sidewalk.py \
    --device test-device-001 \
    simulate --count 20 --interval 1
```

**Test the uplink decoder Lambda with a known payload:**

The payload `AQ8CAJAB` should decode to temp=27.1 °C, hum=52.2 %, motion=True, seq=1.

```bash
# Invoke Lambda directly:
python invoke_test.py   # see scripts/invoke_test.py

# Verify decoded values:
python scripts/test_sidewalk.py --device test-device-001 latest
# Expected: Temperature: 27.1 °C, Humidity: 52.2 %, Motion: YES, Sequence: 1
```

**Test the full IoT Rule → Lambda chain:**

```bash
aws iot-data publish \
    --topic "sidewalk/home/sensor" \
    --payload "{\"WirelessDeviceId\":\"test-device-001\",\"PayloadData\":\"AQ8CAJAB\",\"WirelessMetadata\":{\"Sidewalk\":{\"Seq\":99}}}" \
    --region us-east-1
```

Then immediately check DynamoDB — timestamp should be within 10 seconds.

**Formal test cases:**

| ID | Test | Pass criteria |
|----|------|---------------|
| TC-01 | Registration | LED 1 solid within 3 min; device shows REGISTERED in AWS Console |
| TC-02 | Periodic uplink | MQTT message arrives every 30 s ± 5 s |
| TC-03 | On-demand uplink | Button 3 triggers uplink within 5 s |
| TC-04 | Payload decode | DynamoDB record shows correct temperature and humidity values |
| TC-05 | Motion flag | Button 2 + Button 3 → next record shows motion=true |
| TC-06 | Downlink LED ON | `led_on` command → LED 2 illuminates within 10 s |
| TC-07 | Downlink LED OFF | `led_off` command → LED 2 extinguishes within 10 s |
| TC-08 | DynamoDB storage | Record contains device_id, timestamp, temperature_c, humidity_pct |
| TC-09 | Dashboard display | Dashboard chart updates within 30 s of new DynamoDB write |
| TC-10 | SNS motion alert | Motion event triggers email within 60 s |

### 4.7 Troubleshooting

| Symptom | Most likely cause | Fix |
|---------|------------------|-----|
| `west build` fails — board not found | Sidewalk add-on does not include nRF54L15 board target | Post on devzone.nordicsemi.com; ask for correct board target for your SDK + add-on version |
| `west` command not found | Wrong terminal | Open terminal from inside Toolchain Manager, not a system terminal |
| `sid_init failed` in serial log | MFG.hex not flashed or erased | Re-run `flash_mfg.bat` with `Nordic_MFG.hex`; then reflash app |
| LED 1 blinks indefinitely (never solid) | Echo not in range, Sidewalk disabled, or not in US | Check Alexa app Sidewalk setting; verify Echo is 4th gen+; confirm US location |
| BME280 not ready in serial log | VDD not set to 3.3 V or wrong I2C address | Run Board Configurator; check SDO pin wiring and address in overlay + app_config.h |
| No MQTT messages in test client | Destination not configured or wrong topic | Verify Destination Expression is exactly `sidewalk/home/sensor`; confirm us-east-1 |
| Lambda decode error in CloudWatch | Byte order mismatch | Firmware must encode big-endian (high byte first); Lambda uses `struct.unpack('>hhBB')` |
| Downlink not received by DK | Device not connected (LED 1 not solid) or wrong device ID | Check LED 1; verify WirelessDeviceId from `WirelessDevice.json` |
| CloudFormation deploy fails | IAM permissions or wrong region | Confirm region is us-east-1; check IAM user has CloudFormation + Lambda + IoT permissions |
| `botocore.exceptions.MissingDependencyException` | Missing CRT dependency | Run: `pip install "botocore[crt]"` |
| SNS subscription shows `PendingConfirmation` | Confirmation email not clicked | Check inbox (and spam) for AWS Notifications email; click the confirmation link |
| Dashboard shows no data | Wrong device ID in dashboard field | Paste WirelessDeviceId exactly from `WirelessDevice.json` including all dashes |
| Downlink Lambda returns 404 | Device ID valid UUID format but not provisioned | Use the real UUID from `WirelessDevice.json`, not a test ID |

**View live Lambda logs:**
```bash
aws logs tail /aws/lambda/SidewalkUplinkDecoder --follow --region us-east-1
aws logs tail /aws/lambda/SidewalkDownlink --follow --region us-east-1
```

### 4.8 Offline Mode

If AWS cloud connectivity is unavailable (no internet, wrong region, or billing issues), the firmware continues to function locally:

- The nRF54L15 DK will attempt Sidewalk registration and retry automatically.
- If the Echo gateway is available but AWS is unreachable, the DK will register locally but uplinks will fail to deliver.
- The serial log will show uplink errors (`sid_put_msg failed`) but the device will not crash.
- LED 4 (red) will illuminate on repeated send failures.

**To run AWS-side validation without a physical DK**, use the simulation script which writes directly to DynamoDB:

```bash
python scripts/test_sidewalk.py \
    --device test-device-001 \
    simulate --count 50 --interval 2
```

This populates the dashboard with realistic data and allows full testing of the Lambda, API Gateway, and dashboard without any hardware.

---

## 5. Testing and Measurement

See [Section 4.6](#46-testing-and-measurement) for the full test case table and CLI commands.

**Measuring uplink latency:** Note the timestamp of a Button 3 press on the serial log, then record the timestamp of the corresponding MQTT message arrival in the IoT Core MQTT test client. Difference = end-to-end uplink latency.

**Measuring downlink latency:** Record the time of the `aws iotwireless send-data-to-wireless-device` call, then watch the serial log for `Downlink received`. Difference = downlink latency.

**Measuring packet delivery ratio:** After a run of N uplinks (use the sequence number counter), query DynamoDB for the device and count unique sequence numbers. PDR = received / sent × 100 %.

---

## 6. Troubleshooting

See the full troubleshooting table in [Section 4.7](#47-troubleshooting).

For issues not covered there, post on the **Nordic DevZone** (devzone.nordicsemi.com) and include:
- nRF Connect SDK version (from Toolchain Manager)
- Sidewalk add-on version
- Full serial log output
- CloudWatch Logs output (from `aws logs tail` command)

---

## 7. Offline Mode

See [Section 4.8](#48-offline-mode).

---

## 8. Security Keys and Tokens


| Credential | Where it lives | How to generate |
|-----------|---------------|----------------|
| AWS Access Key ID | `~/.aws/credentials` | AWS Console → IAM → Users → Security credentials → Create access key |
| AWS Secret Access Key | `~/.aws/credentials` | Generated alongside Access Key ID — copy immediately, not shown again |
| Sidewalk MFG credentials (Nordic_MFG.hex) | Flashed to DK flash partition at `0x160000` | Generated by `provision_sidewalk_end_device.py` — unique per device |
| WirelessDeviceId | `WirelessDevice.json` | Generated by `provision_sidewalk_end_device.py` — UUID format |
| SNS alert email | CloudFormation parameter | Your own email address — confirmed via subscription email |

**Placeholder values used in this repository (replace before use):**

```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
WIRELESS_DEVICE_ID=00000000-0000-0000-0000-000000000000
ALERT_EMAIL=your@email.com
```

**The `Nordic_MFG.hex` file must never be shared or committed.** It contains the ECDH private key and Sidewalk certificate chain for the specific DK it was generated for. Treat it with the same sensitivity as a TLS private key.

---

## References

- Nordic Sidewalk Add-on Documentation: https://docs.nordicsemi.com/bundle/addon-sidewalk-latest
- nRF54L15 DK Product Page: https://www.nordicsemi.com/Products/Development-hardware/nRF54L15-DK
- Nordic GitHub — SDK Sidewalk: https://github.com/nrfconnect/sdk-sidewalk
- AWS Sidewalk Sample App: https://github.com/aws-samples/aws-iot-core-for-amazon-sidewalk-sample-app
- Amazon Sidewalk Developer Docs: https://docs.sidewalk.amazon
- Amazon Sidewalk Coverage Map: https://coverage.sidewalk.amazon 
- AWS IoT Wireless — Sidewalk: https://docs.aws.amazon.com/iot-wireless/latest/developerguide/iot-sidewalk.html
- Nordic DevZone (Sidewalk Q&A): https://devzone.nordicsemi.com 
- UWB Sniffer (reference example): https://github.com/seemoo-lab/uwb-sniffer 

---

