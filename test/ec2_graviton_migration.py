ec2_graviton_migration.py"""
EC2 Graviton Migration FinOps Analysis Script

Responsibility:
    RESOURCE DISCOVERY ONLY.

This script:
    1. Scans all enabled AWS regions.
    2. Discovers running EC2 instances using supported x86 families.
    3. Identifies an equivalent Graviton ARM instance type.
    4. Extracts only the metrics required by the pricing plugin.
    5. Calls the pricing plugin.
    6. Merges the financial metrics into the final finding.
    7. Exports standardized findings to XLSX.

Supported migration mappings:
    m5  -> m6g
    c5  -> c6g
    r5  -> r6g
    t3  -> t4g

Example:
    m5.large  -> m6g.large
    c5.large  -> c6g.large
    r5.xlarge -> r6g.xlarge
    t3.medium -> t4g.medium

Important:
    An EC2 instance must actually be compatible with ARM64 before migration.
    This script therefore flags the opportunity; it does not perform the
    migration.
"""

import os
import sys
from datetime import datetime, timezone

import boto3
import pandas as pd
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Import pricing plugin
# ---------------------------------------------------------------------------

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import ec2_graviton_pricing


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIRECTORY = os.environ.get(
    "FINOPS_OUTPUT_DIRECTORY",
    CURRENT_DIR
)

OUTPUT_FILENAME = os.environ.get(
    "FINOPS_OUTPUT_FILENAME",
    "ec2_graviton_migration.xlsx"
)


# ---------------------------------------------------------------------------
# Supported x86 -> Graviton family mappings
# ---------------------------------------------------------------------------

GRAVITON_FAMILY_MAP = {
    "m5": "m6g",
    "m5a": "m6g",
    "m5n": "m6gn",
    "m5dn": "m6gd",

    "c5": "c6g",
    "c5a": "c6g",
    "c5n": "c6gn",
    "c5d": "c6gd",

    "r5": "r6g",
    "r5a": "r6g",
    "r5n": "r6gn",
    "r5d": "r6gd",

    "t3": "t4g",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_account_id(sts_client):
    """
    Return the AWS account ID associated with the credentials.
    """
    return sts_client.get_caller_identity()["Account"]


def get_enabled_regions(ec2_client):
    """
    Return all AWS regions enabled for the account.

    If DescribeRegions fails, raise the error instead of silently returning
    partial results.
    """
    response = ec2_client.describe_regions(
        AllRegions=False
    )

    return sorted(
        region["RegionName"]
        for region in response["Regions"]
    )


def get_graviton_instance_type(instance_type):
    """
    Convert a supported x86 instance type to its Graviton equivalent.

    Example:
        m5.large -> m6g.large
        c5.2xlarge -> c6g.2xlarge
    """
    if not instance_type:
        return None

    parts = instance_type.split(".", 1)

    if len(parts) != 2:
        return None

    family, size = parts

    graviton_family = GRAVITON_FAMILY_MAP.get(family)

    if not graviton_family:
        return None

    return f"{graviton_family}.{size}"


def is_supported_instance(instance):
    """
    Return True when the instance is a running instance belonging to a
    supported x86 family.
    """
    if instance.get("State", {}).get("Name") != "running":
        return False

    instance_type = instance.get("InstanceType", "")

    family = instance_type.split(".", 1)[0]

    return family in GRAVITON_FAMILY_MAP


def get_instance_name(instance):
    """
    Extract the Name tag when present.
    """
    for tag in instance.get("Tags", []):
        if tag.get("Key") == "Name":
            return tag.get("Value")

    return None


def build_evaluation(
    instance,
    account_id,
    region
):
    """
    Build a resource-discovery-only evaluation.

    No financial calculations happen here.
    """

    instance_id = instance["InstanceId"]
    instance_type = instance["InstanceType"]

    graviton_instance_type = get_graviton_instance_type(
        instance_type
    )

    return {
        "accountId": account_id,
        "region": region,
        "resourceId": instance_id,
        "resourceNameOrId": (
            get_instance_name(instance) or instance_id
        ),
        "resourceArn": (
            f"arn:aws:ec2:{region}:{account_id}:"
            f"instance/{instance_id}"
        ),
        "currentInstanceType": instance_type,
        "targetInstanceType": graviton_instance_type,
        "resourceType": "EC2 Instance",
        "platform": instance.get("PlatformDetails", ""),
        "architecture": instance.get("Architecture", ""),
    }


def discover_region(ec2_client, account_id, region):
    """
    Discover all supported EC2 Graviton migration candidates in one region.
    """

    evaluations = []

    paginator = ec2_client.get_paginator(
        "describe_instances"
    )

    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):

                if not is_supported_instance(instance):
                    continue

                evaluation = build_evaluation(
                    instance=instance,
                    account_id=account_id,
                    region=region,
                )

                # Only retain candidates for which an equivalent
                # Graviton instance type was successfully identified.
                if not evaluation["targetInstanceType"]:
                    continue

                evaluations.append(evaluation)

    return evaluations


