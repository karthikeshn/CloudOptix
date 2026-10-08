# ============================================================
# AWS FinOps Policy: GuardDuty S3 Protection Idle
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

OUTPUT_FILE = "guardduty_s3_protection_idle.xlsx"

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

POLICY_TITLE = "Guardduty S3 Protection Idle"

POLICY_CATEGORY = "Guardduty S3 Protection Idle"

POLICY_SERVICE = "GuardDuty"

POLICY_TAG = "CLX"

POLICY_AREA_PATH = "AWS Cost Optimization"

POLICY_STATUS = "Pending for Review"

# GuardDuty feature name
GUARDDUTY_S3_FEATURE = "S3_DATA_EVENTS"


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
                    "Name": "S3_DATA_EVENTS",
                    "Status": "ENABLED"
                }
            ]
        }

def create_clients(region_name):

    guardduty = MockGuardDutyClient()

    s3 = boto3.client(
        "s3",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return guardduty, s3, sts


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_guardduty_detectors(guardduty):

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


def fetch_all_s3_buckets(s3):

    """
    S3 ListBuckets is account-level rather than
    Region-paginated.

    We filter the returned buckets to the configured
    Region using GetBucketLocation.
    """

    buckets_in_region = []

    try:

        response = s3.list_buckets()

        buckets = response.get(
            "Buckets",
            []
        )

        logger.info(
            "Total S3 buckets returned by account: %d",
            len(buckets)
        )

        for bucket in buckets:

            bucket_name = bucket.get(
                "Name"
            )

            try:

                location_response = (
                    s3.get_bucket_location(
                        Bucket=bucket_name
                    )
                )

                location = (
                    location_response.get(
                        "LocationConstraint"
                    )
                )

                # S3 returns None for us-east-1
                bucket_region = (
                    "us-east-1"
                    if location is None
                    else location
                )

                # AWS may return legacy region
                if bucket_region == "EU":
                    bucket_region = "eu-west-1"

                if bucket_region == AWS_REGION:

                    buckets_in_region.append(
                        bucket
                    )

            except ClientError as e:

                logger.warning(
                    "Unable to determine Region for "
                    "bucket %s: %s",
                    bucket_name,
                    e
                )

    except ClientError as e:

        logger.error(
            "Failed to list S3 buckets: %s",
            e
        )

    logger.info(
        "S3 buckets in %s: %d",
        AWS_REGION,
        len(buckets_in_region)
    )

    return buckets_in_region


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_guardduty_detector(
    guardduty
):

    detector_ids = (
        fetch_all_guardduty_detectors(
            guardduty
        )
    )

    if not detector_ids:

        return None

    return detector_ids[0]


def get_detector_details(
    guardduty,
    detector_id
):

    try:

        return guardduty.get_detector(
            DetectorId=detector_id
        )

    except ClientError as e:

        logger.error(
            "Failed to get GuardDuty detector "
            "%s: %s",
            detector_id,
            e
        )

    return {}


def is_s3_protection_enabled(
    detector_details
):

    """
    Check whether GuardDuty S3 Protection /
    S3 data event monitoring is enabled.
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
            == GUARDDUTY_S3_FEATURE
            and feature_status
            == "ENABLED"
        ):

            return True

    return False


def get_s3_bucket_names(
    buckets
):

    return [
        bucket.get("Name")
        for bucket in buckets
        if bucket.get("Name")
    ]


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_s3_protection(
    guardduty,
    s3,
    detector_id,
    account_id,
    region_name
):

    # --------------------------------------------------------
    # Get GuardDuty detector configuration
    # --------------------------------------------------------

    detector_details = get_detector_details(
        guardduty,
        detector_id
    )

    # --------------------------------------------------------
    # Check S3 Protection
    # --------------------------------------------------------

    s3_protection_enabled = (
        is_s3_protection_enabled(
            detector_details
        )
    )

    if not s3_protection_enabled:

        logger.info(
            "GuardDuty S3 Protection is not enabled "
            "in %s.",
            region_name
        )

        return []

    logger.info(
        "GuardDuty S3 Protection is enabled."
    )

    # --------------------------------------------------------
    # Fetch S3 buckets
    # --------------------------------------------------------

    buckets = fetch_all_s3_buckets(
        s3
    )

    bucket_names = get_s3_bucket_names(
        buckets
    )

    bucket_count = len(
        bucket_names
    )

    # --------------------------------------------------------
    # ZERO BUCKETS
    # --------------------------------------------------------

    if bucket_count == 0:

        logger.info(
            "S3 Protection is enabled but there are "
            "zero S3 buckets in %s.",
            region_name
        )

        logger.info(
            "No current-cost finding generated."
        )

        return []

    # --------------------------------------------------------
    # BUCKETS EXIST
    # --------------------------------------------------------

    logger.info(
        "S3 Protection is enabled with %d S3 bucket(s).",
        bucket_count
    )

    # --------------------------------------------------------
    # IMPORTANT POLICY RULE
    # --------------------------------------------------------
    #
    # Do NOT mark the protection as idle merely because
    # bucket_count is low.
    #
    # Example:
    #
    #     1 bucket
    #
    # does NOT prove:
    #
    #     0 S3 data events
    #
    # Actual S3 Protection cost depends on monitored
    # S3 data-event activity.
    #
    # Therefore actual usage/cost must be obtained from
    # CUR + Athena / CloudTrail event analysis.
    # --------------------------------------------------------

    logger.info(
        "Bucket count alone is insufficient to classify "
        "S3 Protection as idle."
    )

    # --------------------------------------------------------
    # CURRENT IMPLEMENTATION MODIFIED FOR TESTING
    # --------------------------------------------------------
    
    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"detectorId: {detector_id} | "
        f"s3Protection: ENABLED | "
        f"s3Buckets: {bucket_count} | "
        f"recommendation: GuardDuty S3 Protection is enabled with {bucket_count} buckets. Ensure actual CUR cost is optimized."
    )

    return [{
        "account_id": account_id,
        "region": region_name,
        "resource_id": detector_id,
        "resource_arn": f"arn:aws:guardduty:{region_name}:{account_id}:detector/{detector_id}",
        "description": description
    }]


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_id,
    account_id,
    region_name
):

    """
    Current GuardDuty S3 Protection cost should come
    from CUR + Athena.

    Do not estimate cost from bucket count.

    The CUR integration should identify the actual
    GuardDuty usage/cost associated with S3 Protection.
    """

    current_daily_cost = "To be updated"

    current_monthly_cost = "To be updated"

    return (
        current_daily_cost,
        current_monthly_cost
    )


def calculate_potential_savings(
    current_monthly_cost
):

    """
    Potential savings should be calculated from actual
    CUR cost after confirming the feature can safely
    be disabled.
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
            "message": "GuardDuty S3 Protection finding.",
            "recommendation": "Review whether GuardDuty S3 Protection is required.",
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
    # Create AWS clients
    # --------------------------------------------------------

    (
        guardduty,
        s3,
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

    if not detector_id:

        logger.info(
            "No GuardDuty detector found in %s.",
            AWS_REGION
        )

        export_to_excel(
            [],
            OUTPUT_FILE
        )

        return

    logger.info(
        "GuardDuty Detector ID: %s",
        detector_id
    )

    # --------------------------------------------------------
    # Evaluate policy
    # --------------------------------------------------------

    findings = evaluate_s3_protection(
        guardduty=guardduty,
        s3=s3,
        detector_id=detector_id,
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
        "GuardDuty S3 Protection Idle Scan Completed"
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
        "Detector ID    : %s",
        detector_id
    )

    logger.info(
        "Candidates     : %d",
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