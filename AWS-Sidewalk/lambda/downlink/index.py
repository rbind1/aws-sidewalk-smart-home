"""
SidewalkDownlink — Lambda function

Triggered by: API Gateway  POST /downlink

Accepts a JSON body:
  { "device_id": "abc-123", "command": "led_on" }
  or
  { "device_id": "abc-123", "raw_hex": "01" }   ← custom byte payload

Commands:
  led_off    → 0x00
  led_on     → 0x01
  led_toggle → 0x02

The payload byte must match the switch() in the firmware on_msg_received() callback.
"""

import json
import boto3
import base64
import os

iotwireless = boto3.client('iotwireless', region_name='us-east-1')

# Command name -> byte payload mapping
# Must match firmware downlink handler switch statement
COMMANDS = {
    'led_off':    bytes([0x00]),
    'led_on':     bytes([0x01]),
    'led_toggle': bytes([0x02]),
}


def cors_headers():
    return {
        'Access-Control-Allow-Origin':  '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Content-Type': 'application/json',
    }


def lambda_handler(event, context):
    print("Downlink event:", json.dumps(event))

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    # Parse body
    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return {'statusCode': 400, 'headers': cors_headers(),
                'body': json.dumps({'error': 'invalid JSON body'})}

    device_id = body.get('device_id')
    command   = body.get('command')
    raw_hex   = body.get('raw_hex')

    if not device_id:
        return {'statusCode': 400, 'headers': cors_headers(),
                'body': json.dumps({'error': 'device_id is required'})}

    # Resolve payload bytes
    if raw_hex:
        try:
            payload_bytes = bytes.fromhex(raw_hex)
        except ValueError:
            return {'statusCode': 400, 'headers': cors_headers(),
                    'body': json.dumps({'error': f'invalid raw_hex: {raw_hex}'})}
    elif command:
        if command not in COMMANDS:
            return {'statusCode': 400, 'headers': cors_headers(),
                    'body': json.dumps({
                        'error': f'unknown command: {command}',
                        'valid_commands': list(COMMANDS.keys())
                    })}
        payload_bytes = COMMANDS[command]
    else:
        return {'statusCode': 400, 'headers': cors_headers(),
                'body': json.dumps({'error': 'supply either command or raw_hex'})}

    payload_b64 = base64.b64encode(payload_bytes).decode()

    try:
        resp = iotwireless.send_data_to_wireless_device(
            Id=device_id,
            TransmitMode=0,   # 0 = unicast, send once
            PayloadData=payload_b64,
            WirelessMetadata={
                'Sidewalk': {
                    'Seq': 1,
                    'MessageType': 'CUSTOM_COMMAND_ID_NOTIFY',
                }
            }
        )
        msg_id = resp.get('MessageId', 'unknown')
        print(f"Downlink sent: device={device_id} cmd={command or 'raw'} "
              f"payload=0x{payload_bytes.hex()} msgId={msg_id}")
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({
                'message_id':  msg_id,
                'command':     command or 'raw',
                'payload_hex': payload_bytes.hex(),
                'device_id':   device_id,
            })
        }

    except iotwireless.exceptions.ResourceNotFoundException:
        return {'statusCode': 404, 'headers': cors_headers(),
                'body': json.dumps({'error': f'device not found: {device_id}'})}
    except Exception as e:
        print(f"ERROR sending downlink: {e}")
        return {'statusCode': 500, 'headers': cors_headers(),
                'body': json.dumps({'error': str(e)})}
