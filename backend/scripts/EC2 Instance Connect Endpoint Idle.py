# ============================================================
# AWS FinOps Policy
# Policy: EC2 Instance Connect Endpoint Idle
# Service: EC2
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timedelta, timezone

from botocore.config import Config


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "ec2_instance_connect_endpoint_idle.xlsx"
)

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = (
    "Ec2 Instance Connect Endpoint Idle"
)

CATEGORY = (
    "Ec2 Instance Connect Endpoint Idle"
)

SERVICE = "EC2"

IDLE_LOOKBACK_DAYS = 30

# CloudWatch metric used to determine whether
# tunnels were opened through the endpoint.
CLOUDWATCH_NAMESPACE = (
    "AWS/EC2"
)

CLOUDWATCH_METRIC_NAME = (
    "ClientTunnelCount"
)

CLOUDWATCH_PERIOD_SECONDS = 86400


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return (
        ec2,
        cloudwatch,
        sts
    )


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_instance_connect_endpoints(
    ec2
):

    endpoints = []

    paginator = ec2.get_paginator(
        "describe_instance_connect_endpoints"
    )

    for page in paginator.paginate():

        endpoints.extend(
            page.get(
                "InstanceConnectEndpoints",
                []
            )
        )

    return endpoints


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_resource_tags(
    resource
):

    tags = {}

    for tag in resource.get(
        "Tags",
        []
    ):

        key = tag.get("Key")
        value = tag.get("Value")

        if key:

            tags[key] = value

    return tags


