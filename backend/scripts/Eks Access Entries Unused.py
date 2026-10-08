# ============================================================
# AWS FinOps Policy
# Policy : EKS Access Entries Unused
# Service: EKS
#
# Purpose:
# Identify EKS access entries whose IAM principal has had
# no STS activity during the configured lookback period.
#
# Important:
# - AWS service-linked roles are excluded.
# - AWS reserved roles are excluded.
# - EKS cluster creator/admin roles should be reviewed carefully.
# - CloudTrail LookupEvents is used for recent STS activity.
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

OUTPUT_FILE = "eks_access_entries_unused.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "Eks Access Entries Unused"

CATEGORY = "Eks Access Entries Unused"

SERVICE = "EKS"

LOOKBACK_DAYS = 60

# Access entries with no STS activity during this period
# will be considered candidates, subject to exclusions.
STS_LOOKBACK_DAYS = 60


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    eks = boto3.client(
        "eks",
        region_name=region_name,
        config=AWS_CONFIG
    )

    iam = boto3.client(
        "iam",
        region_name=region_name,
        config=AWS_CONFIG
    )

    cloudtrail = boto3.client(
        "cloudtrail",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return (
        eks,
        iam,
        cloudtrail,
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

def fetch_all_eks_clusters(eks):

    clusters = []

    paginator = eks.get_paginator(
        "list_clusters"
    )

    for page in paginator.paginate():

        clusters.extend(
            page.get(
                "clusters",
                []
            )
        )

    return clusters


def fetch_all_access_entries(
    eks,
    cluster_name
):

    access_entries = []

    paginator = eks.get_paginator(
        "list_access_entries"
    )

    try:

        for page in paginator.paginate(
            clusterName=cluster_name
        ):

            access_entries.extend(
                page.get(
                    "accessEntries",
                    []
                )
            )

    except ClientError as error:

        print(
            f"Unable to fetch access entries "
            f"for cluster {cluster_name}: "
            f"{error}"
        )

    return access_entries


def get_access_entry_details(
    eks,
    cluster_name,
    principal_arn
):

    try:

        response = eks.describe_access_entry(
            clusterName=cluster_name,
            principalArn=principal_arn
        )

        return response.get(
            "accessEntry",
            {}
        )

    except ClientError as error:

        print(
            f"Unable to describe access entry "
            f"{principal_arn}: {error}"
        )

        return {}


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def is_service_linked_role(
    principal_arn
):

    if not principal_arn:
        return False

    # AWS service-linked role pattern
    if ":role/aws-service-role/" in principal_arn:

        return True

    return False


def is_aws_reserved_role(
    principal_arn
):

    if not principal_arn:
        return False

    # AWS reserved SSO / AWSReservedSSO roles
    if ":role/aws-reserved/sso.amazonaws.com/" in principal_arn:

        return True

    if "/AWSReservedSSO_" in principal_arn:

        return True

    # Other AWS-reserved role patterns
    if ":role/aws-reserved/" in principal_arn:

        return True

    return False


def is_aws_managed_role(
    principal_arn
):

    """
    Detect roles that should not normally be treated
    as ordinary unused access entries.
    """

    return (
        is_service_linked_role(
            principal_arn
        )
        or
        is_aws_reserved_role(
            principal_arn
        )
    )


def extract_role_name(
    principal_arn
):

    if not principal_arn:

        return ""

    if ":role/" not in principal_arn:

        return ""

    role_name = principal_arn.split(
        ":role/",
        1
    )[1]

    # IAM role ARN can contain path.
    # Keep the full role path because it is useful
    # when identifying the principal.
    return role_name


def get_iam_role(
    iam,
    principal_arn
):

    role_name = extract_role_name(
        principal_arn
    )

    if not role_name:

        return {}

    try:

        response = iam.get_role(
            RoleName=role_name.split(
                "/"
            )[-1]
        )

        return response.get(
            "Role",
            {}
        )

    except ClientError:

        return {}


def check_sts_activity(
    cloudtrail,
    principal_arn
):

    """
    Search CloudTrail for STS activity performed by
    the principal during the configured lookback period.

    The lookup is intentionally limited to STS-related
    events rather than treating arbitrary CloudTrail
    activity as STS usage.
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=STS_LOOKBACK_DAYS
        )
    )

    lookup_attributes = [
        {
            "AttributeKey": "Username",
            "AttributeValue": principal_arn
        }
    ]

    events = []

    try:

        paginator = cloudtrail.get_paginator(
            "lookup_events"
        )

        for page in paginator.paginate(
            LookupAttributes=lookup_attributes,
            StartTime=start_time,
            EndTime=end_time,
            PaginationConfig={
                "PageSize": 50
            }
        ):

            events.extend(
                page.get(
                    "Events",
                    []
                )
            )

            # Avoid unnecessarily scanning huge
            # CloudTrail result sets.
            if len(events) >= 100:

                break

    except ClientError as error:

        return {
            "available": False,
            "has_activity": False,
            "event_count": 0,
            "last_event_time": None,
            "error": str(error)
        }

    sts_events = []

    for event in events:

        event_name = (
            event.get(
                "EventName",
                ""
            )
        )

        # STS events commonly associated with
        # IAM role usage.
        if event_name in {
            "AssumeRole",
            "AssumeRoleWithSAML",
            "AssumeRoleWithWebIdentity",
            "GetCallerIdentity",
            "GetFederationToken",
            "GetSessionToken"
        }:

            sts_events.append(
                event
            )

    last_event_time = None

    if sts_events:

        timestamps = [
            event.get(
                "EventTime"
            )
            for event in sts_events
            if event.get(
                "EventTime"
            )
        ]

        if timestamps:

            last_event_time = max(
                timestamps
            )

    return {
        "available": True,
        "has_activity": (
            len(sts_events) > 0
        ),
        "event_count": len(
            sts_events
        ),
        "last_event_time": (
            last_event_time
        ),
        "error": ""
    }


def get_cluster_creator_identity(
    eks,
    cluster_name
):

    """
    EKS does not expose the cluster creator directly
    through a simple cluster field.

    This function is intentionally conservative and
    returns an empty value when it cannot be determined.
    """

    return ""


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_access_entry(
    eks,
    iam,
    cloudtrail,
    cluster_name,
    principal_arn,
    account_id,
    region
):

    access_entry = (
        get_access_entry_details(
            eks,
            cluster_name,
            principal_arn
        )
    )

    access_entry_type = (
        access_entry.get(
            "type",
            ""
        )
    )

    username = (
        access_entry.get(
            "username",
            ""
        )
    )

    kubernetes_groups = (
        access_entry.get(
            "kubernetesGroups",
            []
        )
    )

    created_at = (
        access_entry.get(
            "createdAt"
        )
    )

    modified_at = (
        access_entry.get(
            "modifiedAt"
        )
    )

    # --------------------------------------------------------
    # Exclusion 1:
    # AWS service-linked roles
    # --------------------------------------------------------

    if is_service_linked_role(
        principal_arn
    ):

        return {
            "candidate": False,
            "evaluation": "Excluded",
            "reason": (
                "Principal is an AWS service-linked "
                "role and must not be treated as an "
                "unused EKS access entry."
            ),
            "sts_activity": {},
            "access_entry": access_entry
        }

    # --------------------------------------------------------
    # Exclusion 2:
    # AWS reserved roles
    # --------------------------------------------------------

    if is_aws_reserved_role(
        principal_arn
    ):

        return {
            "candidate": False,
            "evaluation": "Excluded",
            "reason": (
                "Principal is an AWS-reserved role "
                "and should not be automatically "
                "removed based only on STS inactivity."
            ),
            "sts_activity": {},
            "access_entry": access_entry
        }

    # --------------------------------------------------------
    # Exclusion 3:
    # Non STANDARD access entry types
    #
    # EKS can create access entries for AWS-managed
    # authentication integrations.
    # --------------------------------------------------------

    if access_entry_type not in {
        "",
        "STANDARD"
    }:

        return {
            "candidate": False,
            "evaluation": "Excluded",
            "reason": (
                f"Access entry type is "
                f"'{access_entry_type}'. "
                f"Only STANDARD access entries are "
                f"evaluated by this policy."
            ),
            "sts_activity": {},
            "access_entry": access_entry
        }

    # --------------------------------------------------------
    # Check IAM role.
    # --------------------------------------------------------

    role = get_iam_role(
        iam,
        principal_arn
    )

    role_created = role.get(
        "CreateDate"
    )

    role_last_used = (
        role.get(
            "RoleLastUsed",
            {}
        )
    )

    role_last_used_date = (
        role_last_used.get(
            "LastUsedDate"
        )
    )

    # --------------------------------------------------------
    # Check CloudTrail STS activity.
    # --------------------------------------------------------

    sts_activity = check_sts_activity(
        cloudtrail,
        principal_arn
    )

    # --------------------------------------------------------
    # CloudTrail unavailable:
    # Do not create a false positive.
    # --------------------------------------------------------

    if not sts_activity[
        "available"
    ]:

        return {
            "candidate": False,
            "evaluation": "Unable to Evaluate",
            "reason": (
                "CloudTrail activity could not be "
                "retrieved. Resource should not be "
                "classified as unused."
            ),
            "sts_activity": sts_activity,
            "access_entry": access_entry,
            "role": role
        }

    # --------------------------------------------------------
    # Determine activity.
    # --------------------------------------------------------

    has_sts_activity = (
        sts_activity[
            "has_activity"
        ]
    )

    # IAM RoleLastUsed can also provide useful evidence.
    has_iam_last_used = (
        role_last_used_date is not None
    )

    # --------------------------------------------------------
    # Candidate:
    #
    # No STS activity
    # AND
    # no IAM role usage information
    #
    # IMPORTANT:
    # We do not consider the access entry unused merely
    # because one CloudTrail query returns zero events.
    # --------------------------------------------------------

    if (
        not has_sts_activity
        and
        not has_iam_last_used
    ):

        candidate = True

        evaluation = "Candidate"

        reason = (
            f"EKS access entry for principal "
            f"'{principal_arn}' has no detected STS "
            f"activity during the last "
            f"{STS_LOOKBACK_DAYS} days and no IAM "
            f"RoleLastUsed activity was detected."
        )

    else:

        candidate = False

        evaluation = "Not a Candidate"

        if has_sts_activity:

            reason = (
                f"Principal '{principal_arn}' has "
                f"detected STS activity within the "
                f"last {STS_LOOKBACK_DAYS} days."
            )

        else:

            reason = (
                f"Principal '{principal_arn}' has "
                f"IAM RoleLastUsed activity and "
                f"therefore should not be automatically "
                f"classified as unused."
            )

    return {
        "candidate": candidate,
        "evaluation": evaluation,
        "reason": reason,
        "sts_activity": sts_activity,
        "access_entry": access_entry,
        "role": role,
        "username": username,
        "kubernetes_groups": kubernetes_groups,
        "access_entry_type": access_entry_type,
        "created_at": created_at,
        "modified_at": modified_at
    }


# ============================================================
# 9. Build Standard Finding
# ============================================================

def build_finding(
    evaluation,
    cluster_name,
    principal_arn,
    account_id,
    region
):

    access_entry = evaluation.get(
        "access_entry",
        {}
    )

    role = evaluation.get(
        "role",
        {}
    )

    sts_activity = evaluation.get(
        "sts_activity",
        {}
    )

    role_last_used = (
        role.get(
            "RoleLastUsed",
            {}
        )
    )

    role_last_used_date = (
        role_last_used.get(
            "LastUsedDate"
        )
    )

    created_at = (
        access_entry.get(
            "createdAt"
        )
    )

    modified_at = (
        access_entry.get(
            "modifiedAt"
        )
    )

    access_entry_type = (
        access_entry.get(
            "type",
            ""
        )
    )

    username = (
        access_entry.get(
            "username",
            ""
        )
    )

    kubernetes_groups = (
        access_entry.get(
            "kubernetesGroups",
            []
        )
    )

    role_name = extract_role_name(
        principal_arn
    )

    candidate = evaluation[
        "candidate"
    ]

    status = (
        "Pending for Review"
        if candidate
        else "Not a Candidate"
    )

    # --------------------------------------------------------
    # Resource ARN
    # --------------------------------------------------------

    resource_arn = (
        f"arn:aws:eks:"
        f"{region}:"
        f"{account_id}:"
        f"access-entry/"
        f"{cluster_name}/"
        f"{principal_arn}"
    )

    # --------------------------------------------------------
    # Tags
    # --------------------------------------------------------

    tags = {
        "Policy": POLICY_TITLE,
        "Cluster": cluster_name
    }

    # --------------------------------------------------------
    # Description
    #
    # EKS-specific fields stay inside description.
    # --------------------------------------------------------

    description = (
        f"ClusterName: {cluster_name} | "
        f"PrincipalArn: {principal_arn} | "
        f"RoleName: {role_name} | "
        f"AccessEntryType: {access_entry_type} | "
        f"Username: {username} | "
        f"KubernetesGroups: {kubernetes_groups} | "
        f"CreatedAt: {created_at} | "
        f"ModifiedAt: {modified_at} | "
        f"STSActivityLast{STS_LOOKBACK_DAYS}Days: "
        f"{sts_activity.get('has_activity', False)} | "
        f"STSActivityEventCount: "
        f"{sts_activity.get('event_count', 0)} | "
        f"LastSTSActivity: "
        f"{sts_activity.get('last_event_time')} | "
        f"IAMRoleLastUsed: "
        f"{role_last_used_date} | "
        f"Evaluation: "
        f"{evaluation['evaluation']} | "
        f"Reason: "
        f"{evaluation['reason']}"
    )

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_TITLE,
        "category": CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": status,
        "areaPath": "AWS Cost Optimization",
        "tags": str(tags),
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": principal_arn,
        "resourceId": principal_arn,
        "resourceArn": resource_arn,
        "service": SERVICE,
        "type": "EKS Access Entry",
        "policy": POLICY_TITLE,
        "effortLevel": "Low",
        "message": evaluation[
            "reason"
        ],
        "recommendation": (
            "Review the EKS access entry and confirm "
            "that the IAM principal is no longer "
            "required before removing it. Do not "
            "delete AWS-managed, service-linked, "
            "SSO/reserved, or operationally required "
            "access entries automatically."
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
# 10. Scan Region
# ============================================================

def scan_region(
    region_name
):

    (
        eks,
        iam,
        cloudtrail,
        sts
    ) = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    print()
    print(
        f"Account ID : {account_id}"
    )

    print(
        f"Region     : {region_name}"
    )

    print(
        "Fetching EKS clusters..."
    )

    clusters = fetch_all_eks_clusters(
        eks
    )

    print(
        f"EKS clusters found: "
        f"{len(clusters)}"
    )

    findings = []

    total_access_entries = 0

    candidate_count = 0

    excluded_count = 0

    unable_to_evaluate_count = 0

    for cluster_name in clusters:

        print()
        print(
            f"Processing cluster: "
            f"{cluster_name}"
        )

        access_entries = (
            fetch_all_access_entries(
                eks,
                cluster_name
            )
        )

        print(
            f"Access entries: "
            f"{len(access_entries)}"
        )

        total_access_entries += len(
            access_entries
        )

        for principal_arn in access_entries:

            evaluation = (
                evaluate_access_entry(
                    eks,
                    iam,
                    cloudtrail,
                    cluster_name,
                    principal_arn,
                    account_id,
                    region_name
                )
            )

            evaluation_status = (
                evaluation[
                    "evaluation"
                ]
            )

            # ------------------------------------------------
            # Excluded resources are not findings.
            # ------------------------------------------------

            if evaluation_status == "Excluded":

                excluded_count += 1

                continue

            # ------------------------------------------------
            # CloudTrail/IAM could not provide enough
            # evidence.
            # ------------------------------------------------

            if (
                evaluation_status ==
                "Unable to Evaluate"
            ):

                unable_to_evaluate_count += 1

                continue

            # ------------------------------------------------
            # Only output actual candidates.
            # ------------------------------------------------

            if evaluation[
                "candidate"
            ]:

                candidate_count += 1

                finding = build_finding(
                    evaluation,
                    cluster_name,
                    principal_arn,
                    account_id,
                    region_name
                )

                findings.append(
                    finding
                )

    return {
        "account_id": account_id,
        "region": region_name,
        "clusters_scanned": len(
            clusters
        ),
        "access_entries_scanned": (
            total_access_entries
        ),
        "candidate_count": (
            candidate_count
        ),
        "excluded_count": (
            excluded_count
        ),
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

    print()
    print(
        f"Excel file created: "
        f"{output_file}"
    )

    print(
        f"Findings exported: "
        f"{len(dataframe)}"
    )


# ============================================================
# 12. Main
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 80)
    print(
        "AWS FINOPS POLICY SCAN"
    )
    print("=" * 80)

    print(
        f"Policy       : {POLICY_TITLE}"
    )

    print(
        f"Service      : {SERVICE}"
    )

    print(
        f"Region       : {REGION}"
    )

    print(
        f"STS Lookback : {STS_LOOKBACK_DAYS} days"
    )

    print("=" * 80)

    result = scan_region(
        REGION
    )

    findings = result[
        "findings"
    ]

    export_to_excel(
        findings,
        OUTPUT_FILE
    )

    scan_end_time = datetime.now(
        timezone.utc
    )

    scan_duration = (
        scan_end_time -
        scan_start_time
    ).total_seconds()

    print()
    print("=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)

    print(
        f"Account ID                : "
        f"{result['account_id']}"
    )

    print(
        f"Region                    : "
        f"{result['region']}"
    )

    print(
        f"EKS Clusters Scanned      : "
        f"{result['clusters_scanned']}"
    )

    print(
        f"Access Entries Scanned    : "
        f"{result['access_entries_scanned']}"
    )

    print(
        f"Unused Candidates         : "
        f"{result['candidate_count']}"
    )

    print(
        f"Excluded Entries          : "
        f"{result['excluded_count']}"
    )

    print(
        f"Unable To Evaluate        : "
        f"{result['unable_to_evaluate_count']}"
    )

    print(
        f"Scan Duration             : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Output File               : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":

    main()