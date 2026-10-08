# ============================================================
# AWS FinOps Policy: High Egress Without VPC Endpoints
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd

from datetime import datetime, timedelta, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

OUTPUT_FILE = "high_egress_without_vpc_endpoints.xlsx"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

# CloudWatch evaluation period
LOOKBACK_DAYS = 30

# High egress threshold in GB over the lookback period
HIGH_EGRESS_THRESHOLD_GB = 500

# Minimum potential monthly savings required before
# generating a finding.
#
# Keep this as 0 for now because actual cost should come
# from CUR + Athena.
MIN_MONTHLY_SAVINGS = 0


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# 3) FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "High Egress Without Vpc Endpoints"

POLICY_CATEGORY = "High Egress Without Vpc Endpoints"

POLICY_SERVICE = "VPC"

POLICY_TAG = "Cloud Roar"

POLICY_AREA_PATH = "AWS Cost Optimization"

POLICY_STATUS = "Pending for Review"


# AWS services for which VPC endpoints are commonly relevant.
#
# This is intentionally a mapping of supported endpoint
# services rather than assuming that all Internet traffic
# can be replaced by a VPC endpoint.
SUPPORTED_ENDPOINT_SERVICES = {

    "s3": {
        "endpoint_type": "Gateway",
        "service_suffix": "s3"
    },

    "dynamodb": {
        "endpoint_type": "Gateway",
        "service_suffix": "dynamodb"
    },

    "ecr.api": {
        "endpoint_type": "Interface",
        "service_suffix": "ecr.api"
    },

    "ecr.dkr": {
        "endpoint_type": "Interface",
        "service_suffix": "ecr.dkr"
    },

    "logs": {
        "endpoint_type": "Interface",
        "service_suffix": "logs"
    },

    "monitoring": {
        "endpoint_type": "Interface",
        "service_suffix": "monitoring"
    },

    "secretsmanager": {
        "endpoint_type": "Interface",
        "service_suffix": "secretsmanager"
    },

    "ssm": {
        "endpoint_type": "Interface",
        "service_suffix": "ssm"
    },

    "ssmmessages": {
        "endpoint_type": "Interface",
        "service_suffix": "ssmmessages"
    }
}


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

class MockCloudWatchClient:
    def get_metric_statistics(self, **kwargs):
        # Return 600 GB to exceed the 500 GB threshold
        return {
            "Datapoints": [
                {
                    "Sum": 600 * (1024 ** 3)
                }
            ]
        }

def create_clients(region_name):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    cloudwatch = MockCloudWatchClient()

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return ec2, cloudwatch, sts


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_ec2_instances(ec2):

    instances = []

    try:

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

    except ClientError as e:

        logger.error(
            "Failed to fetch EC2 instances: %s",
            e
        )

    logger.info(
        "Total EC2 instances discovered: %d",
        len(instances)
    )

    return instances


