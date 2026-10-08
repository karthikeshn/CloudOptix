from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

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

POLICY_NAME = "Cloudwatch Custom Metrics Cardinality"

CATEGORY = "Cloudwatch Custom Metrics Cardinality"

SERVICE_NAME = "CloudWatch"

EFFORT_LEVEL = "Medium"

DEFAULT_REGION = "eu-west-1"


# ------------------------------------------------------------
# Custom metric detection
# ------------------------------------------------------------

# AWS service namespaces normally start with AWS/.
#
# Examples:
#
# AWS/EC2
# AWS/Lambda
# AWS/RDS
#
# Custom namespaces:
#
# ContainerInsights
# CWAgent
# MyApplication
#
CUSTOM_NAMESPACE_PREFIX = "AWS/"


# ------------------------------------------------------------
# Cardinality thresholds
# ------------------------------------------------------------

# Minimum number of custom metric series in a namespace
# before it is considered a high-cardinality candidate.
#
# Example:
#
# ContainerInsights -> 11,485 metrics
# threshold          -> 5,000
#
# Result -> candidate
MIN_CUSTOM_METRICS_PER_NAMESPACE = 5000


# ------------------------------------------------------------
# Dimension analysis
# ------------------------------------------------------------

# A dimension that appears on a large percentage of the
# namespace's metrics is potentially responsible for
# cardinality growth.
#
# Example:
#
# RequestId
# UserId
# Path
#
# can create a very large number of unique metric series.
MIN_DIMENSION_USAGE_PERCENT = 10.0


# Number of top dimensions to retain in the finding.
TOP_DIMENSIONS_TO_REPORT = 20


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
    Fetch all CloudWatch metrics using the ListMetrics
    paginator.

    ListMetrics can return multiple pages, therefore a paginator
    is required for complete discovery.
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
# 7. CUSTOM METRIC CHECK
# ============================================================

def is_custom_metric(
    metric: Dict[str, Any],
) -> bool:
    """
    Determine whether a metric belongs to a custom namespace.

    AWS service namespaces normally start with AWS/.

    Everything else is treated as a custom namespace.
    """

    namespace = metric.get(
        "Namespace",
        "",
    )

    if not namespace:
        return False

    return not namespace.startswith(
        CUSTOM_NAMESPACE_PREFIX
    )


# ============================================================
# 8. GROUP CUSTOM METRICS BY NAMESPACE
# ============================================================

