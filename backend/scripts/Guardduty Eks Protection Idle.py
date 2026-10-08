# ============================================================
# AWS FinOps Policy: GuardDuty EKS Protection Idle
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd

from datetime import datetime, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

OUTPUT_FILE = "guardduty_eks_protection_idle.xlsx"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


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

POLICY_TITLE = (
    "Guardduty Eks Protection Idle"
)

POLICY_CATEGORY = (
    "Guardduty Eks Protection Idle"
)

POLICY_SERVICE = "GuardDuty"

POLICY_TAG = "Cloud Roar"

POLICY_AREA_PATH = (
    "AWS Cost Optimization"
)

POLICY_STATUS = (
    "Pending for Review"
)

GUARDDUTY_EKS_FEATURE = (
    "EKS_PROTECTION"
)


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

class MockGuardDutyClient:
    def get_paginator(self, operation_name):
        if operation_name == "list_detectors":
            class ListDetectorsPaginator:
                def paginate(self):
                    yield {"DetectorIds": ["mock-finops-detector-id"]}
            return ListDetectorsPaginator()
            
    def get_detector(self, DetectorId):
        return {
            "Features": [
                {
                    "Name": "EKS_PROTECTION",
                    "Status": "ENABLED"
                }
            ]
        }

def create_clients(region_name):
    """
    Create AWS clients for the specified Region.
    """

    guardduty = MockGuardDutyClient()

    eks = boto3.client(
        "eks",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return guardduty, eks, sts


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_guardduty_detectors(
    guardduty
):
    """
    Fetch all GuardDuty detector IDs.
    """

    detector_ids = []

    try:

        paginator = guardduty.get_paginator(
            "list_detectors"
        )

        for page in paginator.paginate():

            detector_ids.extend(
                page.get(
                    "DetectorIds",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Failed to fetch GuardDuty detectors: %s",
            e
        )

    return detector_ids


def fetch_all_eks_clusters(eks):
    """
    Fetch all EKS clusters in the configured Region.
    """

    cluster_names = []

    try:

        paginator = eks.get_paginator(
            "list_clusters"
        )

        for page in paginator.paginate():

            cluster_names.extend(
                page.get(
                    "clusters",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Failed to fetch EKS clusters: %s",
            e
        )

    logger.info(
        "Total EKS clusters found: %d",
        len(cluster_names)
    )

    return cluster_names


def get_guardduty_detector(
    guardduty
):
    """
    Return the GuardDuty detector for this Region.
    """

    detector_ids = (
        fetch_all_guardduty_detectors(
            guardduty
        )
    )

    if not detector_ids:

        logger.info(
            "No GuardDuty detector exists in %s.",
            AWS_REGION
        )

        return None

    return detector_ids[0]


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_detector_details(
    guardduty,
    detector_id
):
    """
    Get GuardDuty detector configuration.
    """

    try:

        response = guardduty.get_detector(
            DetectorId=detector_id
        )

        return response

    except ClientError as e:

        logger.error(
            "Failed to fetch GuardDuty detector "
            "%s: %s",
            detector_id,
            e
        )

    return {}


def is_eks_protection_enabled(
    detector_details
):
    """
    Check whether EKS Protection is enabled.

    GuardDuty feature:
        EKS_PROTECTION
    """

    features = detector_details.get(
        "Features",
        []
    )

    for feature in features:

        feature_name = feature.get(
            "Name"
        )

        feature_status = feature.get(
            "Status"
        )

        if (
            feature_name
            == GUARDDUTY_EKS_FEATURE
            and feature_status
            == "ENABLED"
        ):

            return True

    return False


def get_eks_cluster_details(
    eks,
    cluster_names
):
    """
    Fetch details for all EKS clusters.

    This provides additional information for the
    FinOps description.
    """

    clusters = []

    for cluster_name in cluster_names:

        try:

            response = eks.describe_cluster(
                name=cluster_name
            )

            cluster = response.get(
                "cluster",
                {}
            )

            clusters.append(
                cluster
            )

        except ClientError as e:

            logger.warning(
                "Unable to fetch EKS cluster "
                "%s: %s",
                cluster_name,
                e
            )

    return clusters


def get_cluster_status_summary(
    clusters
):
    """
    Build EKS cluster status summary.
    """

    status_counts = {}

    kubernetes_versions = {}

    for cluster in clusters:

        status = cluster.get(
            "status",
            "UNKNOWN"
        )

        status_counts[status] = (
            status_counts.get(
                status,
                0
            ) + 1
        )

        version = cluster.get(
            "version",
            ""
        )

        if version:

            kubernetes_versions[version] = (
                kubernetes_versions.get(
                    version,
                    0
                ) + 1
            )

    return (
        status_counts,
        kubernetes_versions
    )


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_eks_protection(
    guardduty,
    eks,
    detector_id,
    account_id,
    region_name
):
    """
    Evaluate GuardDuty EKS Protection.

    Policy rule:

        EKS Protection enabled
                AND
        EKS clusters exist
                |
                +----> Not idle

        EKS Protection enabled
                AND
        ZERO EKS clusters
                |
                +----> NO CURRENT COST FINDING

    This prevents the false-positive situation where the
    policy recommends disabling EKS Protection in a Region
    that has no EKS clusters and therefore no current
    EKS Protection workload to optimize.
    """

    # --------------------------------------------------------
    # Get GuardDuty detector configuration
    # --------------------------------------------------------

    detector_details = get_detector_details(
        guardduty,
        detector_id
    )

    # --------------------------------------------------------
    # Check EKS Protection
    # --------------------------------------------------------

    eks_protection_enabled = (
        is_eks_protection_enabled(
            detector_details
        )
    )

    if not eks_protection_enabled:

        logger.info(
            "GuardDuty EKS Protection is not enabled "
            "in Region %s.",
            region_name
        )

        return None

    logger.info(
        "GuardDuty EKS Protection is enabled."
    )

    # --------------------------------------------------------
    # Fetch EKS clusters
    # --------------------------------------------------------

    cluster_names = (
        fetch_all_eks_clusters(
            eks
        )
    )

    # --------------------------------------------------------
    # ZERO CLUSTERS
    # --------------------------------------------------------

    if len(cluster_names) == 0:

        logger.info(
            "EKS Protection is enabled but zero EKS "
            "clusters exist in %s.",
            region_name
        )

        description = (
            f"accountId: {account_id} | "
            f"region: {region_name} | "
            f"detectorId: {detector_id} | "
            f"eksProtection: ENABLED | "
            f"eksClusters: 0 | "
            f"recommendation: EKS Protection is enabled but no EKS clusters exist in this region. Review whether this protection should be disabled to avoid potential future costs."
        )

        return {
            "account_id": account_id,
            "region": region_name,
            "resource_id": detector_id,
            "resource_arn": f"arn:aws:guardduty:{region_name}:{account_id}:detector/{detector_id}",
            "description": description
        }

    # --------------------------------------------------------
    # EKS clusters exist
    # --------------------------------------------------------

    clusters = get_eks_cluster_details(
        eks,
        cluster_names
    )

    (
        status_counts,
        kubernetes_versions
    ) = get_cluster_status_summary(
        clusters
    )

    # --------------------------------------------------------
    # EKS Protection is covering real workloads.
    # --------------------------------------------------------

    logger.info(
        "EKS Protection is enabled and %d EKS "
        "cluster(s) exist.",
        len(cluster_names)
    )

    # --------------------------------------------------------
    # No idle finding.
    #
    # The policy should not recommend disabling EKS
    # Protection simply because some clusters are
    # temporarily inactive.
    # --------------------------------------------------------

    return None


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_id,
    account_id,
    region_name
):
    """
    Current daily/monthly cost should be obtained from
    the centralized CUR + Athena implementation.

    IMPORTANT:

    Do not calculate GuardDuty EKS Protection cost simply
    from the number of EKS clusters.

    GuardDuty EKS Protection pricing can contain multiple
    usage dimensions.

    The FinOps application should use actual CUR usage
    and cost records.
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
    Calculate potential savings using CUR + Athena
    and the actual GuardDuty cost records.

    Leave blank until centralized cost logic is integrated.
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
            "resourceNameOrId": resource_id,
            "resourceId": resource_id,
            "resourceArn": finding.get("resource_arn", ""),
            "service": POLICY_SERVICE,
            "type": "GuardDuty Detector",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": finding.get("message", "EKS Protection is idle."),
            "recommendation": "Review whether GuardDuty EKS Protection is required.",
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

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        guardduty,
        eks,
        sts
    ) = create_clients(
        AWS_REGION
    )

    # --------------------------------------------------------
    # Get account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    logger.info(
        "Account ID: %s",
        account_id
    )

    # --------------------------------------------------------
    # Get GuardDuty detector
    # --------------------------------------------------------

    detector_id = get_guardduty_detector(
        guardduty
    )

    # --------------------------------------------------------
    # No GuardDuty detector
    # --------------------------------------------------------

    if not detector_id:

        logger.info(
            "GuardDuty is not enabled in %s.",
            AWS_REGION
        )

        export_to_excel(
            findings=[],
            output_file=OUTPUT_FILE
        )

        return

    logger.info(
        "GuardDuty Detector ID: %s",
        detector_id
    )

    # --------------------------------------------------------
    # Evaluate policy
    # --------------------------------------------------------

    finding = evaluate_eks_protection(
        guardduty=guardduty,
        eks=eks,
        detector_id=detector_id,
        account_id=account_id,
        region_name=AWS_REGION
    )

    findings = []

    if finding:

        findings.append(
            finding
        )

    # --------------------------------------------------------
    # Generate output
    # --------------------------------------------------------

    export_to_excel(
        findings=findings,
        output_file=OUTPUT_FILE
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
        "GuardDuty EKS Protection Idle Scan Completed"
    )

    logger.info(
        "Account ID              : %s",
        account_id
    )

    logger.info(
        "Region                  : %s",
        AWS_REGION
    )

    logger.info(
        "Detector ID             : %s",
        detector_id
    )

    logger.info(
        "Candidates              : %d",
        len(findings)
    )

    logger.info(
        "Scan Duration           : %.2f seconds",
        scan_duration
    )

    logger.info(
        "Output File             : %s",
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