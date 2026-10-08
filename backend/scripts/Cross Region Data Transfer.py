
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import json
import re

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import pandas as pd


# ============================================================
# AWS CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "cross-az-data-transfer"

CATEGORY = "Cross Region Data Transfer"

SERVICE = "Data Transfer"

AREA_PATH = "AWS Cost Optimization"

WORK_ITEM_TYPE = "Task"

WORKFLOW_STATE = "To Do"

STATUS = "Pending for Review"

EFFORT_LEVEL = "Medium"

# Number of days to inspect in VPC Flow Logs.
LOOKBACK_DAYS = 30

# Minimum observed cross-AZ traffic required
# before creating a finding.
#
# This is a policy threshold, not a pricing calculation.
MIN_CROSS_AZ_GB = 100.0

# VPC Flow Logs destination type used by this script.
FLOW_LOG_DESTINATION_TYPE = "cloud-watch-logs"


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name: str):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    logs = boto3.client(
        "logs",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return ec2, logs, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(sts) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL VPCs
# ============================================================

def fetch_all_vpcs(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL VPCs in the supplied region.

    Pagination is handled using boto3 paginator.
    """

    vpcs = []

    paginator = ec2.get_paginator(
        "describe_vpcs"
    )

    for page in paginator.paginate():

        vpcs.extend(
            page.get(
                "Vpcs",
                []
            )
        )

    return vpcs


# ============================================================
# FETCH ALL SUBNETS
# ============================================================

def fetch_all_subnets(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Fetch all subnets in the region.

    Subnet -> Availability Zone mapping is required
    to identify cross-AZ communication.
    """

    subnets = []

    paginator = ec2.get_paginator(
        "describe_subnets"
    )

    for page in paginator.paginate():

        subnets.extend(
            page.get(
                "Subnets",
                []
            )
        )

    return subnets


# ============================================================
# BUILD SUBNET / ENI / AZ MAP
# ============================================================

def build_subnet_az_map(
    subnets: List[Dict[str, Any]]
) -> Dict[str, str]:

    subnet_az_map = {}

    for subnet in subnets:

        subnet_id = subnet.get(
            "SubnetId"
        )

        availability_zone = subnet.get(
            "AvailabilityZone"
        )

        if subnet_id and availability_zone:

            subnet_az_map[
                subnet_id
            ] = availability_zone

    return subnet_az_map


# ============================================================
# FETCH ALL NETWORK INTERFACES
# ============================================================

def fetch_all_network_interfaces(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Fetch all ENIs in the region.

    ENIs provide the relationship between
    private IP addresses and Availability Zones.
    """

    network_interfaces = []

    paginator = ec2.get_paginator(
        "describe_network_interfaces"
    )

    for page in paginator.paginate():

        network_interfaces.extend(
            page.get(
                "NetworkInterfaces",
                []
            )
        )

    return network_interfaces


# ============================================================
# BUILD IP -> AZ MAP
# ============================================================

def build_private_ip_az_map(
    network_interfaces: List[Dict[str, Any]],
    subnet_az_map: Dict[str, str],
) -> Dict[str, str]:
    """
    Build:

        Private IP -> Availability Zone

    This is useful when processing VPC Flow Logs.
    """

    ip_az_map = {}

    for eni in network_interfaces:

        subnet_id = eni.get(
            "SubnetId"
        )

        availability_zone = subnet_az_map.get(
            subnet_id
        )

        if not availability_zone:
            continue

        private_ip = eni.get(
            "PrivateIpAddress"
        )

        if private_ip:

            ip_az_map[
                private_ip
            ] = availability_zone

        # Secondary private IP addresses
        for private_ip_info in eni.get(
            "PrivateIpAddresses",
            []
        ):

            secondary_ip = private_ip_info.get(
                "PrivateIpAddress"
            )

            if secondary_ip:

                ip_az_map[
                    secondary_ip
                ] = availability_zone

    return ip_az_map


# ============================================================
# FETCH VPC FLOW LOGS
# ============================================================

def fetch_all_vpc_flow_logs(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Fetch all VPC Flow Logs configured in the region.

    Only Flow Logs delivered to CloudWatch Logs can be
    queried by the CloudWatch Logs Insights logic below.
    """

    flow_logs = []

    paginator = ec2.get_paginator(
        "describe_flow_logs"
    )

    for page in paginator.paginate():

        flow_logs.extend(
            page.get(
                "FlowLogs",
                []
            )
        )

    return flow_logs


# ============================================================
# FIND CLOUDWATCH LOG GROUPS
# ============================================================

def fetch_log_groups(
    logs,
) -> List[Dict[str, Any]]:
    """
    Fetch CloudWatch log groups.

    Pagination is handled using boto3 paginator.
    """

    log_groups = []

    paginator = logs.get_paginator(
        "describe_log_groups"
    )

    for page in paginator.paginate():

        log_groups.extend(
            page.get(
                "logGroups",
                []
            )
        )

    return log_groups


# ============================================================
# FIND FLOW LOG CLOUDWATCH DESTINATION
# ============================================================

def get_flow_log_cloudwatch_groups(
    flow_logs: List[Dict[str, Any]],
) -> List[str]:

    log_groups = []

    for flow_log in flow_logs:

        destination_type = flow_log.get(
            "LogDestinationType"
        )

        if destination_type != FLOW_LOG_DESTINATION_TYPE:
            continue

        destination = flow_log.get(
            "LogDestination"
        )

        if destination:
            log_groups.append(
                destination
            )

    return list(
        dict.fromkeys(
            log_groups
        )
    )


# ============================================================
# RUN CLOUDWATCH LOGS INSIGHTS QUERY
# ============================================================

def run_logs_insights_query(
    logs,
    log_group_name: str,
    start_time: datetime,
    end_time: datetime,
) -> List[Dict[str, Any]]:
    """
    Query VPC Flow Logs using CloudWatch Logs Insights.

    IMPORTANT:

    VPC Flow Log fields vary depending on the selected
    log format.

    This query assumes the standard fields:

        srcAddr
        dstAddr
        bytes

    The query identifies conversations where both source
    and destination IPs belong to different AZs.

    AZ classification itself is performed by the Python
    code after retrieving the flow records.
    """

    query_string = """
fields @timestamp, srcAddr, dstAddr, bytes
| filter ispresent(srcAddr)
| filter ispresent(dstAddr)
| filter ispresent(bytes)
| stats sum(bytes) as totalBytes by srcAddr, dstAddr
| sort totalBytes desc
"""

    try:

        response = logs.start_query(
            logGroupNames=[
                log_group_name
            ],
            startTime=int(
                start_time.timestamp()
            ),
            endTime=int(
                end_time.timestamp()
            ),
            queryString=query_string,
        )

    except ClientError:
        return []

    query_id = response.get(
        "queryId"
    )

    if not query_id:
        return []

    # --------------------------------------------------------
    # Poll Logs Insights query
    # --------------------------------------------------------

    for _ in range(60):

        try:

            result = logs.get_query_results(
                queryId=query_id
            )

        except ClientError:
            return []

        status = result.get(
            "status"
        )

        if status == "Complete":

            return result.get(
                "results",
                []
            )

        if status in (
            "Failed",
            "Cancelled",
        ):

            return []

        import time

        time.sleep(1)

    return []


# ============================================================
# CONVERT LOG INSIGHTS RESULT
# ============================================================

def parse_logs_insights_result(
    results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    records = []

    for result in results:

        record = {}

        for field in result:

            name = field.get(
                "field"
            )

            value = field.get(
                "value"
            )

            if name:

                record[
                    name
                ] = value

        records.append(
            record
        )

    return records


# ============================================================
# IDENTIFY CROSS-AZ TRAFFIC
# ============================================================

def calculate_cross_az_traffic(
    flow_records: List[Dict[str, Any]],
    ip_az_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Compare source and destination AZ.

    Example:

        10.0.1.10 -> us-east-1a
        10.0.2.10 -> us-east-1b

    Different AZs = cross-AZ traffic.

    Traffic is calculated from the bytes field returned
    by VPC Flow Logs.
    """

    cross_az_records = []

    for record in flow_records:

        source_ip = record.get(
            "srcAddr"
        )

        destination_ip = record.get(
            "dstAddr"
        )

        if not source_ip or not destination_ip:
            continue

        source_az = ip_az_map.get(
            source_ip
        )

        destination_az = ip_az_map.get(
            destination_ip
        )

        if not source_az or not destination_az:
            continue

        if source_az == destination_az:
            continue

        bytes_value = record.get(
            "totalBytes",
            0
        )

        try:
            total_bytes = float(
                bytes_value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        total_gb = (
            total_bytes
            / (
                1024 ** 3
            )
        )

        cross_az_records.append({

            "sourceIp": source_ip,

            "destinationIp": destination_ip,

            "sourceAz": source_az,

            "destinationAz": destination_az,

            "bytes": total_bytes,

            "gb": total_gb,
        })

    return cross_az_records


# ============================================================
# BUILD CROSS-AZ SUMMARY
# ============================================================

def build_cross_az_summary(
    cross_az_records: List[Dict[str, Any]]
) -> Dict[str, Any]:

    total_gb = 0.0

    pairs = []

    for record in cross_az_records:

        total_gb += record.get(
            "gb",
            0.0
        )

        pairs.append(
            {
                "sourceAz": record.get(
                    "sourceAz"
                ),
                "destinationAz": record.get(
                    "destinationAz"
                ),
                "gb": round(
                    record.get(
                        "gb",
                        0.0
                    ),
                    6,
                ),
            }
        )

    return {

        "totalCrossAzGB": round(
            total_gb,
            6,
        ),

        "pairs": pairs,
    }


# ============================================================
# BUILD STANDARD FINOPS FINDING
# ============================================================

def build_cross_az_finding(
    account_id: str,
    region_name: str,
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    IMPORTANT:

    This function returns ONLY the standardized schema.

    Service-specific information is stored in description.
    """

    total_cross_az_gb = summary.get(
        "totalCrossAzGB",
        0.0
    )

    policy = POLICY_NAME

    resource_id = "region-wide"

    resource_arn = (
        f"arn:aws:ec2:"
        f"{region_name}:"
        f"{account_id}:"
        f"vpc/*"
    )

    finding_type = (
        "High Cross-AZ Data Transfer"
    )

    message = (
        f"High estimated cross-AZ data transfer "
        f"({total_cross_az_gb:.6f} GB over "
        f"{LOOKBACK_DAYS} days) was detected in "
        f"{region_name}."
    )

    recommendation = (
        "Review the source and destination workloads "
        "generating cross-AZ traffic. Where architecturally "
        "appropriate, place communicating resources in the "
        "same Availability Zone, use suitable VPC endpoints "
        "or redesign the traffic path to reduce unnecessary "
        "cross-AZ data transfer. Validate availability, "
        "resilience and compliance requirements before "
        "changing placement."
    )

    # --------------------------------------------------------
    # Dynamic/service-specific attributes
    # are stored ONLY in description.
    # --------------------------------------------------------

    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"resourceId: {resource_id} | "
        f"type: {finding_type} | "
        f"policy: {policy} | "
        f"lookbackDays: {LOOKBACK_DAYS} | "
        f"crossAzGB: {total_cross_az_gb:.6f} | "
        f"thresholdGB: {MIN_CROSS_AZ_GB} | "
        f"pairs: "
        f"{json.dumps(summary.get('pairs', []), default=str)}"
    )

    return {

        # ----------------------------------------------------
        # Workflow & Tracking
        # ----------------------------------------------------

        "workItemType": WORK_ITEM_TYPE,

        "state": WORKFLOW_STATE,

        "id": "",

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": STATUS,

        "areaPath": AREA_PATH,

        "tags": "",

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS Identity
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": resource_id,

        "resourceId": resource_id,

        "resourceArn": resource_arn,

        "service": SERVICE,

        # ----------------------------------------------------
        # FinOps Details
        # ----------------------------------------------------

        "type": finding_type,

        "policy": policy,

        "effortLevel": EFFORT_LEVEL,

        "message": message,

        "recommendation": recommendation,

        "description": description,

        # ----------------------------------------------------
        # Cost & Savings
        #
        # CUR + Athena is intentionally NOT used.
        # ----------------------------------------------------

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",
    }


# ============================================================
# SCAN CROSS-AZ DATA TRANSFER
# ============================================================

def scan_cross_az_data_transfer(
    region_name: str,
) -> Dict[str, Any]:

    ec2, logs, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Fetch infrastructure information
    # --------------------------------------------------------

    subnets = fetch_all_subnets(
        ec2
    )

    subnet_az_map = build_subnet_az_map(
        subnets
    )

    network_interfaces = (
        fetch_all_network_interfaces(
            ec2
        )
    )

    ip_az_map = build_private_ip_az_map(
        network_interfaces,
        subnet_az_map,
    )

    # --------------------------------------------------------
    # Fetch VPC Flow Logs
    # --------------------------------------------------------

    flow_logs = fetch_all_vpc_flow_logs(
        ec2
    )

    cloudwatch_log_groups = (
        get_flow_log_cloudwatch_groups(
            flow_logs
        )
    )

    if not cloudwatch_log_groups:

        return {

            "accountId": account_id,

            "region": region_name,

            "totalSubnetsScanned": len(
                subnets
            ),

            "totalNetworkInterfacesScanned": len(
                network_interfaces
            ),

            "totalFlowLogsFound": len(
                flow_logs
            ),

            "totalCrossAzGB": 0.0,

            "findings": [],

            "message": (
                "No VPC Flow Logs configured for "
                "CloudWatch Logs were found. "
                "Cross-AZ traffic cannot be reliably "
                "calculated from the available data."
            ),
        }

    # --------------------------------------------------------
    # Time window
    # --------------------------------------------------------

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    # --------------------------------------------------------
    # Query every CloudWatch log group
    # --------------------------------------------------------

    all_flow_records = []

    for log_group_name in cloudwatch_log_groups:

        results = run_logs_insights_query(
            logs=logs,
            log_group_name=log_group_name,
            start_time=start_time,
            end_time=end_time,
        )

        records = parse_logs_insights_result(
            results
        )

        all_flow_records.extend(
            records
        )

    # --------------------------------------------------------
    # Identify cross-AZ traffic
    # --------------------------------------------------------

    cross_az_records = calculate_cross_az_traffic(
        flow_records=all_flow_records,
        ip_az_map=ip_az_map,
    )

    summary = build_cross_az_summary(
        cross_az_records
    )

    total_cross_az_gb = summary.get(
        "totalCrossAzGB",
        0.0
    )

    findings = []

    # --------------------------------------------------------
    # Apply policy threshold
    # --------------------------------------------------------

    if total_cross_az_gb >= MIN_CROSS_AZ_GB:

        finding = build_cross_az_finding(
            account_id=account_id,
            region_name=region_name,
            summary=summary,
        )

        findings.append(
            finding
        )

    # --------------------------------------------------------
    # Return scan result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "lookbackDays": LOOKBACK_DAYS,

        "totalSubnetsScanned": len(
            subnets
        ),

        "totalNetworkInterfacesScanned": len(
            network_interfaces
        ),

        "totalFlowLogsFound": len(
            flow_logs
        ),

        "cloudWatchLogGroupsQueried": len(
            cloudwatch_log_groups
        ),

        "totalFlowRecordsAnalyzed": len(
            all_flow_records
        ),

        "totalCrossAzRecords": len(
            cross_az_records
        ),

        "totalCrossAzGB": total_cross_az_gb,

        "totalFindings": len(
            findings
        ),

        "findings": findings,
    }


# ============================================================
# STANDARD EXCEL COLUMN ORDER
# ============================================================

STANDARD_COLUMNS = [

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
    "month",
]


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
):

    rows = []

    for finding in findings:

        row = {}

        for column in STANDARD_COLUMNS:

            value = finding.get(
                column
            )

            # Convert dictionaries/lists to text
            # so Excel receives a simple value.
            if isinstance(
                value,
                (dict, list)
            ):

                value = json.dumps(
                    value,
                    default=str
                )

            row[
                column
            ] = value

        rows.append(
            row
        )

    df = pd.DataFrame(
        rows,
        columns=STANDARD_COLUMNS
    )

    df.to_excel(
        filename,
        index=False
    )

    print(
        f"\nExcel report successfully "
        f"exported to {filename}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Only the REGION is supplied.
    #
    # VPCs, subnets, ENIs and VPC Flow Logs
    # are discovered automatically.

    region = "us-east-1"

    result = scan_cross_az_data_transfer(
        region
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )

    findings = result.get(
        "findings",
        []
    )

    if not findings:

        print(
            "\nNo cross-AZ data transfer "
            "policy findings detected."
        )

    export_to_excel(
        findings=findings,
        filename="cross_az_data_transfer_report.xlsx",
    )

