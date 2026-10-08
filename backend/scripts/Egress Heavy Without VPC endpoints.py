# ============================================================
# AWS FinOps Policy
# Policy: Egress Heavy Without VPC endpoints
# Service: VPC
# Resource: EC2 Instance
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timedelta, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "egress_heavy_without_vpc_endpoints.xlsx"
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
    "Egress Heavy Without VPC endpoints"
)

CATEGORY = (
    "Egress Heavy Without VPC endpoints"
)

SERVICE = "VPC"

RESOURCE_SERVICE = "EC2"

# Number of days used for traffic analysis.
LOOKBACK_DAYS = 30

# High outbound traffic threshold.
# Instance becomes a candidate when NetworkOut
# exceeds this amount over the lookback period.
EGRESS_THRESHOLD_GB = 100

# Approximate public internet data transfer rate
# used only as policy information.
# No savings calculation is performed from this value.
EGRESS_RATE_PER_GB = 0.09


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

def fetch_all_ec2_instances(ec2):

    instances = []

    paginator = ec2.get_paginator(
        "describe_instances"
    )

    for page in paginator.paginate():

        for reservation in page.get(
            "Reservations",
            []
        ):

            instances.extend(
                reservation.get(
                    "Instances",
                    []
                )
            )

    return instances


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_instance_vpc_details(
    ec2,
    instance
):

    instance_id = instance.get(
        "InstanceId"
    )

    vpc_id = instance.get(
        "VpcId"
    )

    subnet_id = instance.get(
        "SubnetId"
    )

    security_groups = [
        sg.get("GroupId")
        for sg in instance.get(
            "SecurityGroups",
            []
        )
        if sg.get("GroupId")
    ]

    return {
        "instance_id": instance_id,
        "vpc_id": vpc_id,
        "subnet_id": subnet_id,
        "security_groups": security_groups
    }


def get_vpc_endpoints(
    ec2,
    vpc_id
):

    if not vpc_id:

        return []

    endpoints = []

    paginator = ec2.get_paginator(
        "describe_vpc_endpoints"
    )

    try:

        for page in paginator.paginate(
            Filters=[
                {
                    "Name": "vpc-id",
                    "Values": [vpc_id]
                }
            ]
        ):

            endpoints.extend(
                page.get(
                    "VpcEndpoints",
                    []
                )
            )

    except ClientError:

        return []

    return endpoints


