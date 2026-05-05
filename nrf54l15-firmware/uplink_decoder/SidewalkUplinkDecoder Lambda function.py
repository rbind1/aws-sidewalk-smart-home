"""
SidewalkUplinkDecoder — Lambda function
=======================================

Triggered by: IoT Core Rule (SidewalkUplinkRule)
Topic:        sidewalk/uplink

Receives a Sidewalk uplink from the nRF54L15 DK via IoT Wireless,
decodes the BME280 JSON payload, stores successful readings in DynamoDB,
and publishes a high-temperature SNS alert when the threshold is exceeded.

Current firmware payload format:
  Original JSON:
    {"sensor":"bme280","temp_c":23.400000,"pressure_kpa":99.873703,"humidity_pct":39.384765}

  Possible error JSON:
    {"sensor":"bme280","status":"error","err":-11}

  Encoded as:
    JSON string -> hex string -> base64 PayloadData

Environment variables:
  TABLE_NAME        DynamoDB table name
  ALERT_TOPIC_ARN   SNS topic ARN for alerts
  TEMP_THRESHOLD    Temperature C above which SNS fires, default 30
"""

import json
import boto3
import base64
import time
import os


# Initialized at module level and reused on warm Lambda invocations
ddb = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
sns = boto3.client("sns")

TOPIC = os.environ["ALERT_TOPIC_ARN"]
THRESH = float(os.environ.get("TEMP_THRESHOLD", 30))


def decode_bme280_payload(raw_b64):
    """
    Decode the current firmware payload format:

    PayloadData base64
      -> UTF-8 hex string
      -> UTF-8 JSON string
      -> Python dict
    """

    # Step 1: AWS gives PayloadData as base64.
    # Decoding it gives a hex string like:
    # 7b2273656e736f72223a22626d6532383022...
    hex_string = base64.b64decode(raw_b64).decode("utf-8")

    # Step 2: Convert the hex string back into the original JSON string.
    json_string = bytes.fromhex(hex_string).decode("utf-8")

    # Step 3: Parse the JSON string into a Python dictionary.
    return json.loads(json_string)


def lambda_handler(event, context):
    print("Raw event:", json.dumps(event))

    raw_b64 = event.get("PayloadData", "")
    device_id = event.get("WirelessDeviceId", "unknown")
    sidewalk = event.get("WirelessMetadata", {}).get("Sidewalk", {})
    msg_seq = sidewalk.get("Seq", -1)

    if not raw_b64:
        print("ERROR: PayloadData missing or empty")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "empty payload"
            })
        }

    # Decode PayloadData into JSON
    try:
        sensor_data = decode_bme280_payload(raw_b64)
    except Exception as e:
        print(f"ERROR: payload decode failed: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "payload decode failed",
                "details": str(e)
            })
        }

    print("Decoded JSON:", json.dumps(sensor_data))

    # Handle firmware-side BME280 read errors cleanly.
    # Example:
    # {"sensor":"bme280","status":"error","err":-11}
    if sensor_data.get("status") == "error":
        err_code = sensor_data.get("err", "unknown")
        sensor_name = sensor_data.get("sensor", "bme280")

        print(
            f"BME280 read failed: "
            f"device={device_id} "
            f"sensor={sensor_name} "
            f"err={err_code} "
            f"sidewalk_seq={msg_seq}"
        )

        # Optional: store the failed read in DynamoDB too.
        ts = str(int(time.time()))
        ttl = int(time.time()) + (30 * 24 * 3600)

        ddb.put_item(
            Item={
                "device_id": device_id,
                "timestamp": ts,
                "sensor": sensor_name,
                "status": "error",
                "err": str(err_code),
                "sidewalk_seq": msg_seq,
                "raw_payload": raw_b64,
                "decoded_payload": json.dumps(sensor_data),
                "ttl": ttl,
            }
        )

        print("DynamoDB error item written")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "device_id": device_id,
                "status": "sensor_error",
                "err": err_code
            })
        }

    # Extract successful BME280 readings
    try:
        sensor_name = sensor_data.get("sensor", "bme280")
        temperature_c = float(sensor_data["temp_c"])
        pressure_kpa = float(sensor_data["pressure_kpa"])
        humidity_pct = float(sensor_data["humidity_pct"])
    except Exception as e:
        print(f"ERROR: decoded JSON did not contain expected BME280 fields: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "bad sensor JSON",
                "details": str(e),
                "decoded": sensor_data
            })
        }

    print(
        f"Decoded: device={device_id} "
        f"sensor={sensor_name} "
        f"temp={temperature_c:.2f}C "
        f"pressure={pressure_kpa:.2f}kPa "
        f"humidity={humidity_pct:.2f}% "
        f"sidewalk_seq={msg_seq}"
    )

    # Write successful reading to DynamoDB
    ts = str(int(time.time()))
    ttl = int(time.time()) + (30 * 24 * 3600)

    ddb.put_item(
        Item={
            "device_id": device_id,
            "timestamp": ts,
            "sensor": sensor_name,
            "status": "ok",
            "temperature_c": str(round(temperature_c, 2)),
            "pressure_kpa": str(round(pressure_kpa, 2)),
            "humidity_pct": str(round(humidity_pct, 2)),
            "sidewalk_seq": msg_seq,
            "raw_payload": raw_b64,
            "decoded_payload": json.dumps(sensor_data),
            "ttl": ttl,
        }
    )

    print("DynamoDB item written")

    # High-temperature SNS alert
    if temperature_c > THRESH:
        sns.publish(
            TopicArn=TOPIC,
            Subject=f"[Sidewalk Alert] High temperature: {temperature_c:.2f}C",
            Message=(
                f"Device {device_id} reported {temperature_c:.2f}C, "
                f"above threshold of {THRESH:.2f}C.\n"
                f"Sensor:   {sensor_name}\n"
                f"Pressure: {pressure_kpa:.2f} kPa\n"
                f"Humidity: {humidity_pct:.2f}%\n"
                f"Time:     {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(int(ts)))}"
            ),
        )

        print(f"SNS alert sent: {temperature_c:.2f}C > {THRESH:.2f}C threshold")

    else:
        print(f"No SNS alert: {temperature_c:.2f}C <= {THRESH:.2f}C threshold")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "device_id": device_id,
            "status": "ok",
            "decoded": sensor_data
        })
    }