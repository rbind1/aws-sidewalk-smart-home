"""
SidewalkDashboardApi — Lambda function

Triggered by: API Gateway
  GET /readings?device_id=<id>&limit=<n>   → last N readings (oldest→newest)
  GET /latest?device_id=<id>               → single most recent reading

Used by the HTML dashboard to populate charts and the status card.
All responses include CORS headers so the browser can call from any origin.
"""

import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

ddb = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])


def decimal_default(obj):
    """JSON serialiser for DynamoDB Decimal types."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def cors_headers():
    return {
        'Access-Control-Allow-Origin':  '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
        'Content-Type': 'application/json',
    }


def lambda_handler(event, context):
    print("API event:", json.dumps(event))

    method = event.get('httpMethod', 'GET')
    path   = event.get('path', '/')
    params = event.get('queryStringParameters') or {}

    # Handle CORS preflight
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    device_id = params.get('device_id', 'unknown')
    limit     = min(int(params.get('limit', 50)), 200)

    try:
        if '/latest' in path:
            # Most recent single reading
            resp  = ddb.query(
                KeyConditionExpression=Key('device_id').eq(device_id),
                ScanIndexForward=False,
                Limit=1
            )
            items = resp.get('Items', [])
            body  = items[0] if items else {}

        else:
            # /readings — last N items, reversed to chronological order for charting
            resp  = ddb.query(
                KeyConditionExpression=Key('device_id').eq(device_id),
                ScanIndexForward=False,
                Limit=limit
            )
            items = resp.get('Items', [])
            items.reverse()
            body  = items

        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps(body, default=decimal_default)
        }

    except Exception as e:
        print(f"ERROR: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': str(e)})
        }
