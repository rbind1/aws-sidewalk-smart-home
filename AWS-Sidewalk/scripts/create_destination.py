#!/usr/bin/env python3
"""
create_destination.py

Creates the AWS IoT Wireless Destination that links incoming Sidewalk
uplinks to your MQTT topic. Run this BEFORE deploying the CloudFormation
stack (the destination must exist before the IoT Rule references it).

Usage:
    python3 create_destination.py \
        --destination SidewalkSmartHomeDest \
        --topic sidewalk/home/sensor \
        --region us-east-1

Requirements:
    pip install boto3
    AWS credentials configured (aws configure)
    MUST run in us-east-1 region
"""

import argparse
import boto3
import json
import sys


def get_account_id():
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']


def create_destination_role(iam, role_name: str, account_id: str, region: str, topic: str) -> str:
    """Create an IAM role that allows IoT Wireless to publish to IoT Core."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "iotwireless.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["iot:Publish", "iot:DescribeEndpoint"],
            "Resource": f"arn:aws:iot:{region}:{account_id}:topic/{topic}"
        }]
    }

    # Create or update role
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='IoT Wireless Sidewalk destination role'
        )
        role_arn = resp['Role']['Arn']
        print(f"  Created IAM role: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=role_name)['Role']['Arn']
        print(f"  IAM role already exists: {role_arn}")

    # Attach inline policy
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName='SidewalkDestinationPolicy',
        PolicyDocument=json.dumps(inline_policy)
    )
    print(f"  Inline policy attached to {role_name}")
    return role_arn


def create_destination(client, name: str, topic: str, role_arn: str) -> dict:
    """Create the IoT Wireless Destination."""
    try:
        resp = client.create_destination(
            Name=name,
            ExpressionType='MqttTopic',
            Expression=topic,
            RoleArn=role_arn,
            Description='Sidewalk uplink destination — smart home project',
            Tags=[
                {'Key': 'Project', 'Value': 'SidewalkSmartHome'},
            ]
        )
        print(f"  Destination created: {name}")
        return resp
    except client.exceptions.ConflictException:
        print(f"  Destination '{name}' already exists — skipping creation")
        return client.get_destination(Name=name)


def main():
    parser = argparse.ArgumentParser(description='Create Sidewalk IoT Wireless Destination')
    parser.add_argument('--destination', default='SidewalkSmartHomeDest',
                        help='Destination name (default: SidewalkSmartHomeDest)')
    parser.add_argument('--topic', default='sidewalk/home/sensor',
                        help='MQTT topic (default: sidewalk/home/sensor)')
    parser.add_argument('--region', default='us-east-1',
                        help='AWS region — MUST be us-east-1 for Sidewalk')
    args = parser.parse_args()

    if args.region != 'us-east-1':
        print("WARNING: Sidewalk IoT Wireless only works in us-east-1.")
        print(f"         You specified: {args.region}")
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        if confirm != 'y':
            sys.exit(1)

    session    = boto3.Session(region_name=args.region)
    client     = session.client('iotwireless')
    iam        = session.client('iam')
    account_id = get_account_id()

    print(f"\nAccount:     {account_id}")
    print(f"Region:      {args.region}")
    print(f"Destination: {args.destination}")
    print(f"MQTT topic:  {args.topic}\n")

    # Step 1: Create the IAM role for the destination
    print("Step 1: Creating IAM role for destination...")
    role_name = 'SidewalkDestinationRole'
    role_arn  = create_destination_role(iam, role_name, account_id, args.region, args.topic)

    # Step 2: Create the destination
    print("\nStep 2: Creating IoT Wireless Destination...")
    create_destination(client, args.destination, args.topic, role_arn)

    # Step 3: Verify
    print("\nStep 3: Verifying destination...")
    dest = client.get_destination(Name=args.destination)
    print(f"  Name:       {dest.get('Name')}")
    print(f"  Expression: {dest.get('Expression')}")
    print(f"  RoleArn:    {dest.get('RoleArn')}")

    print(f"\nDone. Destination '{args.destination}' is ready.")
    print("You can now deploy the CloudFormation stack:")
    print(f"  aws cloudformation deploy \\")
    print(f"    --template-file cloudformation/sidewalk-stack.yaml \\")
    print(f"    --stack-name sidewalk-smart-home \\")
    print(f"    --capabilities CAPABILITY_NAMED_IAM \\")
    print(f"    --parameter-overrides SidewalkDestinationName={args.destination} \\")
    print(f"                          AlertEmail=your@email.com")


if __name__ == '__main__':
    main()
