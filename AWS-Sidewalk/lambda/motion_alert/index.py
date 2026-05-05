"""
SidewalkMotionAlert — Lambda function

Triggered by: IoT Core Rule (SidewalkMotionRule) — same topic as uplink rule.
Purpose:      Decodes the payload, checks the motion flag (bit 0 of flags byte),
              and publishes an SNS notification only when motion is confirmed.

Running both rules in parallel means the uplink decoder handles storage
and this function handles alerting — clean separation of concerns.
"""

import json
import boto3
import base64
import struct
import time
import os

sns   = boto3.client('sns')
TOPIC = os.environ['ALERT_TOPIC_ARN']


def lambda_handler(event, context):
    print("Motion check event:", json.dumps(event))

    raw_b64   = event.get('PayloadData', '')
    device_id = event.get('WirelessDeviceId', 'unknown')

    if not raw_b64:
        return {'statusCode': 400}

    try:
        raw = base64.b64decode(raw_b64)
        if len(raw) < 6:
            return {'statusCode': 400}

        _, _, flags, _ = struct.unpack('>hhBB', raw[:6])
        motion = bool(flags & 0x01)

    except Exception as e:
        print(f"Decode error: {e}")
        return {'statusCode': 400}

    if not motion:
        print(f"No motion flag set for device {device_id} — no alert sent")
        return {'statusCode': 200}

    ts = int(time.time())
    sns.publish(
        TopicArn=TOPIC,
        Subject="[Sidewalk Alert] Motion detected",
        Message=(
            f"Motion detected by device {device_id}.\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts))}\n\n"
            f"To investigate, query DynamoDB:\n"
            f"  device_id = {device_id}\n"
            f"  timestamp = {ts}"
        )
    )
    print(f"Motion SNS alert sent for device {device_id}")
    return {'statusCode': 200}
