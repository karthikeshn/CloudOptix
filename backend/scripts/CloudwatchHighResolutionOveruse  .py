from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# 1. IMPORTS
# ============================================================


# ============================================================
# 2. AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "Cloudwatch High Resolution Overuse"

CATEGORY = "Cloudwatch High Resolution Overuse"

SERVICE_NAME = "CloudWatch"

EFFORT_LEVEL = "Medium"

# CloudWatch is regional.
# Change this when scanning another AWS region.
DEFAULT_REGION = "eu-west-1"


# ------------------------------------------------------------
# High-resolution detection
# ------------------------------------------------------------

# Number of high-resolution custom metrics required before
# creating a FinOps finding.
#
# Example:
# 138 high-resolution metrics > 100
# -> candidate
#
# This is configurable and should be adjusted according to
# your organization's policy.
HIGH_RESOLUTION_METRIC_THRESHOLD = 100


# Number of days to inspect for recent metric activity.
LOOKBACK_DAYS = 1


# CloudWatch high-resolution metrics support periods below
# 60 seconds. We use a 1-second period to probe for actual
# high-resolution datapoints.
HIGH_RESOLUTION_PERIOD_SECONDS = 1


# Number of minutes of recent activity to inspect.
#
# Keeping this relatively small avoids unnecessarily large
# CloudWatch API calls.
METRIC_ACTIVITY_LOOKBACK_MINUTES = 15


# ------------------------------------------------------------
# Custom metric identification
# ------------------------------------------------------------

# AWS service namespaces normally begin with "AWS/".
#
# Custom namespaces such as:
#
#   CWAgent
#   Custom/Application
#   MyCompany/Application
#
# do not.
#
# This policy therefore considers non-AWS namespaces as
# custom metrics.
EXCLUDED_AWS_NAMESPACE_PREFIX = "AWS/"


# ============================================================
# 4. STANDARD EXCEL COLUMNS
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
# 5. AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):
    """
    Create CloudWatch and STS clients.
    """

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return cloudwatch, sts


def get_account_id(sts) -> str:
    """
    Return the AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. FETCH ALL CLOUDWATCH METRICS
# ============================================================

def fetch_all_metrics(
    cloudwatch,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudWatch metrics available to the account
    in the selected region.

    Uses the CloudWatch ListMetrics paginator so that the
    scanner does not stop at the first page.
    """

    metrics: List[
        Dict[str, Any]
    ] = []

    paginator = cloudwatch.get_paginator(
        "list_metrics"
    )

    for page in paginator.paginate():

        page_metrics = page.get(
            "Metrics",
            [],
        )

        metrics.extend(
            page_metrics
        )

    return metrics


# ============================================================
# 7. CUSTOM METRIC FILTER
# ============================================================

def is_custom_metric(
    metric: Dict[str, Any],
) -> bool:
    """
    Determine whether a CloudWatch metric belongs to a
    custom namespace.

    AWS service namespaces generally use the AWS/ prefix.

    Examples:

        AWS/EC2
        AWS/Lambda
        AWS/RDS

    are AWS service metrics.

    Examples:

        CWAgent
        Custom/Application
        MyCompany/Platform

    are treated as custom namespaces.
    """

    namespace = metric.get(
        "Namespace",
        "",
    )

    if not namespace:
        return False

    return not namespace.startswith(
        EXCLUDED_AWS_NAMESPACE_PREFIX
    )


# ============================================================
# 8. BUILD METRIC DIMENSIONS
# ============================================================

