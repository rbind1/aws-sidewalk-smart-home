import boto3
import json

lam = boto3.client('lambda', region_name='us-east-1')

event = {
    "WirelessDeviceId": "test-device-001",
    "PayloadData": "AQ8CAJAB",
    "WirelessMetadata": {
        "Sidewalk": {
            "Seq": 1,
            "MessageType": "CUSTOM_COMMAND_ID_NOTIFY"
        }
    }
}

print("Sending event:")
print(json.dumps(event, indent=2))

response = lam.invoke(
    FunctionName='SidewalkUplinkDecoder',
    InvocationType='RequestResponse',
    Payload=json.dumps(event).encode('utf-8')
)

result = json.loads(response['Payload'].read().decode('utf-8'))
print("\nLambda response:", result)
print("\nNow check: python scripts/test_sidewalk.py --device test-device-001 latest")