def group_metrics_by_namespace(
    metrics: List[Dict[str, Any]],
) -> Dict[
    str,
    List[Dict[str, Any]],
]:
    """
    Group custom metrics by namespace.
    """

    namespace_metrics: Dict[
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

        if namespace not in namespace_metrics:

            namespace_metrics[
                namespace
            ] = []

        namespace_metrics[
            namespace
        ].append(
            metric
        )

    return namespace_metrics


# ============================================================
# 9. ANALYZE DIMENSION CARDINALITY
# ============================================================

def analyze_dimensions(
    metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyze dimension usage across a namespace.

    This does NOT simply count dimension definitions.

    It calculates:

        dimension name
        number of metric series containing it
        percentage of namespace metrics containing it
        number of unique values observed

    Example:

        RequestId
        used by: 9,200 metrics
        usage:   80%
        values:  8,900

    A dimension with many unique values is a strong
    cardinality signal.
    """

    total_metrics = len(
        metrics
    )

    dimension_usage: Dict[
        str,
        int,
    ] = {}

    dimension_values: Dict[
        str,
        Set[str],
    ] = {}

    for metric in metrics:

        seen_dimensions: Set[
            str
        ] = set()

        for dimension in metric.get(
            "Dimensions",
            [],
        ):

            dimension_name = dimension.get(
                "Name"
            )

            dimension_value = dimension.get(
                "Value"
            )

            if not dimension_name:
                continue

            # Count each dimension only once per metric.
            if (
                dimension_name
                not in seen_dimensions
            ):

                dimension_usage[
                    dimension_name
                ] = (
                    dimension_usage.get(
                        dimension_name,
                        0,
                    )
                    + 1
                )

                seen_dimensions.add(
                    dimension_name
                )

            if dimension_value is not None:

                if (
                    dimension_name
                    not in dimension_values
                ):

                    dimension_values[
                        dimension_name
                    ] = set()

                dimension_values[
                    dimension_name
                ].add(
                    str(
                        dimension_value
                    )
                )

    dimension_analysis: List[
        Dict[str, Any]
    ] = []

    for dimension_name, usage_count in (
        dimension_usage.items()
    ):

        usage_percentage = 0.0

        if total_metrics > 0:

            usage_percentage = (
                usage_count
                / total_metrics
            ) * 100.0

        unique_value_count = len(
            dimension_values.get(
                dimension_name,
                set(),
            )
        )

        dimension_analysis.append(
            {
                "dimensionName": dimension_name,
                "metricCount": usage_count,
                "usagePercentage": round(
                    usage_percentage,
                    2,
                ),
                "uniqueValueCount": (
                    unique_value_count
                ),
            }
        )

    # Sort primarily by unique value count,
    # then by metric usage.
    dimension_analysis.sort(
        key=lambda item: (
            item["uniqueValueCount"],
            item["metricCount"],
        ),
        reverse=True,
    )

    return {
        "totalMetrics": total_metrics,
        "dimensions": dimension_analysis,
    }


# ============================================================
# 10. IDENTIFY HIGH-CARDINALITY DIMENSIONS
# ============================================================

def identify_high_cardinality_dimensions(
    dimension_analysis: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Identify dimensions that are widely used and have
    significant numbers of unique values.

    The logic is intentionally configurable rather than
    hardcoding dimension names such as RequestId or UserId.
    """

    candidates: List[
        Dict[str, Any]
    ] = []

    for dimension in dimension_analysis.get(
        "dimensions",
        [],
    ):

        usage_percentage = dimension.get(
            "usagePercentage",
            0.0,
        )

        unique_value_count = dimension.get(
            "uniqueValueCount",
            0,
        )

        if (
            usage_percentage
            >= MIN_DIMENSION_USAGE_PERCENT
            and unique_value_count > 1
        ):

            candidates.append(
                dimension
            )

    return candidates[
        :TOP_DIMENSIONS_TO_REPORT
    ]


# ============================================================
# 11. NAMESPACE BUSINESS LOGIC
# ============================================================

def is_candidate(
    namespace: str,
    metrics: List[Dict[str, Any]],
) -> bool:
    """
    Determine whether a custom namespace is a
    cardinality candidate.

    Primary condition:

        Custom metric count >= threshold

    Secondary condition:

        Namespace must contain at least one dimension.

    The second condition ensures that the policy is actually
    analyzing metric cardinality rather than simply identifying
    a large collection of unrelated metrics.
    """

    metric_count = len(
        metrics
    )

    if (
        metric_count
        < MIN_CUSTOM_METRICS_PER_NAMESPACE
    ):
        return False

    has_dimensions = any(
        len(
            metric.get(
                "Dimensions",
                [],
            )
        )
        > 0
        for metric in metrics
    )

    return has_dimensions


# ============================================================
# 12. BUILD MESSAGE
# ============================================================

def build_message(
    namespace: str,
    metric_count: int,
    high_cardinality_dimensions: List[
        Dict[str, Any]
    ],
) -> str:
    """
    Build the human-readable finding message.
    """

    dimension_names = [
        item["dimensionName"]
        for item in high_cardinality_dimensions
    ]

    if dimension_names:

        dimensions_text = ", ".join(
            dimension_names[
                :5
            ]
        )

        return (
            f"CloudWatch custom namespace "
            f"'{namespace}' contains "
            f"{metric_count} metric series. "
            f"High-usage/high-cardinality dimensions "
            f"include: {dimensions_text}. "
            f"These dimensions may be generating excessive "
            f"custom metric cardinality."
        )

    return (
        f"CloudWatch custom namespace "
        f"'{namespace}' contains "
        f"{metric_count} metric series, which exceeds "
        f"the configured cardinality threshold of "
        f"{MIN_CUSTOM_METRICS_PER_NAMESPACE}."
    )


# ============================================================
# 13. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    namespace: str,
    metric_count: int,
    high_cardinality_dimensions: List[
        Dict[str, Any]
    ],
) -> str:
    """
    Build remediation guidance.
    """

    if high_cardinality_dimensions:

        dimension_names = [
            item["dimensionName"]
            for item in high_cardinality_dimensions[
                :5
            ]
        ]

        dimensions_text = ", ".join(
            dimension_names
        )

        return (
            f"Review the metric dimensions used by "
            f"CloudWatch namespace '{namespace}'. "
            f"Investigate high-cardinality dimensions "
            f"such as {dimensions_text}. "
            f"Remove unnecessary high-cardinality dimensions "
            f"where possible, aggregate metrics, or move "
            f"application metric publishing to Embedded Metric "
            f"Format where appropriate. Avoid dimensions such "
            f"as request IDs, user IDs, or unrestricted URL "
            f"paths when they are not required for monitoring."
        )

    return (
        f"Review the {metric_count} custom metric series "
        f"in namespace '{namespace}'. Remove unnecessary "
        f"dimensions and aggregate metrics where possible "
        f"to reduce metric cardinality."
    )


# ============================================================
# 14. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    namespace: str,
    metrics: List[Dict[str, Any]],
    dimension_analysis: Dict[str, Any],
    high_cardinality_dimensions: List[
        Dict[str, Any]
    ],
) -> Dict[str, Any]:
    """
    Build the standardized FinOps finding.

    Service-specific fields are retained here and will be
    bundled into the description column by export_to_excel().
    """

    metric_count = len(
        metrics
    )

    metric_names: List[
        str
    ] = []

    # Keep a representative list instead of dumping every
    # metric into the finding.
    for metric in metrics[
        :100
    ]:

        metric_name = metric.get(
            "MetricName",
            "",
        )

        if metric_name:

            metric_names.append(
                metric_name
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
            f"arn:aws:cloudwatch:"
            f"{region_name}::metric:"
            f"{namespace}"
        ),

        "resourceId": (
            f"{namespace}"
        ),

        "resourceArn": (
            f"arn:aws:cloudwatch:"
            f"{region_name}::metric:"
            f"{namespace}"
        ),

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
            namespace=namespace,
            metric_count=metric_count,
            high_cardinality_dimensions=(
                high_cardinality_dimensions
            ),
        ),

        "recommendation": build_recommendation(
            namespace=namespace,
            metric_count=metric_count,
            high_cardinality_dimensions=(
                high_cardinality_dimensions
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
        # ----------------------------------------------------

        "namespace": namespace,

        "metricCount": metric_count,

        "metricThreshold": (
            MIN_CUSTOM_METRICS_PER_NAMESPACE
        ),

        "dimensionCount": len(
            dimension_analysis.get(
                "dimensions",
                [],
            )
        ),

        "highCardinalityDimensions": (
            high_cardinality_dimensions
        ),

        "representativeMetricNames": (
            metric_names
        ),
    }


# ============================================================
# 15. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the 30 standard columns.

    Service-specific fields are dynamically bundled into the
    description column.
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
# 16. MAIN SCANNER
# ============================================================

def scan_service(
    region_name: str = DEFAULT_REGION,
) -> Dict[str, Any]:
    """
    Main CloudWatch Custom Metrics Cardinality scanner.
    """

    cloudwatch, sts = create_clients(
        region_name=region_name,
    )

    account_id = get_account_id(
        sts
    )

    print(
        f"[INFO] Scanning CloudWatch custom metrics "
        f"in {region_name}..."
    )

    # --------------------------------------------------------
    # Fetch all metrics
    # --------------------------------------------------------

    metrics = fetch_all_metrics(
        cloudwatch
    )

    print(
        f"[INFO] Total metrics discovered: "
        f"{len(metrics)}"
    )

    # --------------------------------------------------------
    # Group custom metrics
    # --------------------------------------------------------

    namespace_metrics = (
        group_metrics_by_namespace(
            metrics
        )
    )

    total_custom_metrics = sum(
        len(
            namespace_metric_list
        )
        for namespace_metric_list
        in namespace_metrics.values()
    )

    print(
        f"[INFO] Custom metrics discovered: "
        f"{total_custom_metrics}"
    )

    findings: List[
        Dict[str, Any]
    ] = []

    candidate_namespaces = 0

    # --------------------------------------------------------
    # Analyze each custom namespace
    # --------------------------------------------------------

    for namespace, namespace_metric_list in (
        namespace_metrics.items()
    ):

        metric_count = len(
            namespace_metric_list
        )

        print(
            f"[INFO] Namespace '{namespace}': "
            f"{metric_count} metrics"
        )

        try:

            if not is_candidate(
                namespace=namespace,
                metrics=namespace_metric_list,
            ):

                continue

            dimension_analysis = (
                analyze_dimensions(
                    namespace_metric_list
                )
            )

            high_cardinality_dimensions = (
                identify_high_cardinality_dimensions(
                    dimension_analysis
                )
            )

            finding = build_finding(
                account_id=account_id,
                region_name=region_name,
                namespace=namespace,
                metrics=namespace_metric_list,
                dimension_analysis=(
                    dimension_analysis
                ),
                high_cardinality_dimensions=(
                    high_cardinality_dimensions
                ),
            )

            findings.append(
                finding
            )

            candidate_namespaces += 1

            print(
                f"[FINDING] High cardinality namespace: "
                f"{namespace} | "
                f"Metrics: {metric_count}"
            )

        except ClientError as exc:

            print(
                f"[ERROR] Failed processing namespace "
                f"{namespace}: {exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error processing "
                f"namespace {namespace}: {exc}"
            )

            continue

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

        "totalCustomNamespaces": len(
            namespace_metrics
        ),

        "totalCandidateNamespaces": (
            candidate_namespaces
        ),

        "metricThreshold": (
            MIN_CUSTOM_METRICS_PER_NAMESPACE
        ),

        "findings": findings,
    }


# ============================================================
# 17. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    region = DEFAULT_REGION

    result = scan_service(
        region_name=region
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
            "cloudwatch_custom_metrics_cardinality.xlsx"
        ),
    )