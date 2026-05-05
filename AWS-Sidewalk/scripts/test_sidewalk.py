#!/usr/bin/env python3
"""
test_sidewalk.py — CLI tool for testing the Sidewalk smart home stack

Usage:
  python3 test_sidewalk.py --device <device-id> downlink led_on
  python3 test_sidewalk.py --device <device-id> downlink led_off
  python3 test_sidewalk.py --device <device-id> downlink led_toggle
  python3 test_sidewalk.py --device <device-id> readings --limit 10
  python3 test_sidewalk.py --device <device-id> latest
  python3 test_sidewalk.py simulate  --device <device-id>
    (simulates an uplink by posting directly to DynamoDB for testing)

Requirements:
  pip install boto3
  AWS CLI configured (aws configure) with us-east-1
"""

import argparse
import base64
import boto3
import json
import struct
import sys
import time
import random
from datetime import datetime


REGION = 'us-east-1'
TABLE  = 'SidewalkSensorData'

COMMANDS = {
    'led_off':    bytes([0x00]),
    'led_on':     bytes([0x01]),
    'led_toggle': bytes([0x02]),
}


def fmt_time(ts: str) -> str:
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        return ts


def send_downlink(device_id: str, command: str, raw_hex: str = None):
    """Send a downlink command to the DK via IoT Wireless."""
    client = boto3.client('iotwireless', region_name=REGION)

    if raw_hex:
        payload_bytes = bytes.fromhex(raw_hex)
        label = f'raw(0x{raw_hex})'
    elif command in COMMANDS:
        payload_bytes = COMMANDS[command]
        label = command
    else:
        print(f"ERROR: unknown command '{command}'. Valid: {list(COMMANDS.keys())}")
        sys.exit(1)

    payload_b64 = base64.b64encode(payload_bytes).decode()
    print(f"Sending downlink: device={device_id} command={label} "
          f"payload=0x{payload_bytes.hex()} ({payload_b64})")

    try:
        resp = client.send_data_to_wireless_device(
            Id=device_id,
            TransmitMode=0,
            PayloadData=payload_b64,
            WirelessMetadata={
                'Sidewalk': {
                    'Seq': 1,
                    'MessageType': 'CUSTOM_COMMAND_ID_NOTIFY',
                }
            }
        )
        print(f"OK — MessageId: {resp.get('MessageId')}")
        print("The DK should toggle its LED within ~10 seconds if connected.")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def get_readings(device_id: str, limit: int = 10):
    """Query the last N sensor readings from DynamoDB."""
    ddb = boto3.resource('dynamodb', region_name=REGION).Table(TABLE)
    from boto3.dynamodb.conditions import Key

    resp  = ddb.query(
        KeyConditionExpression=Key('device_id').eq(device_id),
        ScanIndexForward=False,
        Limit=limit
    )
    items = resp.get('Items', [])
    items.reverse()

    if not items:
        print(f"No readings found for device: {device_id}")
        return

    print(f"\n{'Time (UTC)':<22} {'Temp (°C)':<11} {'Hum (%)':<9} {'Motion':<8} {'Seq'}")
    print("─" * 62)
    for item in items:
        print(f"{fmt_time(item.get('timestamp','?')):<22} "
              f"{item.get('temperature_c','?'):<11} "
              f"{item.get('humidity_pct','?'):<9} "
              f"{'YES' if item.get('motion') else 'no':<8} "
              f"{item.get('seq','?')}")
    print(f"\nShowing {len(items)} of last {limit} readings for device {device_id}")


def get_latest(device_id: str):
    """Get the most recent reading."""
    ddb = boto3.resource('dynamodb', region_name=REGION).Table(TABLE)
    from boto3.dynamodb.conditions import Key

    resp  = ddb.query(
        KeyConditionExpression=Key('device_id').eq(device_id),
        ScanIndexForward=False,
        Limit=1
    )
    items = resp.get('Items', [])
    if not items:
        print(f"No readings found for device: {device_id}")
        return

    item = items[0]
    print(f"\nLatest reading for device: {device_id}")
    print(f"  Time:        {fmt_time(item.get('timestamp','?'))}")
    print(f"  Temperature: {item.get('temperature_c','?')} °C")
    print(f"  Humidity:    {item.get('humidity_pct','?')} %")
    print(f"  Motion:      {'YES' if item.get('motion') else 'no'}")
    print(f"  Sequence:    {item.get('seq','?')}")


def simulate_uplink(device_id: str, count: int = 5, interval: float = 2.0):
    """
    Write simulated sensor readings directly to DynamoDB.
    Used for testing the dashboard without a physical DK.
    Does NOT go through Sidewalk — purely for dashboard/API testing.
    """
    ddb = boto3.resource('dynamodb', region_name=REGION).Table(TABLE)
    print(f"Simulating {count} uplinks for device {device_id}...")

    base_temp = 21.5
    base_hum  = 52.0
    seq       = 0

    for i in range(count):
        temp_c   = round(base_temp + random.uniform(-1.5, 2.0), 1)
        hum_pct  = round(base_hum  + random.uniform(-3.0, 3.0), 1)
        motion   = random.random() < 0.3  # 30% chance of motion
        ts       = str(int(time.time()))
        ttl      = int(time.time()) + (30 * 24 * 3600)

        ddb.put_item(Item={
            'device_id':     device_id,
            'timestamp':     ts,
            'temperature_c': str(temp_c),
            'humidity_pct':  str(hum_pct),
            'motion':        motion,
            'seq':           seq,
            'sidewalk_seq':  -1,
            'flags':         1 if motion else 0,
            'raw_payload':   '(simulated)',
            'ttl':           ttl,
        })
        print(f"  [{i+1}/{count}] temp={temp_c}°C hum={hum_pct}% motion={motion} seq={seq}")
        seq = (seq + 1) % 256
        if i < count - 1:
            time.sleep(interval)

    print(f"\nDone. {count} simulated readings written to DynamoDB.")
    print("Open the dashboard to see them on the chart.")


def main():
    parser = argparse.ArgumentParser(description='Sidewalk Smart Home CLI test tool')
    parser.add_argument('--device', default='test-device-001',
                        help='Wireless Device ID from WirelessDevice.json')

    sub = parser.add_subparsers(dest='command')

    # downlink subcommand
    dl = sub.add_parser('downlink', help='Send a downlink command to the DK')
    dl.add_argument('action', choices=['led_on', 'led_off', 'led_toggle'],
                    help='Command to send')
    dl.add_argument('--raw', help='Send raw hex payload instead (e.g. 01)')

    # readings subcommand
    rd = sub.add_parser('readings', help='Show recent sensor readings from DynamoDB')
    rd.add_argument('--limit', type=int, default=10, help='Number of readings (default 10)')

    # latest subcommand
    sub.add_parser('latest', help='Show the most recent reading')

    # simulate subcommand
    sim = sub.add_parser('simulate', help='Write simulated readings to DynamoDB (no DK needed)')
    sim.add_argument('--count',    type=int,   default=5,   help='Number of readings (default 5)')
    sim.add_argument('--interval', type=float, default=2.0, help='Seconds between readings (default 2)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'downlink':
        send_downlink(args.device, args.action, args.raw)
    elif args.command == 'readings':
        get_readings(args.device, args.limit)
    elif args.command == 'latest':
        get_latest(args.device)
    elif args.command == 'simulate':
        simulate_uplink(args.device, args.count, args.interval)


if __name__ == '__main__':
    main()