def build_final_finding(resource, financial_metrics):
    """
    Convert a discovery resource + financial metrics into the exact
    standardized dashboard ticket schema.
    """

    current_type = resource["currentInstanceType"]
    target_type = resource["targetInstanceType"]
    resource_id = resource["resourceId"]
    region = resource["region"]
    account_id = resource["accountId"]

    title = (
        f"Migrate EC2 {resource_id} "
        f"from {current_type} to {target_type}"
    )

    recommendation = (
        f"Evaluate migrating EC2 instance {resource_id} "
        f"from {current_type} to the equivalent Graviton "
        f"instance type {target_type}."
    )

    message = (
        f"EC2 instance {resource_id} is running on the x86-based "
        f"{current_type} family. The equivalent Graviton target "
        f"is {target_type}."
    )

    description = (
        f"The instance is a candidate for an architecture migration "
        f"from {current_type} (x86) to {target_type} (AWS Graviton/ARM64). "
        f"Validate application and AMI ARM64 compatibility before migration."
    )

    # IMPORTANT:
    # The dictionary below contains EXACTLY the keys requested by the
    # dashboard contract.
    finding = {
        "workItemType": "FinOps Optimization",
        "state": "New",
        "id": f"EC2-GRAVITON-{account_id}-{region}-{resource_id}",
        "title": title,
        "category": "EC2 Graviton Migration",
        "owner": "",
        "assignedTo": "",
        "status": "Open",
        "areaPath": "FinOps",
        "tags": (
            "AWS,EC2,Graviton,ARM64,"
            f"{current_type},{target_type}"
        ),
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": resource["resourceNameOrId"],
        "resourceId": resource_id,
        "resourceArn": resource["resourceArn"],
        "service": "EC2",
        "type": "Architecture Optimization",
        "policy": "Migrate eligible x86 EC2 workloads to Graviton",
        "effortLevel": "Medium",
        "message": message,
        "recommendation": recommendation,
        "description": description,

        # Financial values supplied by the pricing plugin.
        "currentDailyCost": financial_metrics["currentDailyCost"],
        "currentMonthlyCost": financial_metrics["currentMonthlyCost"],
        "estimatedMonthlySavings": financial_metrics[
            "estimatedMonthlySavings"
        ],

        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "$0.00",
        "month": datetime.now(timezone.utc).strftime("%Y-%m"),
    }

    expected_keys = [
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

    # Production safety check:
    if list(finding.keys()) != expected_keys:
        raise RuntimeError(
            "Final finding schema does not match the required contract."
        )

    return finding


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    """
    Main execution function.
    """

    # -----------------------------------------------------------------------
    # AWS session
    # -----------------------------------------------------------------------

    session = boto3.Session()

    sts_client = session.client("sts")

    account_id = get_account_id(sts_client)

    base_ec2_client = session.client("ec2")

    regions = get_enabled_regions(base_ec2_client)

    # -----------------------------------------------------------------------
    # PHASE 2 - RESOURCE DISCOVERY
    # -----------------------------------------------------------------------

    evaluations = []

    for region in regions:

        try:
            regional_ec2_client = session.client(
                "ec2",
                region_name=region
            )

            regional_evaluations = discover_region(
                ec2_client=regional_ec2_client,
                account_id=account_id,
                region=region,
            )

            evaluations.extend(regional_evaluations)

        except (ClientError, BotoCoreError) as exc:
            # One inaccessible region should not prevent processing of
            # other regions.
            print(
                f"[WARN] Unable to scan region {region}: {exc}",
                file=sys.stderr
            )

    # -----------------------------------------------------------------------
    # REQUIRED METRIC EXTRACTION
    #
    # Before building final findings, extract ONLY the metrics required
    # by the Pricing Plugin.
    # -----------------------------------------------------------------------

    pricing_resources = []

    for evaluation in evaluations:

        pricing_resources.append({
            "accountId": evaluation["accountId"],
            "region": evaluation["region"],
            "resourceId": evaluation["resourceId"],
            "resourceNameOrId": evaluation["resourceNameOrId"],
            "resourceArn": evaluation["resourceArn"],
            "resourceType": evaluation["resourceType"],
            "currentInstanceType": evaluation["currentInstanceType"],
            "targetInstanceType": evaluation["targetInstanceType"],
        })

    # -----------------------------------------------------------------------
    # PHASE 3 - COST RESOLUTION
    #
    # Pricing plugin returns the same dictionaries enriched with:
    # currentDailyCost
    # currentMonthlyCost
    # estimatedMonthlySavings
    # -----------------------------------------------------------------------

    enriched_resources = ec2_graviton_pricing.calculate_savings(
        discovered_resources=pricing_resources,
        account_id=account_id,
    )

    # -----------------------------------------------------------------------
    # PHASE 4 - FINAL FINDINGS
    # -----------------------------------------------------------------------

    findings = []

    for resource, financial_metrics in zip(
        pricing_resources,
        enriched_resources
    ):

        finding = build_final_finding(
            resource=resource,
            financial_metrics=financial_metrics,
        )

        findings.append(finding)

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    os.makedirs(
        OUTPUT_DIRECTORY,
        exist_ok=True
    )

    output_path = os.path.join(
        OUTPUT_DIRECTORY,
        OUTPUT_FILENAME
    )

    dataframe = pd.DataFrame(findings)

    # Enforce exact column ordering.
    required_columns = [
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

    dataframe = dataframe[required_columns]

    dataframe.to_excel(
        output_path,
        index=False,
        engine="openpyxl",
    )

    print(
        f"[INFO] Account: {account_id}"
    )

    print(
        f"[INFO] Regions scanned: {len(regions)}"
    )

    print(
        f"[INFO] Graviton candidates discovered: {len(findings)}"
    )

    print(
        f"[INFO] Output: {output_path}"
    )


if __name__ == "__main__":
    main()