# ============================================================
# AWS FinOps Policy
# Policy: Efs Lifecycle Policy Missing
# Service: EFS
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "efs_lifecycle_policy_missing.xlsx"
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
    "Efs Lifecycle Policy Missing"
)

CATEGORY = (
    "Efs Lifecycle Policy Missing"
)

SERVICE = "EFS"

# Recommended EFS lifecycle transition.
TARGET_TRANSITION_DAYS = 30

TARGET_TRANSITION = (
    f"AFTER_{TARGET_TRANSITION_DAYS}_DAYS"
)


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    efs = boto3.client(
        "efs",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return (
        efs,
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

def fetch_all_efs_file_systems(
    efs
):

    file_systems = []

    paginator = efs.get_paginator(
        "describe_file_systems"
    )

    for page in paginator.paginate():

        file_systems.extend(
            page.get(
                "FileSystems",
                []
            )
        )

    return file_systems


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_resource_tags(
    efs,
    file_system_id
):

    tags = []

    try:

        paginator = efs.get_paginator(
            "describe_tags"
        )

        for page in paginator.paginate(
            FileSystemId=file_system_id
        ):

            tags.extend(
                page.get(
                    "Tags",
                    []
                )
            )

    except ClientError:

        return {}

    tag_map = {}

    for tag in tags:

        key = tag.get(
            "Key"
        )

        value = tag.get(
            "Value"
        )

        if key:

            tag_map[key] = value

    return tag_map


def get_lifecycle_configuration(
    efs,
    file_system_id
):

    try:

        response = (
            efs.describe_lifecycle_configuration(
                FileSystemId=file_system_id
            )
        )

        lifecycle_policies = (
            response.get(
                "LifecyclePolicies",
                []
            )
        )

        return {
            "exists": bool(
                lifecycle_policies
            ),
            "policies": lifecycle_policies,
            "error": None
        }

    except ClientError as error:

        error_code = (
            error.response
            .get(
                "Error",
                {}
            )
            .get(
                "Code"
            )
        )

        # EFS returns ResourceNotFoundException
        # when no lifecycle configuration exists.
        if error_code == (
            "PolicyNotFound"
        ):

            return {
                "exists": False,
                "policies": [],
                "error": None
            }

        if error_code == (
            "ResourceNotFoundException"
        ):

            return {
                "exists": False,
                "policies": [],
                "error": None
            }

        return {
            "exists": None,
            "policies": [],
            "error": str(error)
        }


def get_file_system_name(
    file_system,
    tags
):

    # EFS name is normally represented
    # through the Name tag.

    if tags.get("Name"):

        return tags[
            "Name"
        ]

    # Some EFS resources may have a
    # Name field in the returned object.

    if file_system.get("Name"):

        return file_system[
            "Name"
        ]

    return ""


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_file_system(
    efs,
    file_system,
    account_id,
    region
):

    file_system_id = (
        file_system.get(
            "FileSystemId"
        )
    )

    name_from_resource = (
        file_system.get(
            "Name"
        )
    )

    lifecycle = (
        get_lifecycle_configuration(
            efs,
            file_system_id
        )
    )

    tags = get_resource_tags(
        efs,
        file_system_id
    )

    file_system_name = (
        get_file_system_name(
            file_system,
            tags
        )
    )

    if not file_system_name:

        file_system_name = (
            name_from_resource
            or file_system_id
        )

    # --------------------------------------------------------
    # Unable to determine lifecycle configuration.
    # --------------------------------------------------------

    if lifecycle["exists"] is None:

        return {
            "candidate": False,
            "evaluation_status": (
                "Unable to evaluate"
            ),
            "reason": (
                "Unable to retrieve EFS "
                "LifecycleConfiguration."
            ),
            "recommendation": (
                "Do not classify this file system "
                "until lifecycle configuration "
                "can be retrieved."
            ),
            "file_system": file_system,
            "file_system_id": file_system_id,
            "file_system_name": file_system_name,
            "lifecycle": lifecycle,
            "tags": tags,
            "account_id": account_id,
            "region": region
        }

    # --------------------------------------------------------
    # Policy condition:
    #
    # Lifecycle configuration does not exist.
    # --------------------------------------------------------

    if not lifecycle["exists"]:

        candidate = True

        evaluation_status = (
            "Candidate"
        )

        reason = (
            "EFS file system does not have "
            "a LifecycleConfiguration."
        )

        recommendation = (
            "Configure an EFS lifecycle policy "
            f"with TransitionTo="
            f"{TARGET_TRANSITION} to transition "
            "eligible files from Standard storage "
            "to Infrequent Access (IA), subject to "
            "application access requirements."
        )

    else:

        candidate = False

        evaluation_status = (
            "Not a Candidate"
        )

        reason = (
            "EFS file system already has "
            "a LifecycleConfiguration."
        )

        recommendation = (
            "No action required for the "
            "missing lifecycle policy finding."
        )

    return {
        "candidate": candidate,
        "evaluation_status": evaluation_status,
        "reason": reason,
        "recommendation": recommendation,
        "file_system": file_system,
        "file_system_id": file_system_id,
        "file_system_name": file_system_name,
        "lifecycle": lifecycle,
        "tags": tags,
        "account_id": account_id,
        "region": region
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

    file_system = evaluation[
        "file_system"
    ]

    file_system_id = evaluation[
        "file_system_id"
    ]

    file_system_name = evaluation[
        "file_system_name"
    ]

    lifecycle = evaluation[
        "lifecycle"
    ]

    tags = evaluation[
        "tags"
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
    # File system properties
    # --------------------------------------------------------

    creation_time = file_system.get(
        "CreationTime"
    )

    creation_date_text = ""

    if creation_time:

        creation_date_text = (
            creation_time.strftime(
                "%d-%m-%Y"
            )
        )

    number_of_mount_targets = (
        file_system.get(
            "NumberOfMountTargets"
        )
    )

    performance_mode = (
        file_system.get(
            "PerformanceMode"
        )
    )

    throughput_mode = (
        file_system.get(
            "ThroughputMode"
        )
    )

    encrypted = file_system.get(
        "Encrypted"
    )

    kms_key_id = file_system.get(
        "KmsKeyId"
    )

    size_in_bytes = (
        file_system
        .get(
            "SizeInBytes",
            {}
        )
    )

    latest_size_bytes = (
        size_in_bytes.get(
            "Value"
        )
    )

    size_value_gb = None

    if latest_size_bytes is not None:

        size_value_gb = (
            latest_size_bytes /
            (1024 ** 3)
        )

    # --------------------------------------------------------
    # Lifecycle policies
    # --------------------------------------------------------

    lifecycle_policies = (
        lifecycle.get(
            "policies",
            []
        )
    )

    # --------------------------------------------------------
    # ARN
    # --------------------------------------------------------

    file_system_arn = (
        f"arn:aws:elasticfilesystem:"
        f"{region}:"
        f"{account_id}:"
        f"file-system/"
        f"{file_system_id}"
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"FileSystemName: "
        f"{file_system_name} | "
        f"FileSystemId: "
        f"{file_system_id} | "
        f"CreationDate: "
        f"{creation_date_text} | "
        f"SizeGB: "
        f"{size_value_gb} | "
        f"PerformanceMode: "
        f"{performance_mode} | "
        f"ThroughputMode: "
        f"{throughput_mode} | "
        f"Encrypted: "
        f"{'Yes' if encrypted else 'No'} | "
        f"KmsKeyId: "
        f"{kms_key_id or 'None'} | "
        f"MountTargets: "
        f"{number_of_mount_targets} | "
        f"LifecycleConfiguration: "
        f"{'Present' if lifecycle['exists'] else 'Missing'} | "
        f"LifecyclePolicies: "
        f"{lifecycle_policies} | "
        f"RecommendedTransition: "
        f"{TARGET_TRANSITION} | "
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
        "resourceNameOrId": file_system_arn,
        "resourceId": file_system_id,
        "resourceArn": file_system_arn,
        "service": SERVICE,
        "type": "EFS File System",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "EFS file system is missing a lifecycle policy.",
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

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        efs,
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
    # Fetch EFS file systems
    # --------------------------------------------------------

    print(
        "Fetching EFS file systems..."
    )

    file_systems = (
        fetch_all_efs_file_systems(
            efs
        )
    )

    print(
        f"EFS file systems scanned: "
        f"{len(file_systems)}"
    )

    # --------------------------------------------------------
    # Evaluate
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    lifecycle_present_count = 0

    unable_to_evaluate_count = 0

    for file_system in file_systems:

        evaluation = evaluate_file_system(
            efs,
            file_system,
            account_id,
            REGION
        )

        if evaluation[
            "evaluation_status"
        ] == "Unable to evaluate":

            unable_to_evaluate_count += 1

            continue

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

        else:

            lifecycle_present_count += 1

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
        f"Account ID                  : "
        f"{account_id}"
    )

    print(
        f"Region                      : "
        f"{REGION}"
    )

    print(
        f"EFS File Systems Scanned    : "
        f"{len(file_systems)}"
    )

    print(
        f"Missing Lifecycle Policy    : "
        f"{candidate_count}"
    )

    print(
        f"Lifecycle Policy Present    : "
        f"{lifecycle_present_count}"
    )

    print(
        f"Unable To Evaluate          : "
        f"{unable_to_evaluate_count}"
    )

    print(
        f"Recommended Transition      : "
        f"{TARGET_TRANSITION}"
    )

    print(
        f"Scan Duration               : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output                : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()