def build_metric_dimensions(
    metric: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Convert the ListMetrics dimension structure into the
    structure required by GetMetricStatistics.
    """

    dimensions: List[
        Dict[str, str]
    ] = []

    for dimension in metric.get(
        "Dimensions",
        [],
    ):

        name = dimension.get(
            "Name"
        )

        value = dimension.get(
            "Value"
        )

        if not name or value is None:
            continue

        dimensions.append(
            {
                "Name": name,
                "Value": value,
            }
        )

    return dimensions


# ============================================================
# 9. HIGH-RESOLUTION METRIC DETECTION
# ============================================================

def has_high_resolution_datapoints(
    cloudwatch,
    metric: Dict[str, Any],
) -> bool:
    """
    Determine whether a custom metric is publishing
    high-resolution datapoints.

    CloudWatch high-resolution custom metrics can be queried
    using periods below 60 seconds.

    This function requests 1-second statistics over a recent
    activity window.

    If CloudWatch returns datapoints for the 1-second period,
    the metric is treated as high-resolution.

    IMPORTANT:
    A metric that has not emitted data during the lookback
    period may not be detected even if it was configured as
    high-resolution.
    """

    namespace = metric.get(
        "Namespace"
    )

    metric_name = metric.get(
        "MetricName"
    )

    if not namespace or not metric_name:
        return False

    dimensions = build_metric_dimensions(
        metric
    )

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            minutes=METRIC_ACTIVITY_LOOKBACK_MINUTES
        )
    )

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=HIGH_RESOLUTION_PERIOD_SECONDS,
            Statistics=[
                "SampleCount"
            ],
        )

        datapoints = response.get(
            "Datapoints",
            [],
        )

        return len(
            datapoints
        ) > 0

    except ClientError as exc:

        error_code = exc.response.get(
            "Error",
            {},
        ).get(
            "Code"
        )

        # InvalidParameterValue can occur when the requested
        # period is not supported by the metric.
        if error_code in {
            "InvalidParameterValue",
            "InvalidParameterCombination",
        }:

            return False

        print(
            f"[WARN] Unable to test high-resolution metric "
            f"{namespace}/{metric_name}: {exc}"
        )

        return False

    except Exception as exc:

        print(
            f"[WARN] Unexpected error testing metric "
            f"{namespace}/{metric_name}: {exc}"
        )

        return False


# ============================================================
# 10. GROUP METRICS BY NAMESPACE
# ============================================================

def group_custom_metrics_by_namespace(
    metrics: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group custom metrics by namespace.
    """

    grouped: Dict[
        str,
        List[Dict[str, Any]],
    ] = {}

    for metric in metrics:

        if not is_custom_metric(
            metric
        ):
            continue

        namespace = metric.get(
            "Namespace"
        )

        if not namespace:
            continue

        if namespace not in grouped:

            grouped[namespace] = []

        grouped[
            namespace
        ].append(
            metric
        )

    return grouped


# ============================================================
# 11. SCAN HIGH-RESOLUTION CUSTOM METRICS
# ============================================================

def scan_high_resolution_metrics(
    cloudwatch,
    metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Inspect custom metrics and identify metrics that are
    actively publishing high-resolution datapoints.

    Returns both aggregate counts and the individual metrics.
    """

    custom_metrics: List[
        Dict[str, Any]
    ] = []

    high_resolution_metrics: List[
        Dict[str, Any]
    ] = []

    for metric in metrics:

        if not is_custom_metric(
            metric
        ):
            continue

        custom_metrics.append(
            metric
        )

    print(
        f"[INFO] Custom metrics found: "
        f"{len(custom_metrics)}"
    )

    for index, metric in enumerate(
        custom_metrics,
        start=1,
    ):

        namespace = metric.get(
            "Namespace",
            "",
        )

        metric_name = metric.get(
            "MetricName",
            "",
        )

        print(
            f"[INFO] Checking metric "
            f"{index}/{len(custom_metrics)}: "
            f"{namespace}/{metric_name}"
        )

        try:

            if has_high_resolution_datapoints(
                cloudwatch=cloudwatch,
                metric=metric,
            ):

                high_resolution_metrics.append(
                    metric
                )

        except ClientError as exc:

            print(
                f"[ERROR] Failed checking "
                f"{namespace}/{metric_name}: "
                f"{exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error checking "
                f"{namespace}/{metric_name}: "
                f"{exc}"
            )

            continue

    namespace_counts: Dict[
        str,
        int,
    ] = {}

    for metric in high_resolution_metrics:

        namespace = metric.get(
            "Namespace",
            "Unknown",
        )

        namespace_counts[
            namespace
        ] = (
            namespace_counts.get(
                namespace,
                0,
            )
            + 1
        )

    return {
        "totalCustomMetrics": len(
            custom_metrics
        ),
        "totalHighResolutionMetrics": len(
            high_resolution_metrics
        ),
        "highResolutionMetrics": (
            high_resolution_metrics
        ),
        "highResolutionMetricsByNamespace": (
            namespace_counts
        ),
    }


# ============================================================
# 12. BUSINESS LOGIC
# ============================================================

def is_candidate(
    total_high_resolution_metrics: int,
) -> bool:
    """
    Determine whether the environment is a candidate for the
    CloudWatch High Resolution Overuse policy.

    Candidate condition:

        High-resolution custom metric count
        >= configured threshold
    """

    return (
        total_high_resolution_metrics
        >= HIGH_RESOLUTION_METRIC_THRESHOLD
    )


# ============================================================
# 13. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    total_high_resolution_metrics: int,
) -> str:
    """
    Build the human-readable remediation recommendation.
    """

    return (
        f"Review the {total_high_resolution_metrics} "
        f"confirmed high-resolution custom metrics. "
        f"Where 1-second or sub-minute resolution is not "
        f"required, change the metric publishing interval "
        f"to 60 seconds or use standard-resolution metrics. "
        f"Review CloudWatch Agent configuration and custom "
        f"metric publishers before making the change."
    )


# ============================================================
# 14. BUILD MESSAGE
# ============================================================

def build_message(
    total_custom_metrics: int,
    total_high_resolution_metrics: int,
) -> str:
    """
    Build the explanation for the finding.
    """

    return (
        f"Detected {total_high_resolution_metrics} "
        f"high-resolution custom metrics out of "
        f"{total_custom_metrics} custom metrics in the "
        f"region. High-resolution metrics can incur higher "
        f"CloudWatch custom metric charges when sub-minute "
        f"resolution is used."
    )


# ============================================================
# 15. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    total_custom_metrics: int,
    total_high_resolution_metrics: int,
    high_resolution_metrics: List[
        Dict[str, Any]
    ],
    high_resolution_metrics_by_namespace: Dict[
        str,
        int,
    ],
) -> Dict[str, Any]:
    """
    Build the standardized FinOps finding.

    Policy-specific information is stored as additional keys
    and will later be bundled into the description column.
    """

    metric_names: List[
        str
    ] = []

    for metric in high_resolution_metrics:

        namespace = metric.get(
            "Namespace",
            "",
        )

        metric_name = metric.get(
            "MetricName",
            "",
        )

        dimensions = metric.get(
            "Dimensions",
            [],
        )

        dimension_text = ""

        if dimensions:

            dimension_parts = []

            for dimension in dimensions:

                name = dimension.get(
                    "Name"
                )

                value = dimension.get(
                    "Value"
                )

                if name and value is not None:

                    dimension_parts.append(
                        f"{name}={value}"
                    )

            if dimension_parts:

                dimension_text = (
                    " ["
                    + ", ".join(
                        dimension_parts
                    )
                    + "]"
                )

        metric_names.append(
            f"{namespace}/{metric_name}"
            f"{dimension_text}"
        )

    return {
        # ----------------------------------------------------
        # Standard workflow fields
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": None,

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": "DevOps",

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS information
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": (
            "CWAgent-HighRes"
        ),

        "resourceId": (
            "CloudWatch-CustomMetrics"
        ),

        "resourceArn": None,

        # ----------------------------------------------------
        # Service information
        # ----------------------------------------------------

        "service": SERVICE_NAME,

        "type": "Optimization Description",

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        # ----------------------------------------------------
        # Finding
        # ----------------------------------------------------

        "message": build_message(
            total_custom_metrics=(
                total_custom_metrics
            ),
            total_high_resolution_metrics=(
                total_high_resolution_metrics
            ),
        ),

        "recommendation": build_recommendation(
            total_high_resolution_metrics=(
                total_high_resolution_metrics
            ),
        ),

        # ----------------------------------------------------
        # Cost
        #
        # CUR/Athena intentionally not used.
        # ----------------------------------------------------

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        # ----------------------------------------------------
        # Workflow
        # ----------------------------------------------------

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",

        # ----------------------------------------------------
        # Service-specific attributes
        # These will be moved into description.
        # ----------------------------------------------------

        "totalCustomMetrics": (
            total_custom_metrics
        ),

        "totalHighResolutionMetrics": (
            total_high_resolution_metrics
        ),

        "highResolutionThreshold": (
            HIGH_RESOLUTION_METRIC_THRESHOLD
        ),

        "lookbackMinutes": (
            METRIC_ACTIVITY_LOOKBACK_MINUTES
        ),

        "highResolutionPeriodSeconds": (
            HIGH_RESOLUTION_PERIOD_SECONDS
        ),

        "highResolutionMetricsByNamespace": (
            high_resolution_metrics_by_namespace
        ),

        "highResolutionMetricNames": (
            metric_names
        ),
    }


# ============================================================
# 16. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the 30 standard columns.

    All policy-specific attributes are dynamically bundled
    into the description column.
    """

    flat_findings: List[
        Dict[str, Any]
    ] = []

    for finding in findings:

        standard_data: Dict[
            str,
            Any,
        ] = {}

        extra_attributes: List[
            str
        ] = []

        for key, value in finding.items():

            if key in STANDARD_COLUMNS:

                standard_data[key] = value

            else:

                if value is None:
                    continue

                if isinstance(
                    value,
                    (dict, list),
                ):

                    value_string = json.dumps(
                        value,
                        default=str,
                    )

                else:

                    value_string = str(
                        value
                    )

                extra_attributes.append(
                    f"{key}: {value_string}"
                )

        existing_description = (
            standard_data.get(
                "description",
                "",
            )
        )

        if extra_attributes:

            extra_description = (
                " | ".join(
                    extra_attributes
                )
            )

            if existing_description:

                standard_data[
                    "description"
                ] = (
                    f"{existing_description} | "
                    f"{extra_description}"
                )

            else:

                standard_data[
                    "description"
                ] = extra_description

        else:

            standard_data[
                "description"
            ] = existing_description

        flat_findings.append(
            standard_data
        )

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS,
    )

    df.to_excel(
        filename,
        index=False,
    )

    print(
        f"[INFO] Excel report generated: "
        f"{filename}"
    )


# ============================================================
# 17. MAIN SCANNER
# ============================================================

def scan_service(
    region_name: str = DEFAULT_REGION,
) -> Dict[str, Any]:
    """
    Main CloudWatch High Resolution Overuse scanner.
    """

    cloudwatch, sts = create_clients(
        region_name=region_name,
    )

    account_id = get_account_id(
        sts
    )

    print(
        f"[INFO] Scanning CloudWatch in "
        f"{region_name}..."
    )

    # --------------------------------------------------------
    # Fetch all metrics
    # --------------------------------------------------------

    metrics = fetch_all_metrics(
        cloudwatch
    )

    print(
        f"[INFO] Total CloudWatch metrics found: "
        f"{len(metrics)}"
    )

    # --------------------------------------------------------
    # Scan custom metrics
    # --------------------------------------------------------

    scan_result = (
        scan_high_resolution_metrics(
            cloudwatch=cloudwatch,
            metrics=metrics,
        )
    )

    total_custom_metrics = (
        scan_result[
            "totalCustomMetrics"
        ]
    )

    total_high_resolution_metrics = (
        scan_result[
            "totalHighResolutionMetrics"
        ]
    )

    high_resolution_metrics = (
        scan_result[
            "highResolutionMetrics"
        ]
    )

    high_resolution_metrics_by_namespace = (
        scan_result[
            "highResolutionMetricsByNamespace"
        ]
    )

    findings: List[
        Dict[str, Any]
    ] = []

    candidates = 0

    # --------------------------------------------------------
    # Candidate evaluation
    # --------------------------------------------------------

    try:

        if is_candidate(
            total_high_resolution_metrics=(
                total_high_resolution_metrics
            ),
        ):

            finding = build_finding(
                account_id=account_id,
                region_name=region_name,
                total_custom_metrics=(
                    total_custom_metrics
                ),
                total_high_resolution_metrics=(
                    total_high_resolution_metrics
                ),
                high_resolution_metrics=(
                    high_resolution_metrics
                ),
                high_resolution_metrics_by_namespace=(
                    high_resolution_metrics_by_namespace
                ),
            )

            findings.append(
                finding
            )

            candidates = 1

            print(
                f"[FINDING] CloudWatch High Resolution "
                f"Overuse detected: "
                f"{total_high_resolution_metrics} "
                f"high-resolution custom metrics."
            )

        else:

            print(
                f"[INFO] No candidate found. "
                f"High-resolution custom metrics: "
                f"{total_high_resolution_metrics}; "
                f"threshold: "
                f"{HIGH_RESOLUTION_METRIC_THRESHOLD}"
            )

    except ClientError as exc:

        print(
            f"[ERROR] Candidate evaluation failed: "
            f"{exc}"
        )

    except Exception as exc:

        print(
            f"[ERROR] Unexpected candidate evaluation "
            f"error: {exc}"
        )

    return {
        "accountId": account_id,

        "region": region_name,

        "service": SERVICE_NAME,

        "policy": POLICY_NAME,

        "totalMetricsScanned": len(
            metrics
        ),

        "totalCustomMetrics": (
            total_custom_metrics
        ),

        "totalHighResolutionMetrics": (
            total_high_resolution_metrics
        ),

        "highResolutionThreshold": (
            HIGH_RESOLUTION_METRIC_THRESHOLD
        ),

        "totalCandidates": candidates,

        "highResolutionMetricsByNamespace": (
            high_resolution_metrics_by_namespace
        ),

        "findings": findings,
    }


# ============================================================
# 18. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    region = DEFAULT_REGION

    result = scan_service(
        region_name=region,
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    export_to_excel(
        findings=result.get(
            "findings",
            [],
        ),
        filename=(
            "cloudwatch_high_resolution_overuse.xlsx"
        ),
    )