#!/usr/bin/env bash
# deploy.sh — Deploy or teardown the Sidewalk Smart Home AWS stack
# 
# Usage:
#   ./deploy.sh deploy   --email your@email.com [--destination MyDest]
#   ./deploy.sh teardown
#   ./deploy.sh status
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure) with us-east-1 as default region
#   - Python 3.8+ with boto3 installed
#   - Sufficient IAM permissions (see README.md)

set -euo pipefail

STACK_NAME="sidewalk-smart-home"
REGION="us-east-1"
TEMPLATE="cloudformation/sidewalk-stack.yaml"
DESTINATION="SidewalkSmartHomeDest"
ALERT_EMAIL="your@email.com"
TEMP_THRESHOLD="30"
MQTT_TOPIC="sidewalk/home/sensor"

#  Colour helpers 
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

#  Parse arguments 
COMMAND="${1:-deploy}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --email)       ALERT_EMAIL="$2";    shift 2 ;;
    --destination) DESTINATION="$2";   shift 2 ;;
    --threshold)   TEMP_THRESHOLD="$2"; shift 2 ;;
    --topic)       MQTT_TOPIC="$2";    shift 2 ;;
    *) error "Unknown argument: $1"; exit 1 ;;
  esac
done

#  Preflight checks 
check_prerequisites() {
  info "Checking prerequisites..."

  if ! command -v aws &>/dev/null; then
    error "AWS CLI not found. Install from https://aws.amazon.com/cli/"
    exit 1
  fi

  ACTUAL_REGION=$(aws configure get region 2>/dev/null || echo "")
  if [[ "$ACTUAL_REGION" != "us-east-1" ]]; then
    warn "Default region is '${ACTUAL_REGION:-not set}'. Sidewalk requires us-east-1."
    warn "Forcing region to us-east-1 for all commands."
  fi

  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
  info "AWS Account: $ACCOUNT_ID"
  info "Region:      $REGION"
}

#  Step 1: Create Destination 
create_destination() {
  info "Step 1/4: Creating IoT Wireless Destination..."
  python3 scripts/create_destination.py \
    --destination "$DESTINATION" \
    --topic       "$MQTT_TOPIC" \
    --region      "$REGION"
}

#  Step 2: Deploy CloudFormation stack 
deploy_stack() {
  info "Step 2/4: Deploying CloudFormation stack '${STACK_NAME}'..."
  info "  Alert email:     $ALERT_EMAIL"
  info "  Destination:     $DESTINATION"
  info "  Temp threshold:  ${TEMP_THRESHOLD}°C"
  info "  MQTT topic:      $MQTT_TOPIC"
  echo ""

  aws cloudformation deploy \
    --region           "$REGION" \
    --template-file    "$TEMPLATE" \
    --stack-name       "$STACK_NAME" \
    --capabilities     CAPABILITY_NAMED_IAM \
    --parameter-overrides \
      SidewalkDestinationName="$DESTINATION" \
      AlertEmail="$ALERT_EMAIL" \
      TemperatureAlertThresholdC="$TEMP_THRESHOLD" \
      MqttUplinkTopic="$MQTT_TOPIC"

  info "Stack deployed successfully."
}

#  Step 3: Upload dashboard 
upload_dashboard() {
  info "Step 3/4: Uploading dashboard to S3..."

  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
  BUCKET="sidewalk-dashboard-${ACCOUNT_ID}"
  API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region     "$REGION" \
    --query      "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output     text)

  # Inject the API URL into the dashboard HTML
  sed "s|__API_ENDPOINT__|${API_URL}|g" dashboard/index.html > /tmp/sidewalk-dashboard.html
  aws s3 cp /tmp/sidewalk-dashboard.html "s3://${BUCKET}/index.html" \
    --content-type text/html \
    --region "$REGION"

  DASHBOARD_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region     "$REGION" \
    --query      "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" \
    --output     text)

  info "Dashboard uploaded: $DASHBOARD_URL"
}

#  Step 4: Print summary 
print_summary() {
  info "Step 4/4: Deployment summary"
  echo ""
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region     "$REGION" \
    --query      "Stacks[0].Outputs[*].[OutputKey,OutputValue]" \
    --output     table

  echo ""
  info "Confirm your email subscription in the SNS alert email you received."
  info "Then flash your nRF54L15 DK and press Button 3 to send a test uplink."
  echo ""
  warn "IMPORTANT: Sidewalk only works in the United States."
  warn "           All hardware must be physically located in the US."
}

#  Teardown 
teardown() {
  warn "This will DELETE the CloudFormation stack and ALL resources (DynamoDB data, S3 bucket, etc.)"
  read -p "Type 'yes' to confirm: " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    info "Teardown cancelled."
    exit 0
  fi

  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
  BUCKET="sidewalk-dashboard-${ACCOUNT_ID}"

  info "Emptying S3 bucket ${BUCKET}..."
  aws s3 rm "s3://${BUCKET}" --recursive --region "$REGION" 2>/dev/null || true

  info "Deleting CloudFormation stack ${STACK_NAME}..."
  aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region     "$REGION"

  aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region     "$REGION"

  info "Stack deleted."
  warn "The IoT Wireless Destination was created separately and must be deleted manually:"
  warn "  aws iotwireless delete-destination --name $DESTINATION --region $REGION"
}

#  Status 
status() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region     "$REGION" \
    --query      "Stacks[0].{Status:StackStatus,Created:CreationTime,Updated:LastUpdatedTime,Outputs:Outputs}" \
    --output     json
}

#  Main 
case "$COMMAND" in
  deploy)
    check_prerequisites
    create_destination
    deploy_stack
    upload_dashboard
    print_summary
    ;;
  teardown)
    check_prerequisites
    teardown
    ;;
  status)
    status
    ;;
  *)
    error "Unknown command: $COMMAND"
    echo "Usage: $0 {deploy|teardown|status} [options]"
    exit 1
    ;;
esac
