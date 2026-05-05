# Sidewalk Smart Home Node — nRF54L15 DK × AWS IoT Core

**EN.601.616.01.SP26 · Embedded Systems & Wireless Internet of Things · Johns Hopkins University**  
*Ryan Binder · Ethan Brown · Marwan Aldahmani · Instructor: Dr. Renjie Zhao*

---

## Introduction - What we built

Most smart home sensors require dedicated gateways, proprietary hubs, or always-on Wi-Fi to reach the cloud. We eliminated all of that. By porting Amazon Sidewalk's Bluetooth LE stack to the newest Nordic Semiconductor SoC — the nRF54L15 — we turned an ordinary Amazon Echo into a zero-cost Sidewalk gateway and connected a fully bidirectional smart room node to AWS IoT Core with no additional infrastructure.

The device reads real temperature and humidity from a BME280 sensor every 30 seconds, streams the data to AWS over Sidewalk BLE, stores every reading in DynamoDB, and triggers SNS email alerts on motion or temperature threshold breaches. Critically, the cloud can also *talk back*: a single AWS CLI command or a click in the live web dashboard toggles an LED or relay on the DK within 5–10 seconds — end-to-end, through Amazon's network.

The result is a working prototype of a battery-friendly, infrastructure-free smart home sensor node that demonstrates the full IoT stack: embedded Zephyr RTOS firmware, Amazon Sidewalk BLE, AWS Lambda, DynamoDB, API Gateway, and a live S3-hosted dashboard — all integrated and running.

---

## Live dashboard

![Sidewalk Smart Home Dashboard — live temperature and humidity charts with downlink LED controls](docs/figures/dashboard.png)

*The S3-hosted dashboard shows live temperature (21.42 °C) and humidity (44.34 %) readings from the nRF54L15 DK, with one-click downlink controls to toggle the onboard LED/relay. Auto-refreshes every 30 seconds. Charts display the last 50 uplinks.*

---

> **See it live** — press Button 3 on the DK, watch the MQTT test client update in AWS IoT Core, and see the new data point appear on the dashboard within one refresh cycle.

---