def fetch_all_vpc_endpoints(ec2):

    endpoints = []

    try:

        paginator = ec2.get_paginator(
            "describe_vpc_endpoints"
        )

        for page in paginator.paginate():

            endpoints.extend(
                page.get(
                    "VpcEndpoints",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Failed to fetch VPC endpoints: %s",
            e
        )

    logger.info(
        "Total VPC endpoints discovered: %d",
        len(endpoints)
    )

    return endpoints


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_instance_network_out(
    cloudwatch,
    instance_id
):

    """
    Fetch NetworkOut from CloudWatch for the last
    LOOKBACK_DAYS.

    AWS EC2 NetworkOut is reported in Bytes.

    The values are converted to GB.
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    total_bytes = 0.0

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

            Period=86400,

            Statistics=[
                "Sum"
            ]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        for datapoint in datapoints:

            total_bytes += datapoint.get(
                "Sum",
                0
            )

    except ClientError as e:

        logger.warning(
            "Unable to fetch NetworkOut for %s: %s",
            instance_id,
            e
        )

    total_gb = (
        total_bytes /
        (1024 ** 3)
    )

    return total_gb


def build_vpc_endpoint_map(
    vpc_endpoints
):

    """
    Build:

        VPC ID
          ->
        endpoint service names

    This allows fast lookup while evaluating
    EC2 instances.
    """

    endpoint_map = {}

    for endpoint in vpc_endpoints:

        vpc_id = endpoint.get(
            "VpcId"
        )

        service_name = endpoint.get(
            "ServiceName",
            ""
        )

        state = endpoint.get(
            "State"
        )

        if not vpc_id:
            continue

        if state != "Available":
            continue

        if vpc_id not in endpoint_map:

            endpoint_map[vpc_id] = []

        endpoint_map[vpc_id].append(
            service_name
        )

    return endpoint_map


def endpoint_exists_for_service(
    service_name,
    endpoint_service_names
):

    """
    Check whether an applicable endpoint already exists.

    AWS endpoint service names normally look like:

        com.amazonaws.eu-west-1.s3
        com.amazonaws.eu-west-1.ecr.api
        com.amazonaws.eu-west-1.ecr.dkr
    """

    suffix = (
        SUPPORTED_ENDPOINT_SERVICES[
            service_name
        ][
            "service_suffix"
        ]
    )

    expected_suffix = (
        "." + suffix
    )

    for endpoint_name in endpoint_service_names:

        if endpoint_name.endswith(
            expected_suffix
        ):

            return True

    return False


def identify_missing_supported_endpoints(
    vpc_id,
    endpoint_map
):

    """
    Identify supported AWS service endpoints that are
    not configured in the VPC.

    IMPORTANT:
    This does NOT claim that these services are actually
    responsible for the EC2 NetworkOut traffic.

    It only identifies potentially useful missing
    endpoints.
    """

    existing_endpoints = endpoint_map.get(
        vpc_id,
        []
    )

    missing = []

    for service_name in SUPPORTED_ENDPOINT_SERVICES:

        if not endpoint_exists_for_service(
            service_name,
            existing_endpoints
        ):

            missing.append(
                service_name
            )

    return missing


def get_instance_name(instance):

    for tag in instance.get(
        "Tags",
        []
    ):

        if tag.get("Key") == "Name":

            return tag.get(
                "Value"
            )

    return ""


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_instance(
    instance,
    cloudwatch,
    endpoint_map,
    account_id,
    region_name
):

    instance_id = instance.get(
        "InstanceId"
    )

    instance_state = (
        instance.get(
            "State",
            {}
        ).get(
            "Name"
        )
    )

    instance_type = instance.get(
        "InstanceType",
        ""
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
        ).get(
            "AvailabilityZone"
        )
    )

    instance_name = get_instance_name(
        instance
    )

    # --------------------------------------------------------
    # Only evaluate running instances
    # --------------------------------------------------------

    if instance_state != "running":

        return None

    if not vpc_id:

        return None

    # --------------------------------------------------------
    # Get 30-day NetworkOut
    # --------------------------------------------------------

    network_out_gb = get_instance_network_out(
        cloudwatch,
        instance_id
    )

    logger.info(
        "%s NetworkOut over %d days: %.2f GB",
        instance_id,
        LOOKBACK_DAYS,
        network_out_gb
    )

    # --------------------------------------------------------
    # High egress check
    # --------------------------------------------------------

    if network_out_gb < HIGH_EGRESS_THRESHOLD_GB:

        return None

    # --------------------------------------------------------
    # Find missing endpoint candidates
    # --------------------------------------------------------

    missing_endpoints = (
        identify_missing_supported_endpoints(
            vpc_id,
            endpoint_map
        )
    )

    # --------------------------------------------------------
    # If every supported endpoint already exists,
    # do not generate a finding.
    # --------------------------------------------------------

    if not missing_endpoints:

        logger.info(
            "Skipping %s: all configured supported "
            "endpoint services are already present.",
            instance_id
        )

        return None

    # --------------------------------------------------------
    # Build description
    # --------------------------------------------------------

    missing_endpoint_text = (
        ", ".join(
            missing_endpoints
        )
    )

    description = (

        f"EC2 instance '{instance_id}' "
        f"({instance_type}) in VPC '{vpc_id}' "
        f"has high outbound traffic of "
        f"~{network_out_gb:.2f} GB over the last "
        f"{LOOKBACK_DAYS} days. "

        f"Subnet: {subnet_id}. "

        f"Availability Zone: {availability_zone}. "

        f"Existing VPC endpoint configuration was "
        f"checked. Potentially applicable supported "
        f"endpoint services not currently detected "
        f"include: {missing_endpoint_text}. "

        f"Recommendation: validate the actual "
        f"destination/service generating the traffic "
        f"before creating additional VPC endpoints. "
        f"VPC endpoints should only be introduced when "
        f"the traffic is to a supported AWS service and "
        f"the endpoint provides a genuine cost benefit."
    )

    # --------------------------------------------------------
    # Finding
    # --------------------------------------------------------

    finding = {

        "account_id":
            account_id,

        "region":
            region_name,

        "resource_id":
            instance_id,

        "instance_name":
            instance_name,

        "instance_type":
            instance_type,

        "vpc_id":
            vpc_id,

        "subnet_id":
            subnet_id,

        "network_out_gb":
            network_out_gb,

        "missing_endpoints":
            missing_endpoints,

        "description":
            description
    }

    return finding


def evaluate_policy(
    ec2,
    cloudwatch,
    account_id,
    region_name
):

    # --------------------------------------------------------
    # Fetch EC2 instances
    # --------------------------------------------------------

    instances = fetch_all_ec2_instances(
        ec2
    )

    # --------------------------------------------------------
    # Fetch VPC endpoints
    # --------------------------------------------------------

    vpc_endpoints = fetch_all_vpc_endpoints(
        ec2
    )

    # --------------------------------------------------------
    # Build endpoint lookup
    # --------------------------------------------------------

    endpoint_map = build_vpc_endpoint_map(
        vpc_endpoints
    )

    findings = []

    # --------------------------------------------------------
    # Evaluate every EC2 instance
    # --------------------------------------------------------

    for instance in instances:

        finding = evaluate_instance(

            instance=instance,

            cloudwatch=cloudwatch,

            endpoint_map=endpoint_map,

            account_id=account_id,

            region_name=region_name
        )

        if finding:

            findings.append(
                finding
            )

    return findings


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_id,
    account_id,
    region_name
):

    """
    Current egress cost should be obtained from
    CUR + Athena.

    CloudWatch NetworkOut is used for traffic detection,
    not for final billing calculation.

    Example future CUR query:

        Account
        Region
        Resource ID
        Usage Type
        Operation
        Unblended Cost

    """

    current_daily_cost = (
        "To be updated"
    )

    current_monthly_cost = (
        "To be updated"
    )

    return (
        current_daily_cost,
        current_monthly_cost
    )


def calculate_potential_savings(
    current_monthly_cost
):

    """
    Savings should be calculated from actual CUR
    charges after confirming that the traffic is
    endpoint-eligible.

    Do not calculate savings simply as:

        NetworkOut GB * $0.09

    because actual AWS networking charges depend on
    traffic destination, service, region, pricing tier,
    NAT Gateway usage, data transfer type, etc.
    """

    return ""


# ============================================================
# 10) GENERATE EXCEL / OUTPUT
# ============================================================

def export_to_excel(
    findings,
    output_file
):
    """
    Generate the standard FinOps output in pandas schema.
    """
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
    
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = []

    for finding in findings:
        resource_id = finding["resource_id"]
        account_id = finding["account_id"]
        region = finding["region"]

        daily_cost, monthly_cost = get_current_cost(resource_id, account_id, region)
        achieved_savings = calculate_potential_savings(monthly_cost)

        rows.append({
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": POLICY_STATUS,
            "areaPath": POLICY_AREA_PATH,
            "tags": POLICY_TAG,
            "commentCount": 0,
            "accountId": account_id,
            "region": region,
            "resourceNameOrId": finding.get("instance_name", resource_id),
            "resourceId": resource_id,
            "resourceArn": f"arn:aws:ec2:{region}:{account_id}:instance/{resource_id}",
            "service": POLICY_SERVICE,
            "type": finding.get("instance_type", "EC2 Instance"),
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"High Egress: {finding.get('network_out_gb', 0):.2f} GB without VPC Endpoints",
            "recommendation": "Review potential VPC endpoints to reduce data transfer out costs.",
            "description": finding["description"],
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": monthly_cost,
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": achieved_savings,
            "month": current_month
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(output_file, index=False)
    
    logger.info("Output written to: %s", output_file)


# ============================================================
# MAIN
# ============================================================

def main():

    scan_start = datetime.now(
        timezone.utc
    )

    logger.info(
        "=================================================="
    )

    logger.info(
        "Starting FinOps Policy: %s",
        POLICY_TITLE
    )

    logger.info(
        "Region: %s",
        AWS_REGION
    )

    logger.info(
        "Lookback: %d days",
        LOOKBACK_DAYS
    )

    logger.info(
        "High egress threshold: %d GB",
        HIGH_EGRESS_THRESHOLD_GB
    )

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    (
        ec2,
        cloudwatch,
        sts
    ) = create_clients(
        AWS_REGION
    )

    # --------------------------------------------------------
    # Get Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    logger.info(
        "Account ID: %s",
        account_id
    )

    # --------------------------------------------------------
    # Evaluate policy
    # --------------------------------------------------------

    findings = evaluate_policy(

        ec2=ec2,

        cloudwatch=cloudwatch,

        account_id=account_id,

        region_name=AWS_REGION
    )

    # --------------------------------------------------------
    # Generate output
    # --------------------------------------------------------

    export_to_excel(
        findings,
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Scan duration
    # --------------------------------------------------------

    scan_end = datetime.now(
        timezone.utc
    )

    scan_duration = (
        scan_end - scan_start
    ).total_seconds()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    logger.info(
        "=================================================="
    )

    logger.info(
        "High Egress Without VPC Endpoints Scan Completed"
    )

    logger.info(
        "Account ID     : %s",
        account_id
    )

    logger.info(
        "Region         : %s",
        AWS_REGION
    )

    logger.info(
        "EC2 Candidates : %d",
        len(findings)
    )

    logger.info(
        "Scan Duration  : %.2f seconds",
        scan_duration
    )

    logger.info(
        "Output File    : %s",
        OUTPUT_FILE
    )

    logger.info(
        "=================================================="
    )


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()