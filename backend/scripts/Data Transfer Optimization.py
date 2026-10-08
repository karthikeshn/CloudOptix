from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import boto3
import pandas as pd
import json

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# AWS CLIENT CONFIGURATION
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

POLICY_NAME = "data-transfer-optimization"

CATEGORY = "Data Transfer Optimization"

SERVICE_NAME = "Data Transfer"

LOOKBACK_DAYS = 30

# Minimum traffic threshold.
#
# This prevents very small amounts of traffic from creating
# unnecessary findings.
#
# 1 GB = 1024^3 bytes
MINIMUM_TRANSFER_GB = 1.0

MINIMUM_TRANSFER_BYTES = (
    MINIMUM_TRANSFER_GB * 1024 * 1024 * 1024
)


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name: str):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    ec2_logs = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return ec2, ec2_logs, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(sts) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL VPCS
# ============================================================

def fetch_all_vpcs(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Fetch all VPCs in the region.
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
# FETCH ALL VPC FLOW LOGS
# ============================================================

def fetch_all_flow_logs(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Fetch all VPC Flow Logs configured in the region.

    Pagination is handled using the boto3 paginator.
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
# FETCH FLOW LOG DESTINATION
# ============================================================

def get_flow_log_destination(
    flow_log: Dict[str, Any],
) -> str:

    destination = flow_log.get(
        "LogDestination"
    )

    if destination:
        return destination

    return flow_log.get(
        "LogGroupName",
        "Unknown"
    )


# ============================================================
# CHECK FLOW LOG FORMAT
# ============================================================

def is_accepted_flow_log(
    flow_log: Dict[str, Any],
) -> bool:
    """
    Only ACTIVE flow logs are useful for this scan.
    """

    status = flow_log.get(
        "FlowLogStatus"
    )

    return status == "ACTIVE"


# ============================================================
# CONVERT BYTES TO GB
# ============================================================

def bytes_to_gb(
    byte_count: int,
) -> float:

    return round(
        byte_count / (1024 ** 3),
        6,
    )


# ============================================================
# BUILD FLOW LOG METADATA
# ============================================================

def build_flow_log_metadata(
    flow_log: Dict[str, Any],
) -> Dict[str, Any]:

    return {

        "flowLogId": flow_log.get(
            "FlowLogId"
        ),

        "resourceId": flow_log.get(
            "ResourceId"
        ),

        "trafficType": flow_log.get(
            "TrafficType"
        ),

        "flowLogStatus": flow_log.get(
            "FlowLogStatus"
        ),

        "logDestination": get_flow_log_destination(
            flow_log
        ),

        "deliverLogsStatus": flow_log.get(
            "DeliverLogsStatus"
        ),

        "logFormat": flow_log.get(
            "LogFormat"
        ),

        "creationTime": (
            flow_log.get(
                "CreationTime"
            ).isoformat()
            if flow_log.get("CreationTime")
            else None
        ),

        "maxAggregationInterval": flow_log.get(
            "MaxAggregationInterval"
        ),
    }


# ============================================================
# CLASSIFY DATA TRANSFER TYPE
# ============================================================

def classify_transfer_type(
    flow_log: Dict[str, Any],
) -> str:
    """
    Determine the broad data-transfer category.

    This is intentionally conservative.

    VPC Flow Logs alone cannot reliably reproduce every
    AWS billing dimension such as:

        CA-DataTransfer-Out-Bytes
        EU-DataTransfer-Out-Bytes
        EU-DataTransfer-Regional-Bytes

    Those billing classifications require billing data.

    Therefore this function classifies the discovery as
    VPC/network data transfer.
    """

    traffic_type = flow_log.get(
        "TrafficType"
    )

    resource_id = flow_log.get(
        "ResourceId"
    )

    if traffic_type == "ALL":

        return (
            f"VPC network data transfer "
            f"for resource {resource_id}"
        )

    if traffic_type == "ACCEPT":

        return (
            f"Accepted VPC network data transfer "
            f"for resource {resource_id}"
        )

    if traffic_type == "REJECT":

        return (
            f"Rejected VPC network traffic "
            f"for resource {resource_id}"
        )

    return (
        f"VPC data transfer for "
        f"resource {resource_id}"
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_data_transfer_finding(
    flow_log: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    flow_log_id = flow_log.get(
        "FlowLogId"
    )

    resource_id = flow_log.get(
        "ResourceId"
    )

    traffic_type = flow_log.get(
        "TrafficType"
    )

    flow_log_status = flow_log.get(
        "FlowLogStatus"
    )

    log_destination = get_flow_log_destination(
        flow_log
    )

    transfer_type = classify_transfer_type(
        flow_log
    )

    policy = POLICY_NAME

    effort_level = "Medium"

    message = (
        f"VPC data transfer monitoring is enabled "
        f"for resource {resource_id} in {region_name}. "
        f"Flow Log {flow_log_id} is active with "
        f"traffic type {traffic_type}. "
        f"Review network traffic to identify "
        f"unnecessary cross-region, cross-AZ, "
        f"or internet data transfer."
    )

    recommendation = (
        "Review the source and destination of the "
        "network traffic. Where applicable, place "
        "communicating resources in the same AZ, "
        "use VPC endpoints for AWS service traffic, "
        "use CloudFront for internet-facing content, "
        "and review unnecessary cross-region traffic."
    )

    # --------------------------------------------------------
    # Service-specific information goes into description.
    # This preserves the standard Excel schema.
    # --------------------------------------------------------

    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"resourceId: {resource_id} | "
        f"flowLogId: {flow_log_id} | "
        f"trafficType: {traffic_type} | "
        f"flowLogStatus: {flow_log_status} | "
        f"logDestination: {log_destination} | "
        f"transferType: {transfer_type} | "
        f"lookbackDays: {LOOKBACK_DAYS} | "
        f"policy: {policy} | "
        f"message: {message} | "
        f"recommendation: {recommendation}"
    )

    # --------------------------------------------------------
    # Standardized 30-column schema
    # --------------------------------------------------------

    return {

        # ----------------------------------------------------
        # Workflow & Tracking
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": "",

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": "",

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS Identity
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": (
            resource_id
            if resource_id
            else flow_log_id
        ),

        "resourceId": (
            resource_id
            if resource_id
            else flow_log_id
        ),

        "resourceArn": "",

        "service": SERVICE_NAME,

        # ----------------------------------------------------
        # FinOps Details
        # ----------------------------------------------------

        "type": "Data Transfer",

        "policy": policy,

        "effortLevel": effort_level,

        "message": message,

        "recommendation": recommendation,

        "description": description,

        # ----------------------------------------------------
        # Cost & Savings
        #
        # Currently not populated because CUR/Athena
        # is intentionally not being used.
        # ----------------------------------------------------

        "currentDailyCost": "To be updated",

        "currentMonthlyCost": "To be updated",

        "estimatedMonthlySavings": "To be updated",

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": "",
    }


# ============================================================
# SCAN DATA TRANSFER CONFIGURATION
# ============================================================

def scan_data_transfer(
    region_name: str,
) -> Dict[str, Any]:

    ec2, ec2_logs, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Fetch VPCs
    # --------------------------------------------------------

    vpcs = fetch_all_vpcs(
        ec2
    )

    # --------------------------------------------------------
    # Fetch VPC Flow Logs
    # --------------------------------------------------------

    flow_logs = fetch_all_flow_logs(
        ec2_logs
    )

    # --------------------------------------------------------
    # Find active Flow Logs
    # --------------------------------------------------------

    active_flow_logs = []

    for flow_log in flow_logs:

        if is_accepted_flow_log(
            flow_log
        ):

            active_flow_logs.append(
                flow_log
            )

    # --------------------------------------------------------
    # Build findings
    # --------------------------------------------------------

    findings = []

    for flow_log in active_flow_logs:

        finding = build_data_transfer_finding(
            flow_log=flow_log,
            account_id=account_id,
            region_name=region_name,
        )

        findings.append(
            finding
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalVpcsScanned": len(
            vpcs
        ),

        "totalFlowLogsScanned": len(
            flow_logs
        ),

        "totalActiveFlowLogs": len(
            active_flow_logs
        ),

        "totalFindings": len(
            findings
        ),

        "findings": findings,
    }


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    result: Dict[str, Any],
    excel_file: str,
):

    findings = result.get(
        "findings",
        []
    )

    # --------------------------------------------------------
    # Standard column order
    # --------------------------------------------------------

    STANDARD_COLUMNS = [

        # Workflow & Tracking
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

        # AWS Identity
        "accountId",
        "region",
        "resourceNameOrId",
        "resourceId",
        "resourceArn",
        "service",

        # FinOps Details
        "type",
        "policy",
        "effortLevel",
        "message",
        "recommendation",
        "description",

        # Cost & Savings
        "currentDailyCost",
        "currentMonthlyCost",
        "estimatedMonthlySavings",
        "approvalComments",
        "reasonForRejection",
        "achievedSavingsMonthly",
        "month",
    ]

    # --------------------------------------------------------
    # Flatten findings for Excel
    # --------------------------------------------------------

    flat_findings = []

    for finding in findings:

        flat_finding = {}

        for column in STANDARD_COLUMNS:

            value = finding.get(
                column,
                ""
            )

            if isinstance(
                value,
                (dict, list)
            ):

                value = json.dumps(
                    value,
                    default=str
                )

            flat_finding[column] = value

        flat_findings.append(
            flat_finding
        )

    # --------------------------------------------------------
    # Create DataFrame with EXACT column order
    # --------------------------------------------------------

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS
    )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    df.to_excel(
        excel_file,
        index=False
    )

    print(
        f"\nResult successfully exported to "
        f"{excel_file}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Only REGION is supplied.
    #
    # VPCs and Flow Logs are discovered automatically.
    # --------------------------------------------------------

    region = "us-east-1"

    result = scan_data_transfer(
        region
    )

    # --------------------------------------------------------
    # Print JSON result
    # --------------------------------------------------------

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "data_transfer_optimization_report.xlsx"
    )

    export_to_excel(
        result=result,
        excel_file=excel_file,
    )

    # --------------------------------------------------------
    # No findings
    # --------------------------------------------------------

    if not result.get(
        "findings"
    ):

        print(
            "\nNo active VPC Flow Logs found."
        )

        print(
            "Data-transfer discovery using "
            "VPC Flow Logs requires Flow Logs "
            "to be enabled."
        )