def get_cloudwatch_network_out(
    cloudwatch,
    instance_id
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="NetworkOut",
            Dimensions=[
                {
                    "Name": "InstanceId",
                    "Value": instance_id
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=[
                "Sum"
            ]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        total_bytes = 0

        for datapoint in datapoints:

            total_bytes += (
                datapoint.get(
                    "Sum",
                    0
                )
            )

        total_gb = (
            total_bytes /
            (1024 ** 3)
        )

        return {
            "available": True,
            "total_bytes": total_bytes,
            "total_gb": total_gb,
            "datapoints": len(
                datapoints
            )
        }

    except ClientError as error:

        return {
            "available": False,
            "total_bytes": 0,
            "total_gb": 0,
            "datapoints": 0,
            "error": str(error)
        }


def get_instance_name(instance):

    for tag in instance.get(
        "Tags",
        []
    ):

        if tag.get("Key") == "Name":

            return tag.get(
                "Value",
                ""
            )

    return ""


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_instance(
    ec2,
    cloudwatch,
    instance,
    account_id,
    region
):

    instance_id = instance.get(
        "InstanceId"
    )

    instance_state = (
        instance.get(
            "State",
            {}
        )
        .get(
            "Name"
        )
    )

    instance_type = instance.get(
        "InstanceType"
    )

    vpc_id = instance.get(
        "VpcId"
    )

    subnet_id = instance.get(
        "SubnetId"
    )

    availability_zone = (
        instance.get(
            "Placement",
            {}
        )
        .get(
            "AvailabilityZone"
        )
    )

    instance_name = (
        get_instance_name(
            instance
        )
    )

    # --------------------------------------------------------
    # Get NetworkOut for the last 30 days.
    # --------------------------------------------------------

    network_out = (
        get_cloudwatch_network_out(
            cloudwatch,
            instance_id
        )
    )

    # --------------------------------------------------------
    # If CloudWatch data is unavailable,
    # do not create a candidate.
    # --------------------------------------------------------

    if not network_out[
        "available"
    ]:

        return {
            "candidate": False,
            "evaluation_status": (
                "Unable to evaluate"
            ),
            "reason": (
                "Unable to retrieve EC2 "
                "NetworkOut CloudWatch metric."
            ),
            "recommendation": (
                "Retry the metric collection "
                "before evaluating this resource."
            ),
            "instance": instance,
            "network_out": network_out,
            "vpc_endpoints": [],
            "instance_id": instance_id,
            "account_id": account_id,
            "region": region
        }

    total_egress_gb = (
        network_out[
            "total_gb"
        ]
    )

    # --------------------------------------------------------
    # Get VPC endpoints.
    # --------------------------------------------------------

    vpc_endpoints = (
        get_vpc_endpoints(
            ec2,
            vpc_id
        )
    )

    endpoint_services = []

    endpoint_ids = []

    for endpoint in vpc_endpoints:

        endpoint_id = endpoint.get(
            "VpcEndpointId"
        )

        service_name = endpoint.get(
            "ServiceName"
        )

        if endpoint_id:

            endpoint_ids.append(
                endpoint_id
            )

        if service_name:

            endpoint_services.append(
                service_name
            )

    # --------------------------------------------------------
    # Determine whether relevant endpoints exist.
    # --------------------------------------------------------

    has_vpc_endpoints = (
        len(vpc_endpoints) > 0
    )

    # --------------------------------------------------------
    # Policy:
    #
    # High NetworkOut
    # +
    # No VPC endpoints
    #
    # -> Candidate
    # --------------------------------------------------------

    if (
        total_egress_gb >=
        EGRESS_THRESHOLD_GB
        and
        not has_vpc_endpoints
    ):

        candidate = True

        evaluation_status = (
            "Candidate"
        )

        reason = (
            f"EC2 instance generated approximately "
            f"{total_egress_gb:.2f} GB of NetworkOut "
            f"over the last {LOOKBACK_DAYS} days "
            f"and its VPC has no VPC endpoints."
        )

        recommendation = (
            "Review the destination services generating "
            "the outbound traffic. Where traffic is "
            "destined for AWS services that support "
            "VPC endpoints, configure the appropriate "
            "Gateway or Interface VPC endpoint and "
            "route eligible traffic through it."
        )

    elif (
        total_egress_gb >=
        EGRESS_THRESHOLD_GB
        and
        has_vpc_endpoints
    ):

        candidate = False

        evaluation_status = (
            "Not a Candidate"
        )

        reason = (
            f"EC2 instance generated approximately "
            f"{total_egress_gb:.2f} GB of NetworkOut "
            f"over the last {LOOKBACK_DAYS} days, "
            f"but the VPC already contains "
            f"{len(vpc_endpoints)} VPC endpoint(s)."
        )

        recommendation = (
            "Review endpoint coverage and confirm that "
            "eligible AWS-service traffic is actually "
            "using the available endpoints."
        )

    else:

        candidate = False

        evaluation_status = (
            "Not a Candidate"
        )

        reason = (
            f"EC2 instance generated approximately "
            f"{total_egress_gb:.2f} GB of NetworkOut "
            f"over the last {LOOKBACK_DAYS} days, "
            f"which is below the configured "
            f"{EGRESS_THRESHOLD_GB} GB threshold."
        )

        recommendation = (
            "No action required for this policy."
        )

    return {
        "candidate": candidate,
        "evaluation_status": evaluation_status,
        "reason": reason,
        "recommendation": recommendation,
        "instance": instance,
        "network_out": network_out,
        "vpc_endpoints": vpc_endpoints,
        "endpoint_ids": endpoint_ids,
        "endpoint_services": endpoint_services,
        "instance_id": instance_id,
        "account_id": account_id,
        "region": region,
        "vpc_id": vpc_id,
        "subnet_id": subnet_id,
        "instance_type": instance_type,
        "instance_state": instance_state,
        "availability_zone": availability_zone,
        "instance_name": instance_name
    }


# ============================================================
# 9. Build Standard Finding
# ============================================================

def build_finding(
    evaluation
):

    instance = evaluation[
        "instance"
    ]

    account_id = evaluation[
        "account_id"
    ]

    region = evaluation[
        "region"
    ]

    instance_id = evaluation[
        "instance_id"
    ]

    instance_name = evaluation[
        "instance_name"
    ]

    vpc_id = evaluation[
        "vpc_id"
    ]

    subnet_id = evaluation[
        "subnet_id"
    ]

    instance_type = evaluation[
        "instance_type"
    ]

    instance_state = evaluation[
        "instance_state"
    ]

    availability_zone = evaluation[
        "availability_zone"
    ]

    network_out = evaluation[
        "network_out"
    ]

    vpc_endpoints = evaluation[
        "vpc_endpoints"
    ]

    endpoint_ids = evaluation.get(
        "endpoint_ids",
        []
    )

    endpoint_services = evaluation.get(
        "endpoint_services",
        []
    )

    reason = evaluation[
        "reason"
    ]

    recommendation = evaluation[
        "recommendation"
    ]

    candidate = evaluation[
        "candidate"
    ]

    # --------------------------------------------------------
    # Instance ARN
    # --------------------------------------------------------

    instance_arn = (
        f"arn:aws:ec2:"
        f"{region}:"
        f"{account_id}:"
        f"instance/"
        f"{instance_id}"
    )

    # --------------------------------------------------------
    # Traffic details
    # --------------------------------------------------------

    total_egress_gb = (
        network_out.get(
            "total_gb",
            0
        )
    )

    datapoints = (
        network_out.get(
            "datapoints",
            0
        )
    )

    # --------------------------------------------------------
    # VPC endpoint details
    # --------------------------------------------------------

    endpoint_count = len(
        vpc_endpoints
    )

    # --------------------------------------------------------
    # Tags
    # --------------------------------------------------------

    tags = {}

    for tag in instance.get(
        "Tags",
        []
    ):

        key = tag.get(
            "Key"
        )

        value = tag.get(
            "Value"
        )

        if key:

            tags[key] = value

    # --------------------------------------------------------
    # Description
    #
    # All service-specific information is kept here.
    # No service-specific Excel columns are introduced.
    # --------------------------------------------------------

    description = (
        f"InstanceId: "
        f"{instance_id} | "
        f"InstanceName: "
        f"{instance_name or 'None'} | "
        f"InstanceType: "
        f"{instance_type} | "
        f"InstanceState: "
        f"{instance_state} | "
        f"AvailabilityZone: "
        f"{availability_zone} | "
        f"VpcId: "
        f"{vpc_id} | "
        f"SubnetId: "
        f"{subnet_id} | "
        f"NetworkOutLast{LOOKBACK_DAYS}DaysGB: "
        f"{total_egress_gb:.2f} | "
        f"NetworkOutDatapoints: "
        f"{datapoints} | "
        f"VPCEndpointsCount: "
        f"{endpoint_count} | "
        f"VPCEndpointIds: "
        f"{endpoint_ids} | "
        f"VPCEndpointServices: "
        f"{endpoint_services} | "
        f"EgressThresholdGB: "
        f"{EGRESS_THRESHOLD_GB} | "
        f"ReferenceEgressRatePerGB: "
        f"${EGRESS_RATE_PER_GB:.2f} | "
        f"Tags: "
        f"{tags} | "
        f"Evaluation: "
        f"{reason} | "
        f"Recommendation: "
        f"{recommendation}"
    )

    # --------------------------------------------------------
    # Standard Finding
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
        "resourceNameOrId": (
            instance_id
        ),
        "resourceId": instance_id,
        "resourceArn": instance_arn,
        "service": SERVICE,
        "type": RESOURCE_SERVICE,
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": (
            reason
        ),
        "recommendation": (
            recommendation
        ),
        "description": description,
        "currentDailyCost": (
            "To be updated"
        ),
        "currentMonthlyCost": (
            "To be updated"
        ),
        "estimatedMonthlySavings": "",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": ""
    }


# ============================================================
# 10. Scan Function
# ============================================================

def scan_region(
    region_name
):

    (
        ec2,
        cloudwatch,
        sts
    ) = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    print(
        f"Account ID: {account_id}"
    )

    print(
        f"Region: {region_name}"
    )

    print(
        "Fetching EC2 instances..."
    )

    instances = (
        fetch_all_ec2_instances(
            ec2
        )
    )

    print(
        f"EC2 instances scanned: "
        f"{len(instances)}"
    )

    findings = []

    candidate_count = 0

    unable_to_evaluate_count = 0

    for instance in instances:

        # ----------------------------------------------------
        # Skip terminated instances.
        # ----------------------------------------------------

        instance_state = (
            instance
            .get(
                "State",
                {}
            )
            .get(
                "Name"
            )
        )

        if instance_state == "terminated":

            continue

        # ----------------------------------------------------
        # Evaluate instance.
        # ----------------------------------------------------

        evaluation = evaluate_instance(
            ec2,
            cloudwatch,
            instance,
            account_id,
            region_name
        )

        if evaluation[
            "evaluation_status"
        ] == "Unable to evaluate":

            unable_to_evaluate_count += 1

            continue

        # ----------------------------------------------------
        # Only output actual candidates.
        # ----------------------------------------------------

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

    return {
        "account_id": account_id,
        "region": region_name,
        "instances_scanned": len(
            instances
        ),
        "candidate_count": candidate_count,
        "unable_to_evaluate_count": (
            unable_to_evaluate_count
        ),
        "findings": findings
    }


# ============================================================
# 11. Excel Export
# ============================================================

def export_to_excel(
    findings,
    output_file
):

    # --------------------------------------------------------
    # Fixed 30-column schema
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

    dataframe.to_excel(
        output_file,
        index=False
    )

    return dataframe


# ============================================================
# 12. Main
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 80)
    print("AWS FinOps Policy Scan")
    print("=" * 80)

    print(
        f"Policy                 : "
        f"{POLICY_TITLE}"
    )

    print(
        f"Service                : "
        f"{SERVICE}"
    )

    print(
        f"Resource               : "
        f"{RESOURCE_SERVICE}"
    )

    print(
        f"Region                 : "
        f"{REGION}"
    )

    print(
        f"Lookback               : "
        f"{LOOKBACK_DAYS} days"
    )

    print(
        f"Egress Threshold       : "
        f"{EGRESS_THRESHOLD_GB} GB"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Scan region
    # --------------------------------------------------------

    result = scan_region(
        REGION
    )

    findings = result[
        "findings"
    ]

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    export_to_excel(
        findings,
        OUTPUT_FILE
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
        f"Account ID                 : "
        f"{result['account_id']}"
    )

    print(
        f"Region                     : "
        f"{REGION}"
    )

    print(
        f"EC2 Instances Scanned      : "
        f"{result['instances_scanned']}"
    )

    print(
        f"Egress Heavy Candidates    : "
        f"{result['candidate_count']}"
    )

    print(
        f"Unable To Evaluate         : "
        f"{result['unable_to_evaluate_count']}"
    )

    print(
        f"Egress Threshold           : "
        f"{EGRESS_THRESHOLD_GB} GB / "
        f"{LOOKBACK_DAYS} days"
    )

    print(
        f"Scan Duration              : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output               : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":

    main()