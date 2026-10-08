from __future__ import annotations

from typing import Any, Dict, List

import boto3
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
# CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name: str):

    autoscaling = boto3.client(
        "autoscaling",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    compute_optimizer = boto3.client(
        "compute-optimizer",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return autoscaling, compute_optimizer, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(sts) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL AUTO SCALING GROUPS
# ============================================================

def fetch_all_auto_scaling_groups(
    autoscaling,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL Auto Scaling Groups
    in the specified region.

    Pagination is handled using boto3 paginator.
    """

    groups = []

    paginator = autoscaling.get_paginator(
        "describe_auto_scaling_groups"
    )

    for page in paginator.paginate():

        page_groups = page.get(
            "AutoScalingGroups",
            []
        )

        groups.extend(page_groups)

    return groups


# ============================================================
# FETCH COMPUTE OPTIMIZER ASG AUTOMATION INFORMATION
# ============================================================

def fetch_asg_automation_status(
    compute_optimizer,
    asg_name: str,
) -> Dict[str, Any]:
    """
    Fetch Compute Optimizer information for an ASG.

    The exact automation state is taken from the
    Compute Optimizer API response rather than being
    hardcoded.
    """

    try:

        response = compute_optimizer.get_auto_scaling_group_recommendations(
            autoScalingGroupArns=[
                asg_name
            ]
        )

        return response

    except ClientError as e:

        return {
            "error": str(e)
        }


# ============================================================
# EXTRACT TAGS
# ============================================================

def extract_tags(
    tags: List[Dict[str, Any]]
) -> Dict[str, str]:

    return {
        tag.get("Key"): tag.get("Value", "")
        for tag in tags
        if tag.get("Key")
    }


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_finding(
    asg: Dict[str, Any],
    automation_status: str,
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    asg_name = asg.get(
        "AutoScalingGroupName"
    )

    asg_arn = asg.get(
        "AutoScalingGroupARN"
    )

    min_size = asg.get(
        "MinSize"
    )

    max_size = asg.get(
        "MaxSize"
    )

    desired_capacity = asg.get(
        "DesiredCapacity"
    )

    tags = extract_tags(
        asg.get(
            "Tags",
            []
        )
    )

    resource_id = asg_name

    policy = (
        "compute-optimizer-asg-automation-disabled"
    )

    effort_level = "Low"

    message = (
        f"Compute Optimizer automation is "
        f"'{automation_status}' for ASG "
        f"{asg_name}. Enabling automation can "
        f"automatically apply approved Compute "
        f"Optimizer rightsizing recommendations."
    )

    recommendation = (
        f"Review Compute Optimizer recommendations "
        f"and consider enabling automation for ASG "
        f"{asg_name} if automated application of "
        f"approved rightsizing recommendations is "
        f"acceptable for this workload."
    )

    # --------------------------------------------------------
    # Service-specific information goes into description.
    # This keeps the Excel schema identical across scripts.
    # --------------------------------------------------------

    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"resourceId: {resource_id} | "
        f"resourceArn: {asg_arn} | "
        f"automationStatus: {automation_status} | "
        f"minSize: {min_size} | "
        f"maxSize: {max_size} | "
        f"desiredCapacity: {desired_capacity} | "
        f"tags: {tags} | "
        f"policy: {policy} | "
        f"message: {message} | "
        f"recommendation: {recommendation}"
    )

    return {

        # ----------------------------------------------------
        # Workflow & Tracking
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": resource_id,

        "title": (
            "Compute Optimizer Asg Automation Disabled"
        ),

        "category": (
            "Compute Optimizer Asg Automation Disabled"
        ),

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": ", ".join(
            f"{key}={value}"
            for key, value in tags.items()
        ),

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS Identity
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": resource_id,

        "resourceId": resource_id,

        "resourceArn": asg_arn,

        "service": "Compute Optimizer",

        # ----------------------------------------------------
        # FinOps Details
        # ----------------------------------------------------

        "type": "Automation Disabled",

        "policy": policy,

        "effortLevel": effort_level,

        "message": message,

        "recommendation": recommendation,

        "description": description,

        # ----------------------------------------------------
        # Cost & Savings
        #
        # Currently not calculated.
        # CUR + Athena can be added later.
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
# SCAN AUTO SCALING GROUPS
# ============================================================

def scan_compute_optimizer_asg_automation(
    region_name: str,
) -> Dict[str, Any]:

    autoscaling, compute_optimizer, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Automatically fetch ALL ASGs
    # --------------------------------------------------------

    asgs = fetch_all_auto_scaling_groups(
        autoscaling
    )

    findings = []

    total_asgs_scanned = 0

    # --------------------------------------------------------
    # Process every ASG
    # --------------------------------------------------------

    for asg in asgs:

        total_asgs_scanned += 1

        asg_name = asg.get(
            "AutoScalingGroupName"
        )

        asg_arn = asg.get(
            "AutoScalingGroupARN"
        )

        if not asg_arn:
            continue

        # ----------------------------------------------------
        # Get Compute Optimizer information
        # ----------------------------------------------------

        try:

            response = (
                compute_optimizer
                .get_auto_scaling_group_recommendations(
                    autoScalingGroupArns=[
                        asg_arn
                    ]
                )
            )

        except ClientError:

            # Compute Optimizer may not have
            # recommendation information for
            # this ASG.
            continue

        recommendations = response.get(
            "autoScalingGroupRecommendations",
            []
        )

        if not recommendations:
            continue

        recommendation = recommendations[0]

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Do not assume that every ASG returned by
        # Compute Optimizer is an automation finding.
        #
        # Extract the automation information from
        # the response when available.
        # ----------------------------------------------------

        automation_status = (
            recommendation.get(
                "effectiveRecommendationPreferences",
                {}
            ).get(
                "utilizationPreferences",
                {}
            )
        )

        # ----------------------------------------------------
        # Convert the returned information to text.
        #
        # This is intentionally kept in description so
        # service-specific API fields do not break the
        # standard Excel schema.
        # ----------------------------------------------------

        automation_text = str(
            automation_status
        )

        # ----------------------------------------------------
        # The finding should only be created when the
        # automation state is explicitly known to be
        # inactive/disabled.
        #
        # Do NOT mark an ASG as disabled simply because
        # Compute Optimizer returned no recommendation.
        # ----------------------------------------------------

        if automation_text.lower() not in (
            "inactive",
            "disabled",
            "false",
        ):
            continue

        finding = build_finding(
            asg=asg,
            automation_status="Inactive",
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

        "totalAsgsScanned": total_asgs_scanned,

        "totalAutomationDisabled": len(
            findings
        ),

        "findings": findings,
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    import json
    import pandas as pd

    # --------------------------------------------------------
    # Only REGION is supplied.
    #
    # ASGs are automatically discovered.
    # --------------------------------------------------------

    region = "us-east-1"

    result = scan_compute_optimizer_asg_automation(
        region
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    findings = result.get(
        "findings",
        []
    )

    if not findings:

        print(
            "\nNo Compute Optimizer ASG automation "
            "disabled findings found."
        )

    # --------------------------------------------------------
    # Flatten complex structures for Excel
    # --------------------------------------------------------

    flat_findings = []

    for finding in findings:

        flat_finding = {}

        for key, value in finding.items():

            if isinstance(
                value,
                (list, dict)
            ):

                flat_finding[key] = json.dumps(
                    value,
                    default=str,
                )

            else:

                flat_finding[key] = value

        flat_findings.append(
            flat_finding
        )

    # --------------------------------------------------------
    # Standard Excel column order
    # --------------------------------------------------------

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

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS,
    )

    excel_file = (
        "compute_optimizer_asg_automation_disabled.xlsx"
    )

    df.to_excel(
        excel_file,
        index=False,
    )

    print(
        f"\nResult successfully exported to "
        f"{excel_file}"
    )