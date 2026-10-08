# ============================================================
# AWS FinOps Policy
# Policy: Efs Unused Old Access Point
# Service: EFS
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
    "efs_unused_old_access_point.xlsx"
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
    "Efs Unused Old Access Point"
)

CATEGORY = (
    "Efs Unused Old Access Point"
)

SERVICE = "EFS"

# Access points older than this are considered
# candidates for review.
OLD_ACCESS_POINT_DAYS = 180


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

def fetch_all_access_points(
    efs
):

    access_points = []

    paginator = efs.get_paginator(
        "describe_access_points"
    )

    for page in paginator.paginate():

        access_points.extend(
            page.get(
                "AccessPoints",
                []
            )
        )

    return access_points


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_resource_tags(
    access_point
):

    tags = {}

    for tag in access_point.get(
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

    return tags


def calculate_age_days(
    creation_time
):

    if not creation_time:

        return None

    now = datetime.now(
        timezone.utc
    )

    # Ensure timezone-aware datetime.
    if creation_time.tzinfo is None:

        creation_time = creation_time.replace(
            tzinfo=timezone.utc
        )

    age = (
        now - creation_time
    )

    return age.total_seconds() / 86400


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_access_point(
    access_point,
    account_id,
    region
):

    access_point_id = (
        access_point.get(
            "AccessPointId"
        )
    )

    file_system_id = (
        access_point.get(
            "FileSystemId"
        )
    )

    lifecycle_state = (
        access_point.get(
            "LifeCycleState"
        )
    )

    creation_time = (
        access_point.get(
            "CreationTime"
        )
    )

    name = access_point.get(
        "Name"
    )

    tags = get_resource_tags(
        access_point
    )

    age_days = calculate_age_days(
        creation_time
    )

    # --------------------------------------------------------
    # Evaluate age.
    # --------------------------------------------------------

    if age_days is None:

        return {
            "candidate": False,
            "evaluation_status": (
                "Unable to evaluate"
            ),
            "reason": (
                "Access point creation time "
                "is unavailable."
            ),
            "recommendation": (
                "Verify the access point manually "
                "before making a deletion decision."
            ),
            "access_point": access_point,
            "access_point_id": access_point_id,
            "file_system_id": file_system_id,
            "age_days": None,
            "account_id": account_id,
            "region": region
        }

    # --------------------------------------------------------
    # Only available access points should be evaluated
    # for this cleanup recommendation.
    # --------------------------------------------------------

    if lifecycle_state != "available":

        return {
            "candidate": False,
            "evaluation_status": (
                "Not a Candidate"
            ),
            "reason": (
                f"Access point lifecycle state "
                f"is {lifecycle_state}."
            ),
            "recommendation": (
                "Do not include this access point "
                "in the old-access-point cleanup."
            ),
            "access_point": access_point,
            "access_point_id": access_point_id,
            "file_system_id": file_system_id,
            "age_days": age_days,
            "account_id": account_id,
            "region": region
        }

    # --------------------------------------------------------
    # Policy condition:
    #
    # Access point is older than configured threshold.
    #
    # IMPORTANT:
    # AWS EFS does not expose a native
    # "last accessed" timestamp for an EFS access point.
    # Therefore age is a candidate signal, not proof of use.
    # --------------------------------------------------------

    if age_days >= OLD_ACCESS_POINT_DAYS:

        candidate = True

        evaluation_status = (
            "Candidate"
        )

        reason = (
            f"Access point is "
            f"{age_days:.2f} days old, which is "
            f"older than the configured "
            f"{OLD_ACCESS_POINT_DAYS}-day threshold. "
            "AWS does not provide a native "
            "last-accessed timestamp for EFS "
            "access points, so usage should be "
            "validated before deletion."
        )

        recommendation = (
            "Verify that no workloads, ECS tasks, "
            "EKS pods, EC2 instances, Lambda "
            "functions, or other clients use this "
            "access point. If unused, delete the "
            "access point."
        )

    else:

        candidate = False

        evaluation_status = (
            "Not a Candidate"
        )

        reason = (
            f"Access point age is "
            f"{age_days:.2f} days, below the "
            f"{OLD_ACCESS_POINT_DAYS}-day threshold."
        )

        recommendation = (
            "No action required."
        )

    return {
        "candidate": candidate,
        "evaluation_status": evaluation_status,
        "reason": reason,
        "recommendation": recommendation,
        "access_point": access_point,
        "access_point_id": access_point_id,
        "file_system_id": file_system_id,
        "age_days": age_days,
        "account_id": account_id,
        "region": region,
        "name": name,
        "tags": tags
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

    access_point = evaluation[
        "access_point"
    ]

    access_point_id = evaluation[
        "access_point_id"
    ]

    file_system_id = evaluation[
        "file_system_id"
    ]

    age_days = evaluation[
        "age_days"
    ]

    name = evaluation.get(
        "name"
    )

    tags = evaluation.get(
        "tags",
        {}
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
    # Creation time
    # --------------------------------------------------------

    creation_time = (
        access_point.get(
            "CreationTime"
        )
    )

    creation_date_text = ""

    if creation_time:

        creation_date_text = (
            creation_time.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # POSIX user configuration
    # --------------------------------------------------------

    posix_user = access_point.get(
        "PosixUser",
        {}
    )

    uid = posix_user.get(
        "Uid"
    )

    gid = posix_user.get(
        "Gid"
    )

    secondary_gids = posix_user.get(
        "SecondaryGids"
    )

    # --------------------------------------------------------
    # Root directory configuration
    # --------------------------------------------------------

    root_directory = (
        access_point.get(
            "RootDirectory",
            {}
        )
    )

    path = root_directory.get(
        "Path"
    )

    creation_info = root_directory.get(
        "CreationInfo",
        {}
    )

    owner_uid = creation_info.get(
        "OwnerUid"
    )

    owner_gid = creation_info.get(
        "OwnerGid"
    )

    permissions = creation_info.get(
        "Permissions"
    )

    # --------------------------------------------------------
    # ARN
    # --------------------------------------------------------

    access_point_arn = (
        f"arn:aws:elasticfilesystem:"
        f"{region}:"
        f"{account_id}:"
        f"access-point/"
        f"{access_point_id}"
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"AccessPointId: "
        f"{access_point_id} | "
        f"AccessPointARN: "
        f"{access_point_arn} | "
        f"FileSystemId: "
        f"{file_system_id} | "
        f"Name: "
        f"{name or 'None'} | "
        f"LifeCycleState: "
        f"{access_point.get('LifeCycleState')} | "
        f"CreationDate: "
        f"{creation_date_text} | "
        f"AgeDays: "
        f"{age_days:.2f} | "
        f"RootPath: "
        f"{path or 'None'} | "
        f"POSIXUid: "
        f"{uid} | "
        f"POSIXGid: "
        f"{gid} | "
        f"SecondaryGids: "
        f"{secondary_gids} | "
        f"RootOwnerUid: "
        f"{owner_uid} | "
        f"RootOwnerGid: "
        f"{owner_gid} | "
        f"Permissions: "
        f"{permissions} | "
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
        "resourceNameOrId": access_point_arn,
        "resourceId": access_point_id,
        "resourceArn": access_point_arn,
        "service": SERVICE,
        "type": "EFS Access Point",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "EFS Access Point is old and potentially unused.",
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
        f"Old Access Point Threshold: "
        f"{OLD_ACCESS_POINT_DAYS} days"
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
    # Fetch all access points
    # --------------------------------------------------------

    print(
        "Fetching EFS access points..."
    )

    access_points = (
        fetch_all_access_points(
            efs
        )
    )

    print(
        f"Access points scanned: "
        f"{len(access_points)}"
    )

    # --------------------------------------------------------
    # Evaluate
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    ignored_count = 0

    unable_to_evaluate_count = 0

    for access_point in access_points:

        evaluation = evaluate_access_point(
            access_point,
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

            ignored_count += 1

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
        f"Account ID                 : "
        f"{account_id}"
    )

    print(
        f"Region                     : "
        f"{REGION}"
    )

    print(
        f"Access Points Scanned      : "
        f"{len(access_points)}"
    )

    print(
        f"Old Access Point Candidates: "
        f"{candidate_count}"
    )

    print(
        f"Ignored                    : "
        f"{ignored_count}"
    )

    print(
        f"Unable To Evaluate         : "
        f"{unable_to_evaluate_count}"
    )

    print(
        f"Age Threshold              : "
        f"{OLD_ACCESS_POINT_DAYS} days"
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