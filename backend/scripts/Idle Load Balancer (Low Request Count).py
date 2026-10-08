# ============================================================
# AWS FinOps Policy: Idle Load Balancer (Low Request Count)
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import csv
import logging

from datetime import datetime, timedelta, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION
# ============================================================

import os
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

OUTPUT_FILE = "idle_load_balancer_low_request_count.xlsx"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

LOOKBACK_DAYS = 30


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

POLICY_TITLE = "Idle Load Balancer (Low Request Count)"

POLICY_CATEGORY = "Idle Load Balancer (Low Request Count)"

POLICY_SERVICE = "ELB"

POLICY_TAG = "DevOps"

POLICY_AREA_PATH = "AWS Cost Optimization"

POLICY_STATUS = "Pending for Review"

# ------------------------------------------------------------
# A Load Balancer is considered idle when:
#
# ALB:
#     RequestCount over 30 days <= 0
#
# NLB:
#     NewFlowCount over 30 days <= 0
#
# Gateway Load Balancer:
#     NewFlowCount over 30 days <= 0
# ------------------------------------------------------------

LOW_ACTIVITY_THRESHOLD = 0


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):

    elbv2 = boto3.client(
        "elbv2",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    elb = boto3.client(
        "elb",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return (
        elbv2,
        elb,
        cloudwatch,
        sts
    )


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_modern_load_balancers(elbv2):

    load_balancers = []

    try:

        paginator = elbv2.get_paginator(
            "describe_load_balancers"
        )

        for page in paginator.paginate():

            load_balancers.extend(
                page.get(
                    "LoadBalancers",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Error fetching ALB/NLB/GWLB: %s",
            e
        )

    logger.info(
        "ALB/NLB/GWLB resources found: %d",
        len(load_balancers)
    )

    return load_balancers


def fetch_all_classic_load_balancers(elb):

    load_balancers = []

    try:

        paginator = elb.get_paginator(
            "describe_load_balancers"
        )

        for page in paginator.paginate():

            load_balancers.extend(
                page.get(
                    "LoadBalancerDescriptions",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Error fetching Classic Load Balancers: %s",
            e
        )

    logger.info(
        "Classic Load Balancers found: %d",
        len(load_balancers)
    )

    return load_balancers


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_cloudwatch_metric_sum(
    cloudwatch,
    namespace,
    metric_name,
    dimensions,
    start_time,
    end_time
):

    total_value = 0.0

    try:

        response = cloudwatch.get_metric_statistics(

            Namespace=namespace,

            MetricName=metric_name,

            Dimensions=dimensions,

            StartTime=start_time,

            EndTime=end_time,

            # One-day datapoints.
            # We only need the total activity over
            # the complete lookback period.
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

            total_value += datapoint.get(
                "Sum",
                0
            )

    except ClientError as e:

        logger.warning(
            "Unable to retrieve %s/%s: %s",
            namespace,
            metric_name,
            e
        )

    return total_value


def get_load_balancer_metric(
    cloudwatch,
    load_balancer
):

    """
    Determine the correct CloudWatch metric
    based on the Load Balancer type.

    Application Load Balancer:
        AWS/ApplicationELB
        RequestCount

    Network Load Balancer:
        AWS/NetworkELB
        NewFlowCount

    Gateway Load Balancer:
        AWS/GatewayELB
        NewFlowCount
    """

    load_balancer_type = load_balancer.get(
        "Type"
    )

    load_balancer_arn = load_balancer.get(
        "LoadBalancerArn",
        ""
    )

    # --------------------------------------------------------
    # CloudWatch LoadBalancer dimension
    #
    # ARN:
    #
    # arn:aws:elasticloadbalancing:region:
    # account:loadbalancer/app/name/id
    #
    # Dimension:
    #
    # app/name/id
    # --------------------------------------------------------

    load_balancer_dimension = (
        load_balancer_arn.split(
            "loadbalancer/",
            1
        )[-1]
    )

    # --------------------------------------------------------
    # Select metric based on type
    # --------------------------------------------------------

    if load_balancer_type == "application":

        namespace = "AWS/ApplicationELB"

        metric_name = "RequestCount"

    elif load_balancer_type == "network":

        namespace = "AWS/NetworkELB"

        metric_name = "NewFlowCount"

    elif load_balancer_type == "gateway":

        namespace = "AWS/GatewayELB"

        metric_name = "NewFlowCount"

    else:

        return {
            "namespace": "",
            "metric_name": "",
            "metric_value": 0
        }

    dimensions = [
        {
            "Name": "LoadBalancer",
            "Value": load_balancer_dimension
        }
    ]

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    metric_value = get_cloudwatch_metric_sum(

        cloudwatch=cloudwatch,

        namespace=namespace,

        metric_name=metric_name,

        dimensions=dimensions,

        start_time=start_time,

        end_time=end_time
    )

    return {

        "namespace":
            namespace,

        "metric_name":
            metric_name,

        "metric_value":
            metric_value
    }


def get_classic_load_balancer_metric(
    cloudwatch,
    load_balancer_name
):

    """
    Classic ELB uses:

        Namespace:
            AWS/ELB

        Metric:
            RequestCount
    """

    dimensions = [
        {
            "Name": "LoadBalancer",
            "Value": load_balancer_name
        }
    ]

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    metric_value = get_cloudwatch_metric_sum(

        cloudwatch=cloudwatch,

        namespace="AWS/ELB",

        metric_name="RequestCount",

        dimensions=dimensions,

        start_time=start_time,

        end_time=end_time
    )

    return {

        "namespace":
            "AWS/ELB",

        "metric_name":
            "RequestCount",

        "metric_value":
            metric_value
    }


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_modern_load_balancer(
    load_balancer,
    cloudwatch,
    account_id,
    region_name
):

    load_balancer_name = load_balancer.get(
        "LoadBalancerName",
        ""
    )

    load_balancer_arn = load_balancer.get(
        "LoadBalancerArn",
        ""
    )

    load_balancer_type = load_balancer.get(
        "Type",
        ""
    )

    dns_name = load_balancer.get(
        "DNSName",
        ""
    )

    vpc_id = load_balancer.get(
        "VpcId",
        ""
    )

    state = (
        load_balancer.get(
            "State",
            {}
        ).get(
            "Code",
            ""
        )
    )

    scheme = load_balancer.get(
        "Scheme",
        ""
    )

    availability_zones = []

    for az in load_balancer.get(
        "AvailabilityZones",
        []
    ):

        zone_name = az.get(
            "ZoneName"
        )

        if zone_name:

            availability_zones.append(
                zone_name
            )

    # --------------------------------------------------------
    # Only evaluate active Load Balancers
    # --------------------------------------------------------

    if state != "active":

        logger.info(
            "Skipping %s because state is %s",
            load_balancer_name,
            state
        )

        return None

    # --------------------------------------------------------
    # Get CloudWatch activity
    # --------------------------------------------------------

    metric_data = get_load_balancer_metric(

        cloudwatch=cloudwatch,

        load_balancer=load_balancer
    )

    namespace = metric_data[
        "namespace"
    ]

    metric_name = metric_data[
        "metric_name"
    ]

    metric_value = metric_data[
        "metric_value"
    ]

    # --------------------------------------------------------
    # Unknown type
    # --------------------------------------------------------

    if not metric_name:

        logger.warning(
            "Unsupported Load Balancer type: %s",
            load_balancer_type
        )

        return None

    # --------------------------------------------------------
    # Evaluate activity
    # --------------------------------------------------------

    is_idle = metric_value <= LOW_ACTIVITY_THRESHOLD

    if is_idle:
        status_text = "Idle"
        recommendation_text = "Delete idle load balancer to save costs."
        effort_level = "Low"
        logger.info("%s is idle. %s = %.0f", load_balancer_name, metric_name, metric_value)
    else:
        status_text = "Active"
        recommendation_text = "Active Load Balancer. Keep."
        effort_level = "None"
        logger.info("%s is active. %s = %.0f", load_balancer_name, metric_name, metric_value)

    # --------------------------------------------------------
    # Activity is zero
    # --------------------------------------------------------

    if load_balancer_type == "application":

        activity_text = (
            f"Total requests in the last "
            f"{LOOKBACK_DAYS} days: "
            f"{metric_value:.0f}"
        )

    elif load_balancer_type == "network":

        activity_text = (
            f"Total new network flows in the last "
            f"{LOOKBACK_DAYS} days: "
            f"{metric_value:.0f}"
        )

    else:

        activity_text = (
            f"Total new flows in the last "
            f"{LOOKBACK_DAYS} days: "
            f"{metric_value:.0f}"
        )

    az_text = ", ".join(
        availability_zones
    )

    # --------------------------------------------------------
    # Build finding description
    # --------------------------------------------------------

    description = (

        f"Load Balancer "
        f"**{load_balancer_name}** "
        f"({load_balancer_type}) is {status_text}. "
        f"{activity_text}. "

        f"CloudWatch namespace: "
        f"{namespace}. "

        f"CloudWatch metric: "
        f"{metric_name}. "

        f"VPC: {vpc_id}. "

        f"Scheme: {scheme}. "

        f"DNS Name: {dns_name}. "

        f"Availability Zones: {az_text}. "

        f"Load Balancer ARN: "
        f"{load_balancer_arn}. "
    )

    return {
        "accountId": account_id,
        "region": region_name,
        "resourceNameOrId": load_balancer_name,
        "resourceArn": load_balancer_arn,
        "service": POLICY_SERVICE,
        "type": "Cost Optimization",
        "policy": POLICY_TITLE,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation_text,
        "description": description,
        "loadBalancerType": load_balancer_type,
        "metricName": metric_name,
        "metricValue": metric_value,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated"
    }


def evaluate_classic_load_balancer(
    load_balancer,
    cloudwatch,
    account_id,
    region_name
):

    load_balancer_name = load_balancer.get(
        "LoadBalancerName",
        ""
    )

    dns_name = load_balancer.get(
        "DNSName",
        ""
    )

    vpc_id = load_balancer.get(
        "VPCId",
        ""
    )

    scheme = load_balancer.get(
        "Scheme",
        ""
    )

    availability_zones = load_balancer.get(
        "AvailabilityZones",
        []
    )

    # --------------------------------------------------------
    # Get RequestCount
    # --------------------------------------------------------

    metric_data = get_classic_load_balancer_metric(

        cloudwatch=cloudwatch,

        load_balancer_name=load_balancer_name
    )

    metric_value = metric_data[
        "metric_value"
    ]

    metric_name = metric_data[
        "metric_name"
    ]

    namespace = metric_data[
        "namespace"
    ]

    # --------------------------------------------------------
    # Evaluate activity
    # --------------------------------------------------------

    is_idle = metric_value <= LOW_ACTIVITY_THRESHOLD

    if is_idle:
        status_text = "Idle"
        recommendation_text = "Delete idle classic load balancer to save costs."
        effort_level = "Low"
        logger.info("Classic ELB %s is idle. RequestCount = %.0f", load_balancer_name, metric_value)
    else:
        status_text = "Active"
        recommendation_text = "Active Load Balancer. Keep."
        effort_level = "None"
        logger.info("Classic ELB %s is active. RequestCount = %.0f", load_balancer_name, metric_value)

    # --------------------------------------------------------
    # Availability Zones
    # --------------------------------------------------------

    az_text = ", ".join(
        availability_zones
    )

    # --------------------------------------------------------
    # Build description
    # --------------------------------------------------------

    description = (

        f"Load Balancer "
        f"**{load_balancer_name}** "
        f"(classic) is {status_text}. "

        f"Total requests in the last "
        f"{LOOKBACK_DAYS} days: "
        f"{metric_value:.0f}. "

        f"CloudWatch namespace: "
        f"{namespace}. "

        f"CloudWatch metric: "
        f"{metric_name}. "

        f"VPC: {vpc_id}. "

        f"Scheme: {scheme}. "

        f"DNS Name: {dns_name}. "

        f"Availability Zones: {az_text}. "
    )

    return {
        "accountId": account_id,
        "region": region_name,
        "resourceNameOrId": load_balancer_name,
        "resourceArn": "",
        "service": POLICY_SERVICE,
        "type": "Cost Optimization",
        "policy": POLICY_TITLE,
        "effortLevel": effort_level,
        "status": status_text,
        "recommendation": recommendation_text,
        "description": description,
        "loadBalancerType": "classic",
        "metricName": metric_name,
        "metricValue": metric_value,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated"
    }


def evaluate_policy(
    elbv2,
    elb,
    cloudwatch,
    account_id,
    region_name
):

    findings = []

    # --------------------------------------------------------
    # ALB / NLB / GWLB
    # --------------------------------------------------------

    modern_load_balancers = (
        fetch_all_modern_load_balancers(
            elbv2
        )
    )

    for load_balancer in modern_load_balancers:

        finding = evaluate_modern_load_balancer(

            load_balancer=load_balancer,

            cloudwatch=cloudwatch,

            account_id=account_id,

            region_name=region_name
        )

        if finding:

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Classic ELB
    # --------------------------------------------------------

    classic_load_balancers = (
        fetch_all_classic_load_balancers(
            elb
        )
    )

    for load_balancer in classic_load_balancers:

        finding = evaluate_classic_load_balancer(

            load_balancer=load_balancer,

            cloudwatch=cloudwatch,

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

def export_to_excel(
    findings,
    filename: str,
):
    from typing import List, Dict, Any
    STANDARD_COLUMNS = [
        "workItemType", "state", "id", "title", "category", "owner",
        "assignedTo", "status", "areaPath", "tags", "commentCount",
        "accountId", "region", "resourceNameOrId", "resourceId",
        "resourceArn", "service", "type", "policy", "effortLevel",
        "message", "recommendation", "description", "currentDailyCost",
        "currentMonthlyCost", "estimatedMonthlySavings", "approvalComments",
        "reasonForRejection", "achievedSavingsMonthly", "month"
    ]

    flat_findings = []
    
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
                import json
                str_val = json.dumps(value, default=str)
            else:
                str_val = value

            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                extra_attributes.append(f"{key}: {str_val}")
                
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        
        for k, v in flat_finding.items():
            standard_row[k] = v
            
        existing_desc = standard_row.get("description", "")
        if existing_desc is None:
            existing_desc = ""
            
        if extra_attributes:
            extra_str = " | ".join(extra_attributes)
            if existing_desc:
                standard_row["description"] = f"{existing_desc} | {extra_str}"
            else:
                standard_row["description"] = extra_str
                
        flat_findings.append(standard_row)

    import pandas as pd
    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)
    logger.info(f"Excel report created: {filename}")


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "=================================================="
    )

    logger.info(
        "Starting FinOps Policy: %s",
        POLICY_TITLE
    )

    logger.info(
        "Lookback period: %d days",
        LOOKBACK_DAYS
    )

    scan_start = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # Get Account ID and Regions
    # --------------------------------------------------------

    # Create a base STS client to get account ID
    sts_base = boto3.client("sts", region_name=AWS_REGION, config=BOTO_CONFIG)
    account_id = get_account_id(sts_base)
    
    logger.info("Account ID: %s", account_id)

    # Use a base EC2 client to get all enabled regions
    ec2_base = boto3.client("ec2", region_name=AWS_REGION, config=BOTO_CONFIG)
    try:
        regions_response = ec2_base.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error("Failed to fetch AWS regions, falling back to %s: %s", AWS_REGION, e)
        regions = [AWS_REGION]

    logger.info("Discovered %d regions to scan.", len(regions))

    all_findings = []

    # --------------------------------------------------------
    # Evaluate policy across all regions
    # --------------------------------------------------------

    for region in regions:
        logger.info("\n========================================")
        logger.info("Scanning region: %s", region)
        logger.info("========================================")

        try:
            (
                elbv2_client,
                elb_client,
                cloudwatch_client,
                sts_client
            ) = create_clients(region)

            findings = evaluate_policy(
                elbv2=elbv2_client,
                elb=elb_client,
                cloudwatch=cloudwatch_client,
                account_id=account_id,
                region_name=region
            )
            
            all_findings.extend(findings)
            logger.info("Found %d candidates in %s", len(findings), region)
            
        except Exception as e:
            logger.error("Failed to evaluate region %s: %s", region, e)

    # --------------------------------------------------------
    # Generate Output
    # --------------------------------------------------------

    # Assuming write_csv works the same and just writes out the dictionary
    export_to_excel(
        findings=all_findings,
        filename=OUTPUT_FILE
    )

    scan_end = datetime.now(timezone.utc)
    scan_duration = (scan_end - scan_start).total_seconds()

    logger.info("\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info("Account ID       : %s", account_id)
    logger.info("Total Regions    : %d", len(regions))
    logger.info("Total Candidates : %d", len(all_findings))
    logger.info("Scan Duration    : %.2f seconds", scan_duration)
    logger.info("Output File      : %s", OUTPUT_FILE)
    logger.info("==================================================")


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()