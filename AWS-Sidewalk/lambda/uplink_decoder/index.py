"""
SidewalkUplinkDecoder — Lambda function

Triggered by: IoT Core Rule (SidewalkUplinkRule)
Topic:        sidewalk/home/sensor

Receives a Sidewalk uplink from the nRF54L15 DK via IoT Wireless,
decodes the 6-byte binary payload, stores the reading in DynamoDB,
and publishes a high-temperature SNS alert when the threshold is exceeded.

Payload format (matches firmware payload_codec.c):
  Bytes 0-1  int16  big-endian  temperature in tenths of °C  (215 = 21.5°C)
  Bytes 2-3  int16  big-endian  humidity in tenths of %RH    (552 = 55.2%)
  Byte  4    uint8              flags  (bit 0 = motion detected)
  Byte  5    uint8              sequence number (0-255, wraps)

Environment variables (set in CloudFormation):
  TABLE_NAME        DynamoDB table name
  ALERT_TOPIC_ARN   SNS topic ARN for alerts
  TEMP_THRESHOLD    Temperature °C above which SNS fires (default 30)
"""

import json
import boto3
import base64
import struct
import time
import os

# Initialised at module level — reused on warm invocations
ddb    = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
sns    = boto3.client('sns')
TOPIC  = os.environ['ALERT_TOPIC_ARN']
THRESH = float(os.environ.get('TEMP_THRESHOLD', 30))


def lambda_handler(event, context):
    print("Raw event:", json.dumps(event))

    #  Step 1: Extract the base64 payload string 
    raw_b64   = event.get('PayloadData', '')
    device_id = event.get('WirelessDeviceId', 'unknown')
    sidewalk  = event.get('WirelessMetadata', {}).get('Sidewalk', {})
    msg_seq   = sidewalk.get('Seq', -1)

    if not raw_b64:
        print("ERROR: PayloadData missing or empty")
        return {'statusCode': 400, 'body': 'empty payload'}

    #  Step 2: Base64 decode → raw bytes 
    try:
        raw = base64.b64decode(raw_b64)
    except Exception as e:
        print(f"ERROR: base64 decode failed: {e}")
        return {'statusCode': 400, 'body': f'base64 error: {e}'}

    if len(raw) < 6:
        print(f"ERROR: payload only {len(raw)} bytes, need 6")
        return {'statusCode': 400, 'body': 'payload too short'}

    #  Step 3: Struct unpack 
    # Format: > = big-endian, h = int16, h = int16, B = uint8, B = uint8
    # MUST match the byte order in firmware payload_codec.c:
    #   payload[0] = (temp_raw >> 8) & 0xFF;  // high byte first = big-endian
    #   payload[1] = temp_raw & 0xFF;
    temp_raw, hum_raw, flags, seq = struct.unpack('>hhBB', raw[:6])

    #  Step 4: Scale to real units 
    temperature_c = round(temp_raw / 10.0, 1)
    humidity_pct  = round(hum_raw  / 10.0, 1)
    motion        = bool(flags & 0x01)   # bit 0 of flags byte

    print(f"Decoded: device={device_id} temp={temperature_c}°C "
          f"hum={humidity_pct}% motion={motion} seq={seq} sidewalk_seq={msg_seq}")

    #  Step 5: Write to DynamoDB 
    ts  = str(int(time.time()))
    ttl = int(time.time()) + (30 * 24 * 3600)  # auto-delete after 30 days

    ddb.put_item(Item={
        'device_id':     device_id,
        'timestamp':     ts,
        'temperature_c': str(temperature_c),
        'humidity_pct':  str(humidity_pct),
        'motion':        motion,
        'seq':           seq,
        'sidewalk_seq':  msg_seq,
        'flags':         flags,
        'raw_payload':   raw_b64,
        'ttl':           ttl,
    })

    #  Step 6: High-temperature alert 
    if temperature_c > THRESH:
        sns.publish(
            TopicArn=TOPIC,
            Subject=f"[Sidewalk Alert] High temperature: {temperature_c}°C",
            Message=(
                f"Device {device_id} reported {temperature_c}°C — "
                f"above threshold of {THRESH}°C.\n"
                f"Humidity: {humidity_pct}%\n"
                f"Motion:   {motion}\n"
                f"Time:     {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(int(ts)))}"
            )
        )
        print(f"SNS alert sent: {temperature_c}°C > {THRESH}°C threshold")

    return {'statusCode': 200}
