# Sidewalk Smart Home — AWS Backend
## nRF54L15 DK + Amazon Sidewalk + AWS IoT Core

Complete AWS infrastructure for the Sidewalk smart home project.
Deploys all cloud resources needed to receive sensor uplinks, store data,
send LED downlink commands, and view a live dashboard.

---

## What this deploys

| Resource | Name | Purpose |
|---|---|---|
| DynamoDB table | `SidewalkSensorData` | Stores all sensor readings (30-day TTL) |
| Lambda | `SidewalkUplinkDecoder` | Decodes 6-byte payload → DynamoDB + high-temp alert |
| Lambda | `SidewalkMotionAlert` | Sends SNS push notification on motion detection |
| Lambda | `SidewalkDashboardApi` | REST API for dashboard — GET /readings, /latest |
| Lambda | `SidewalkDownlink` | REST API for controls — POST /downlink |
| IoT Rule | `SidewalkUplinkRule` | Watches MQTT topic, triggers UplinkDecoder |
| IoT Rule | `SidewalkMotionRule` | Watches same topic, triggers MotionAlert |
| API Gateway | `SidewalkSmartHomeApi` | Public REST endpoints for dashboard + controls |
| S3 bucket | `sidewalk-dashboard-<account>` | Hosts the HTML dashboard |
| SNS topic | `SidewalkSmartHomeAlerts` | Email alerts for motion + high temperature |
| CloudWatch alarm | `SidewalkUplinkErrors` | Notifies on Lambda decode failures |
| IAM roles | 3 roles | Least-privilege roles for Lambda, IoT, API Gateway |

---

## Project structure

```
sidewalk-aws/
├── cloudformation/
│   └── sidewalk-stack.yaml          # All AWS resources in one template
├── lambda/
│   ├── uplink_decoder/index.py      # Decodes Sidewalk payload → DynamoDB
│   ├── motion_alert/index.py        # SNS notification on motion
│   ├── dashboard_api/index.py       # GET /readings, /latest
│   └── downlink/index.py            # POST /downlink → IoT Wireless
├── dashboard/
│   └── index.html                   # Live dashboard with charts + controls
└── scripts/
    ├── create_destination.py        # Creates IoT Wireless Destination
    ├── deploy.sh                    # Full deploy/teardown helper
    └── test_sidewalk.py             # CLI tool for testing
```

---

## Prerequisites

### AWS account
- IAM user with permissions to create: CloudFormation, Lambda, DynamoDB,
  IoT Core, IoT Wireless, API Gateway, S3, SNS, IAM roles, CloudWatch
- AWS CLI v2 installed and configured:
  ```bash
  aws configure
  # Region MUST be: us-east-1
  ```

### Python
```bash
pip install boto3
```

### Sidewalk hardware (physical prerequisites)
- nRF54L15 DK provisioned with `Nordic_MFG.hex` flashed
- Amazon Echo (3rd gen+) with Sidewalk enabled in the Alexa app
- Recent Ring Floodlight, Spotlight, and Dorbell PRo (2nd Gen +) also works
- All hardware physically located in the United States

---

## Deployment 

### Step 0: Confirm region
```bash
aws configure get region
# Must output: us-east-1
# If not: aws configure set region us-east-1. The only region this works is us-east-1!!!
```

### Step 1: Create the IoT Wireless Destination
This must be done **before** CloudFormation because the stack references it.
```bash
python3 scripts/create_destination.py \
    --destination SidewalkSmartHomeDest \
    --topic sidewalk/home/sensor \
    --region us-east-1
```

### Step 2: Deploy the CloudFormation stack
```bash
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
```

Or use the deploy script (handles all steps):
```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh deploy --email your@email.com
```

### Step 3: Confirm your email subscription
AWS SNS sends a confirmation email to the address you provided.
**You must click the confirmation link** or alerts will not be delivered. Make sure email is adjusted in  sidewalk-stack.yaml

### Step 4: Get the API endpoint
```bash
aws cloudformation describe-stacks \
    --stack-name sidewalk-smart-home \
    --query "Stacks[0].Outputs" \
    --output table
```

### Step 5: Upload the dashboard
Replace `__API_ENDPOINT__` in `dashboard/index.html` with your API endpoint:
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="sidewalk-dashboard-${ACCOUNT_ID}"
API_URL=$(aws cloudformation describe-stacks \
    --stack-name sidewalk-smart-home \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text)

sed "s|__API_ENDPOINT__|${API_URL}|g" dashboard/index.html > /tmp/dash.html
aws s3 cp /tmp/dash.html s3://${BUCKET}/index.html --content-type text/html
```

---

---

## Payload format

Important: The firmware and Lambda **must agree** on this byte layout:

```
Byte  0-1   int16   big-endian   Temperature in tenths of °C  (215 = 21.5°C)
Byte  2-3   int16   big-endian   Humidity in tenths of %RH    (552 = 55.2%)
Byte  4     uint8                Flags  (bit 0 = motion detected)
Byte  5     uint8                Sequence number (0–255, wraps)
```

Python struct format string: `'>hhBB'`

The `>` (big-endian) **must** match the firmware's byte encoding:
```c
// firmware payload_codec.c
payload[0] = (temp_raw >> 8) & 0xFF;  // high byte first
payload[1] = temp_raw & 0xFF;
```

---

## API reference

All endpoints at: `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod`

### GET /readings
Returns last N sensor readings in chronological order.
```
GET /readings?device_id=<id>&limit=50
```
Response: JSON array of reading objects.

### GET /latest
Returns the single most recent reading.
```
GET /latest?device_id=<id>
```
Response: Single JSON object.

### POST /downlink
Sends a command to the DK.
```
POST /downlink
Content-Type: application/json

{ "device_id": "abc-123", "command": "led_on" }
```
Valid commands: `led_on`, `led_off`, `led_toggle`

Custom payload:
```json
{ "device_id": "abc-123", "raw_hex": "02" }
```

---

## Testing

### Test without a physical DK (simulate uplinks)
```bash
python3 scripts/test_sidewalk.py --device test-device-001 simulate --count 20
```

### Send a downlink command
```bash
python3 scripts/test_sidewalk.py --device <your-device-id> downlink led_on
```

### Query recent readings
```bash
python3 scripts/test_sidewalk.py --device <your-device-id> readings --limit 10
```

### Watch Lambda logs live (requires awslogs or use CloudWatch console)
```bash
aws logs tail /aws/lambda/SidewalkUplinkDecoder --follow --region us-east-1
```

### Subscribe to MQTT test client
1. AWS Console → IoT Core → MQTT test client (us-east-1)
2. Subscribe to: `sidewalk/home/sensor`
3. Press Button 3 on the DK — message appears within ~5 seconds

---

## Teardown (delete all resources)

```bash
./scripts/deploy.sh teardown
```

Or manually:
```bash
# Empty and delete S3 bucket
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 rm s3://sidewalk-dashboard-${ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name sidewalk-smart-home --region us-east-1

# Delete the Destination (created separately, must be deleted separately)
aws iotwireless delete-destination --name SidewalkSmartHomeDest --region us-east-1
```

---

## Important notes

- **All AWS operations must be in us-east-1.** IoT Wireless does not work in other regions.
- **Never use `--recover` or `--chiperase` after flashing `Nordic_MFG.hex`** on the DK. Use `--sectorerase` only.
- **The 6-byte payload format is a contract.** Any change to the firmware encoder must be matched in the Lambda decoder (`struct.unpack('>hhBB', ...)`).