def get_tunnel_metrics(
    cloudwatch,
    endpoint_id
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=IDLE_LOOKBACK_DAYS
        )
    )

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricName=CLOUDWATCH_METRIC_NAME,
            Dimensions=[
                {
                    "Name": "InstanceConnectEndpointId",
                    "Value": endpoint_id
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=CLOUDWATCH_PERIOD_SECONDS,
            Statistics=[
                "Sum"
            ]
        )

    except Exception as error:

        return {
            "metric_available": False,
            "total_tunnels": None,
            "datapoints": 0,
            "error": str(error)
        }

    datapoints = response.get(
        "Datapoints",
        []
    )

    total_tunnels = 0

    for datapoint in datapoints:

        value = datapoint.get(
            "Sum",
            0
        )

        if value is not None:

            total_tunnels += value

    return {
        "metric_available": True,
        "total_tunnels": total_tunnels,
        "datapoints": len(
            datapoints
        ),
        "error": None
    }


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_endpoint(
    endpoint,
    cloudwatch,
    account_id,
    region
):

    endpoint_id = endpoint.get(
        "InstanceConnectEndpointId"
    )

    state = endpoint.get(
        "State"
    )

    state_message = endpoint.get(
        "StateMessage"
    )

    owner_id = endpoint.get(
        "OwnerId"
    )

    subnet_id = endpoint.get(
        "SubnetId"
    )

    security_group_ids = endpoint.get(
        "SecurityGroupIds",
        []
    )

    preserve_client_ip = endpoint.get(
        "PreserveClientIp"
    )

    network_interface_ids = endpoint.get(
        "NetworkInterfaceIds",
        []
    )

    created_at = endpoint.get(
        "CreatedAt"
    )

    tags = get_resource_tags(
        endpoint
    )

    # --------------------------------------------------------
    # Fetch CloudWatch tunnel activity.
    # --------------------------------------------------------

    metrics = get_tunnel_metrics(
        cloudwatch,
        endpoint_id
    )

    # --------------------------------------------------------
    # If metric is unavailable, do not incorrectly
    # classify the endpoint as idle.
    # --------------------------------------------------------

    if not metrics[
        "metric_available"
    ]:

        return {
            "candidate": False,
            "evaluation_status": (
                "Unable to evaluate"
            ),
            "reason": (
                "CloudWatch ClientTunnelCount "
                "metric could not be retrieved."
            ),
            "recommendation": (
                "Do not classify as idle until "
                "30-day tunnel activity can be verified."
            ),
            "account_id": account_id,
            "region": region,
            "endpoint_id": endpoint_id,
            "state": state,
            "state_message": state_message,
            "owner_id": owner_id,
            "subnet_id": subnet_id,
            "security_group_ids": security_group_ids,
            "preserve_client_ip": preserve_client_ip,
            "network_interface_ids": network_interface_ids,
            "created_at": created_at,
            "tags": tags,
            "total_tunnels": None,
            "datapoints": metrics[
                "datapoints"
            ]
        }

    total_tunnels = metrics[
        "total_tunnels"
    ]

    # --------------------------------------------------------
    # Policy condition:
    #
    # Endpoint must be available and have
    # zero tunnels during the last 30 days.
    # --------------------------------------------------------

    if (
        state == "available"
        and total_tunnels == 0
    ):

        candidate = True

        evaluation_status = (
            "Candidate"
        )

        reason = (
            f"EC2 Instance Connect Endpoint "
            f"had 0 tunnels opened during the "
            f"last {IDLE_LOOKBACK_DAYS} days."
        )

        recommendation = (
            "Delete the idle EC2 Instance Connect "
            "Endpoint after confirming it is no "
            "longer required. This removes the "
            "associated endpoint/availability "
            "charges."
        )

    else:

        candidate = False

        evaluation_status = (
            "Not a Candidate"
        )

        reason = (
            f"Endpoint state: {state} | "
            f"30-day tunnel count: "
            f"{total_tunnels}"
        )

        recommendation = (
            "Retain the EC2 Instance Connect "
            "Endpoint because recent tunnel "
            "activity was detected or the endpoint "
            "is not currently available."
        )

    return {
        "candidate": candidate,
        "evaluation_status": evaluation_status,
        "reason": reason,
        "recommendation": recommendation,
        "account_id": account_id,
        "region": region,
        "endpoint_id": endpoint_id,
        "state": state,
        "state_message": state_message,
        "owner_id": owner_id,
        "subnet_id": subnet_id,
        "security_group_ids": security_group_ids,
        "preserve_client_ip": preserve_client_ip,
        "network_interface_ids": network_interface_ids,
        "created_at": created_at,
        "tags": tags,
        "total_tunnels": total_tunnels,
        "datapoints": metrics[
            "datapoints"
        ]
    }


# ============================================================
# 9. Build FinOps Finding
# ============================================================

def build_finding(
    evaluation
):

    account_id = evaluation[
        "account_id"
    ]

    region = evaluation[
        "region"
    ]

    endpoint_id = evaluation[
        "endpoint_id"
    ]

    state = evaluation[
        "state"
    ]

    state_message = evaluation[
        "state_message"
    ]

    owner_id = evaluation[
        "owner_id"
    ]

    subnet_id = evaluation[
        "subnet_id"
    ]

    security_group_ids = evaluation[
        "security_group_ids"
    ]

    preserve_client_ip = evaluation[
        "preserve_client_ip"
    ]

    network_interface_ids = evaluation[
        "network_interface_ids"
    ]

    created_at = evaluation[
        "created_at"
    ]

    tags = evaluation[
        "tags"
    ]

    total_tunnels = evaluation[
        "total_tunnels"
    ]

    datapoints = evaluation[
        "datapoints"
    ]

    candidate = evaluation[
        "candidate"
    ]

    reason = evaluation[
        "reason"
    ]

    recommendation = evaluation[
        "recommendation"
    ]

    # --------------------------------------------------------
    # Created date
    # --------------------------------------------------------

    created_date_text = ""

    if created_at:

        created_date_text = (
            created_at.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # ARN
    # --------------------------------------------------------

    endpoint_arn = (
        f"arn:aws:ec2:{region}:"
        f"{account_id}:"
        f"instance-connect-endpoint/"
        f"{endpoint_id}"
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"EndpointId: {endpoint_id} | "
        f"EndpointARN: {endpoint_arn} | "
        f"State: {state} | "
        f"StateMessage: "
        f"{state_message or 'None'} | "
        f"CreatedDate: "
        f"{created_date_text} | "
        f"SubnetId: "
        f"{subnet_id or 'None'} | "
        f"SecurityGroups: "
        f"{security_group_ids} | "
        f"NetworkInterfaceIds: "
        f"{network_interface_ids} | "
        f"PreserveClientIp: "
        f"{preserve_client_ip} | "
        f"OwnerId: "
        f"{owner_id or 'None'} | "
        f"30DayTunnelCount: "
        f"{total_tunnels if total_tunnels is not None else 'Unavailable'} | "
        f"CloudWatchDatapoints: "
        f"{datapoints} | "
        f"Tags: {tags} | "
        f"Evaluation: {reason} | "
        f"Recommendation: {recommendation}"
    )

    # --------------------------------------------------------
    # Finding
    # --------------------------------------------------------

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_TITLE,
        "category": CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": (
            "Pending for Review"
            if candidate
            else "Not a Candidate"
        ),
        "areaPath": "AWS Cost Optimization",
        "tags": "",
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": endpoint_arn,
        "resourceId": endpoint_id,
        "resourceArn": endpoint_arn,
        "service": SERVICE,
        "type": "EC2 Instance Connect Endpoint",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "EC2 Instance Connect Endpoint is idle.",
        "recommendation": recommendation,
        "description": description,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "To be updated",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": ""
    }


# ============================================================
# 10. Main Execution
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 80)
    print("AWS FinOps Policy Scan")
    print("=" * 80)

    print(
        f"Policy : {POLICY_TITLE}"
    )

    print(
        f"Service: {SERVICE}"
    )

    print(
        f"Region : {REGION}"
    )

    print(
        f"Lookback: "
        f"{IDLE_LOOKBACK_DAYS} days"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        ec2,
        cloudwatch,
        sts
    ) = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"Account ID: {account_id}"
    )

    # --------------------------------------------------------
    # Fetch endpoints
    # --------------------------------------------------------

    print(
        "Fetching EC2 Instance Connect Endpoints..."
    )

    endpoints = (
        fetch_all_instance_connect_endpoints(
            ec2
        )
    )

    print(
        f"Endpoints scanned: "
        f"{len(endpoints)}"
    )

    # --------------------------------------------------------
    # Evaluate endpoints
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    for endpoint in endpoints:

        evaluation = evaluate_endpoint(
            endpoint,
            cloudwatch,
            account_id,
            REGION
        )

        if evaluation[
            "candidate"
        ]:

            candidate_count += 1

            finding = build_finding(
                evaluation
            )

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Fixed Excel Schema
    # --------------------------------------------------------

    columns = [
        "workItemType",
        "state",
        "id",
        "title",
        "category",
        "owner",
        "assignedTo",
        "status",
        "areaPath",
        "tags",
        "commentCount",
        "accountId",
        "region",
        "resourceNameOrId",
        "resourceId",
        "resourceArn",
        "service",
        "type",
        "policy",
        "effortLevel",
        "message",
        "recommendation",
        "description",
        "currentDailyCost",
        "currentMonthlyCost",
        "estimatedMonthlySavings",
        "approvalComments",
        "reasonForRejection",
        "achievedSavingsMonthly",
        "month"
    ]

    dataframe = pd.DataFrame(
        findings,
        columns=columns
    )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    dataframe.to_excel(
        OUTPUT_FILE,
        index=False
    )

    # --------------------------------------------------------
    # Scan duration
    # --------------------------------------------------------

    scan_end_time = datetime.now(
        timezone.utc
    )

    scan_duration = (
        scan_end_time -
        scan_start_time
    ).total_seconds()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)

    print(
        f"Account ID             : "
        f"{account_id}"
    )

    print(
        f"Region                 : "
        f"{REGION}"
    )

    print(
        f"Endpoints Scanned      : "
        f"{len(endpoints)}"
    )

    print(
        f"Idle Endpoints         : "
        f"{candidate_count}"
    )

    print(
        f"Lookback Period        : "
        f"{IDLE_LOOKBACK_DAYS} days"
    )

    print(
        f"Scan Duration          : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output           : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()