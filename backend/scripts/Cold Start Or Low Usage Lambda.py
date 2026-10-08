
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


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

CATEGORY = (
    "Cold Start Or Low Usage Lambda"
)

POLICY_NAME = (
    "lambda-cold-start-or-low-usage"
)

SERVICE_NAME = "Lambda"

AREA_PATH = (
    "AWS Cost Optimization"
)

TAGS = "CLX"

EFFORT_LEVEL = "Low"

# ------------------------------------------------------------
# CloudWatch analysis period
# ------------------------------------------------------------

LOOKBACK_DAYS = 30


# ------------------------------------------------------------
# Low usage threshold
#
# A function averaging fewer than this many
# invocations per day is considered low usage.
#
# Adjust this according to your organization's
# actual FinOps policy.
# ------------------------------------------------------------

LOW_INVOCATIONS_PER_DAY = 1.0


# ------------------------------------------------------------
# High duration threshold
#
# Lambda average duration above this value
# is considered high duration.
#
# 1000 ms = 1 second
# ------------------------------------------------------------

HIGH_DURATION_MS = 1000.0


# ============================================================
# STANDARD EXCEL SCHEMA
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
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):

    lambda_client = boto3.client(
        "lambda",
        region_name=region_name,
        config=AWS_CONFIG,
    )

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

    return (
        lambda_client,
        cloudwatch,
        sts,
    )


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()[
        "Account"
    ]


# ============================================================
# FETCH ALL LAMBDA FUNCTIONS
# ============================================================

def fetch_all_lambda_functions(
    lambda_client,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL Lambda functions
    in the selected region.

    Pagination is handled using the boto3
    paginator.
    """

    functions = []

    paginator = (
        lambda_client.get_paginator(
            "list_functions"
        )
    )

    for page in paginator.paginate():

        page_functions = page.get(
            "Functions",
            []
        )

        functions.extend(
            page_functions
        )

    return functions


# ============================================================
# FETCH LAMBDA FUNCTION CONFIGURATION
# ============================================================

def fetch_lambda_configuration(
    lambda_client,
    function_name: str,
) -> Dict[str, Any]:
    """
    Fetch detailed Lambda configuration.
    """

    try:

        response = (
            lambda_client.get_function(
                FunctionName=function_name
            )
        )

        return response.get(
            "Configuration",
            {}
        )

    except ClientError as e:

        print(
            f"Could not fetch configuration "
            f"for Lambda "
            f"{function_name}: {e}"
        )

        return {}


# ============================================================
# FETCH CLOUDWATCH METRIC
# ============================================================

def fetch_lambda_metric(
    cloudwatch,
    function_name: str,
    metric_name: str,
    statistic: str,
) -> Dict[str, Any]:
    """
    Fetch a Lambda CloudWatch metric
    for the previous LOOKBACK_DAYS.

    Namespace:
        AWS/Lambda

    Dimension:
        FunctionName
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    try:

        response = (
            cloudwatch.get_metric_statistics(

                Namespace="AWS/Lambda",

                MetricName=metric_name,

                Dimensions=[

                    {
                        "Name":
                            "FunctionName",

                        "Value":
                            function_name,
                    }
                ],

                StartTime=start_time,

                EndTime=end_time,

                Period=86400,

                Statistics=[
                    statistic
                ],
            )
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        values = []

        for point in datapoints:

            if statistic in point:

                values.append(
                    point[statistic]
                )

        if not values:

            return {

                "value": None,

                "datapoints": 0,
            }

        if statistic == "Sum":

            value = sum(
                values
            )

        else:

            value = (
                sum(values)
                / len(values)
            )

        return {

            "value":
                value,

            "datapoints":
                len(values),
        }

    except ClientError as e:

        print(
            f"Could not fetch "
            f"{metric_name} "
            f"for Lambda "
            f"{function_name}: {e}"
        )

        return {

            "value": None,

            "datapoints": 0,

            "error": str(e),
        }


# ============================================================
# FETCH ALL LAMBDA METRICS
# ============================================================

def fetch_lambda_metrics(
    cloudwatch,
    function_name: str,
) -> Dict[str, Any]:
    """
    Fetch all metrics required by the
    FinOps policy.
    """

    # --------------------------------------------------------
    # Invocations
    # --------------------------------------------------------

    invocations = fetch_lambda_metric(

        cloudwatch=cloudwatch,

        function_name=function_name,

        metric_name="Invocations",

        statistic="Sum",
    )

    # --------------------------------------------------------
    # Duration
    # --------------------------------------------------------

    duration = fetch_lambda_metric(

        cloudwatch=cloudwatch,

        function_name=function_name,

        metric_name="Duration",

        statistic="Average",
    )

    # --------------------------------------------------------
    # Errors
    # --------------------------------------------------------

    errors = fetch_lambda_metric(

        cloudwatch=cloudwatch,

        function_name=function_name,

        metric_name="Errors",

        statistic="Sum",
    )

    # --------------------------------------------------------
    # Throttles
    # --------------------------------------------------------

    throttles = fetch_lambda_metric(

        cloudwatch=cloudwatch,

        function_name=function_name,

        metric_name="Throttles",

        statistic="Sum",
    )

    # --------------------------------------------------------
    # Extract values
    # --------------------------------------------------------

    invocation_count = (
        invocations.get(
            "value"
        )
    )

    average_duration = (
        duration.get(
            "value"
        )
    )

    error_count = (
        errors.get(
            "value"
        )
    )

    throttle_count = (
        throttles.get(
            "value"
        )
    )

    # --------------------------------------------------------
    # Calculate average invocations per day
    # --------------------------------------------------------

    average_invocations_per_day = None

    if invocation_count is not None:

        average_invocations_per_day = (

            invocation_count
            / LOOKBACK_DAYS
        )

    # --------------------------------------------------------
    # Calculate error rate
    # --------------------------------------------------------

    error_rate = None

    if (
        invocation_count is not None
        and invocation_count > 0
        and error_count is not None
    ):

        error_rate = (

            error_count
            / invocation_count
        ) * 100

    return {

        "invocations":
            invocation_count,

        "averageDurationMs":
            average_duration,

        "errors":
            error_count,

        "throttles":
            throttle_count,

        "averageInvocationsPerDay":
            average_invocations_per_day,

        "errorRatePercent":
            error_rate,

        "invocationDatapoints":
            invocations.get(
                "datapoints"
            ),

        "durationDatapoints":
            duration.get(
                "datapoints"
            ),

        "errorDatapoints":
            errors.get(
                "datapoints"
            ),

        "throttleDatapoints":
            throttles.get(
                "datapoints"
            ),
    }


# ============================================================
# DETERMINE LOW USAGE
# ============================================================

def is_low_usage(
    average_invocations_per_day,
) -> bool:

    if (
        average_invocations_per_day
        is None
    ):

        # If CloudWatch returns no data points for Invocations, 
        # it means the function was invoked 0 times, which is low usage.
        return True

    return (
        average_invocations_per_day
        < LOW_INVOCATIONS_PER_DAY
    )


# ============================================================
# DETERMINE HIGH DURATION
# ============================================================

def is_high_duration(
    average_duration_ms,
) -> bool:

    if (
        average_duration_ms
        is None
    ):

        return False

    return (
        average_duration_ms
        > HIGH_DURATION_MS
    )


# ============================================================
# DETERMINE FINDING TYPE
# ============================================================

def determine_finding_type(
    low_usage: bool,
    high_duration: bool,
) -> str:

    if low_usage and high_duration:

        return (
            "Low Usage and High Duration"
        )

    if low_usage:

        return "Low Usage"

    if high_duration:

        return "High Duration"

    return "No Finding"


# ============================================================
# BUILD MESSAGE
# ============================================================

def build_message(
    function_name: str,
    memory_size: int | None,
    average_duration_ms: float | None,
    invocation_count: float | None,
    average_invocations_per_day: float | None,
    low_usage: bool,
    high_duration: bool,
) -> str:

    duration_text = (
        f"{average_duration_ms:.2f}ms"
        if average_duration_ms
        is not None
        else "Unknown"
    )

    invocation_text = (
        f"{int(invocation_count)}"
        if invocation_count
        is not None
        else "Unknown"
    )

    daily_invocation_text = (
        f"{average_invocations_per_day:.2f}"
        if average_invocations_per_day
        is not None
        else "Unknown"
    )

    # --------------------------------------------------------
    # Low usage + high duration
    # --------------------------------------------------------

    if low_usage and high_duration:

        return (

            f"Lambda function "
            f"'{function_name}' is flagged "
            f"for both low usage and high "
            f"average duration. "

            f"Memory: "
            f"{memory_size} MB. "

            f"Average Duration: "
            f"{duration_text}. "

            f"Total Invocations over "
            f"{LOOKBACK_DAYS} days: "
            f"{invocation_text}. "

            f"Average Invocations per Day: "
            f"{daily_invocation_text}."
        )

    # --------------------------------------------------------
    # Low usage
    # --------------------------------------------------------

    if low_usage:

        return (

            f"Lambda function "
            f"'{function_name}' has very low "
            f"usage over the last "
            f"{LOOKBACK_DAYS} days. "

            f"Memory: "
            f"{memory_size} MB. "

            f"Total Invocations: "
            f"{invocation_text}. "

            f"Average Invocations per Day: "
            f"{daily_invocation_text}. "

            f"Review whether the function "
            f"is still required."
        )

    # --------------------------------------------------------
    # High duration
    # --------------------------------------------------------

    if high_duration:

        return (

            f"Lambda function "
            f"'{function_name}' has a high "
            f"average duration of "
            f"{duration_text}. "

            f"Memory: "
            f"{memory_size} MB. "

            f"Review the function's execution "
            f"time, memory allocation, "
            f"dependencies and code "
            f"performance."
        )

    return (
        f"Lambda function "
        f"'{function_name}' does not "
        f"currently meet the configured "
        f"FinOps thresholds."
    )


# ============================================================
# BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    function_name: str,
    low_usage: bool,
    high_duration: bool,
) -> str:

    recommendations = []

    if low_usage:

        recommendations.append(

            "Review whether the Lambda "
            "function is still required. "
            "If it is unused, consider "
            "decommissioning it. If it is "
            "required for occasional "
            "events, retain it."
        )

    if high_duration:

        recommendations.append(

            "Review Lambda memory allocation, "
            "execution code, dependencies, "
            "external API calls and database "
            "calls. Increasing memory may "
            "also increase CPU allocation "
            "and reduce execution duration."
        )

    if not recommendations:

        return (
            "No immediate optimization "
            "action required."
        )

    return " ".join(
        recommendations
    )


# ============================================================
# BUILD DESCRIPTION
# ============================================================

def build_description(
    account_id: str,
    region_name: str,
    function_name: str,
    function_arn: str | None,
    configuration: Dict[str, Any],
    metrics: Dict[str, Any],
    finding_type: str,
) -> str:

    memory_size = configuration.get(
        "MemorySize"
    )

    runtime = configuration.get(
        "Runtime"
    )

    timeout = configuration.get(
        "Timeout"
    )

    handler = configuration.get(
        "Handler"
    )

    state = configuration.get(
        "State"
    )

    last_modified = configuration.get(
        "LastModified"
    )

    average_duration = metrics.get(
        "averageDurationMs"
    )

    invocation_count = metrics.get(
        "invocations"
    )

    average_invocations_per_day = (
        metrics.get(
            "averageInvocationsPerDay"
        )
    )

    error_count = metrics.get(
        "errors"
    )

    throttle_count = metrics.get(
        "throttles"
    )

    error_rate = metrics.get(
        "errorRatePercent"
    )

    low_usage = is_low_usage(
        average_invocations_per_day
    )

    high_duration = is_high_duration(
        average_duration
    )

    # --------------------------------------------------------
    # Keep all Lambda-specific information
    # inside description.
    # --------------------------------------------------------

    return (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {function_name} | "

        f"resourceArn: {function_arn} | "

        f"runtime: {runtime} | "

        f"memoryMB: {memory_size} | "

        f"timeoutSeconds: {timeout} | "

        f"handler: {handler} | "

        f"state: {state} | "

        f"lastModified: {last_modified} | "

        f"invocations{LOOKBACK_DAYS}Days: "
        f"{invocation_count} | "

        f"averageInvocationsPerDay: "
        f"{average_invocations_per_day} | "

        f"averageDurationMs: "
        f"{average_duration} | "

        f"errors{LOOKBACK_DAYS}Days: "
        f"{error_count} | "

        f"throttles{LOOKBACK_DAYS}Days: "
        f"{throttle_count} | "

        f"errorRatePercent: "
        f"{error_rate} | "

        f"lookbackDays: "
        f"{LOOKBACK_DAYS} | "

        f"lowUsageThresholdPerDay: "
        f"{LOW_INVOCATIONS_PER_DAY} | "

        f"highDurationThresholdMs: "
        f"{HIGH_DURATION_MS} | "

        f"lowUsage: {low_usage} | "

        f"highDuration: {high_duration} | "

        f"type: {finding_type} | "

        f"policy: {POLICY_NAME}"
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_lambda_finding(
    function: Dict[str, Any],
    configuration: Dict[str, Any],
    metrics: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    function_name = function.get(
        "FunctionName"
    )

    function_arn = function.get(
        "FunctionArn"
    )

    memory_size = configuration.get(
        "MemorySize"
    )

    average_duration = metrics.get(
        "averageDurationMs"
    )

    invocation_count = metrics.get(
        "invocations"
    )

    average_invocations_per_day = (
        metrics.get(
            "averageInvocationsPerDay"
        )
    )

    low_usage = is_low_usage(
        average_invocations_per_day
    )

    high_duration = is_high_duration(
        average_duration
    )

    # --------------------------------------------------------
    # Determine finding type
    # --------------------------------------------------------

    finding_type = (
        determine_finding_type(

            low_usage=
                low_usage,

            high_duration=
                high_duration,
        )
    )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = build_message(

        function_name=
            function_name,

        memory_size=
            memory_size,

        average_duration_ms=
            average_duration,

        invocation_count=
            invocation_count,

        average_invocations_per_day=
            average_invocations_per_day,

        low_usage=
            low_usage,

        high_duration=
            high_duration,
    )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        build_recommendation(

            function_name=
                function_name,

            low_usage=
                low_usage,

            high_duration=
                high_duration,
        )
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        build_description(

            account_id=
                account_id,

            region_name=
                region_name,

            function_name=
                function_name,

            function_arn=
                function_arn,

            configuration=
                configuration,

            metrics=
                metrics,

            finding_type=
                finding_type,
        )
    )

    # --------------------------------------------------------
    # Standard finding
    # --------------------------------------------------------

    return {

        "workItemType":
            "Task",

        "state":
            "To Do",

        "id":
            "",

        "title":
            CATEGORY,

        "category":
            CATEGORY,

        "owner":
            "",

        "assignedTo":
            "",

        "status":
            "Pending for Review",

        "areaPath":
            AREA_PATH,

        "tags":
            TAGS,

        "commentCount":
            0,

        "accountId":
            account_id,

        "region":
            region_name,

        "resourceNameOrId":
            function_name,

        "resourceId":
            function_name,

        "resourceArn":
            function_arn,

        "service":
            SERVICE_NAME,

        "type":
            finding_type,

        "policy":
            POLICY_NAME,

        "effortLevel":
            EFFORT_LEVEL,

        "message":
            message,

        "recommendation":
            recommendation,

        "description":
            description,

        # ----------------------------------------------------
        # Cost is intentionally not calculated yet.
        #
        # CUR + Athena can be added later.
        # ----------------------------------------------------

        "currentDailyCost":
            "To be updated",

        "currentMonthlyCost":
            "To be updated",

        "estimatedMonthlySavings":
            "To be updated",

        # ----------------------------------------------------
        # Human workflow fields
        # ----------------------------------------------------

        "approvalComments":
            "",

        "reasonForRejection":
            "",

        "achievedSavingsMonthly":
            "",

        "month":
            "",
    }


# ============================================================
# SCAN ALL LAMBDA FUNCTIONS
# ============================================================

def scan_lambda_functions(
    region_name: str,
) -> Dict[str, Any]:

    (
        lambda_client,
        cloudwatch,
        sts,
    ) = create_clients(
        region_name
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"\nAccount ID: {account_id}"
    )

    print(
        f"Region: {region_name}"
    )

    # --------------------------------------------------------
    # Fetch all Lambda functions
    # --------------------------------------------------------

    functions = (
        fetch_all_lambda_functions(
            lambda_client
        )
    )

    print(
        f"Total Lambda functions: "
        f"{len(functions)}"
    )

    findings = []

    # --------------------------------------------------------
    # Scan every function
    # --------------------------------------------------------

    for function in functions:

        function_name = function.get(
            "FunctionName"
        )

        print(
            f"\nScanning Lambda: "
            f"{function_name}"
        )

        # ----------------------------------------------------
        # Fetch configuration
        # ----------------------------------------------------

        configuration = (
            fetch_lambda_configuration(

                lambda_client,

                function_name,
            )
        )

        # ----------------------------------------------------
        # Fetch CloudWatch metrics
        # ----------------------------------------------------

        metrics = (
            fetch_lambda_metrics(

                cloudwatch,

                function_name,
            )
        )

        average_duration = metrics.get(
            "averageDurationMs"
        )

        average_invocations_per_day = (
            metrics.get(
                "averageInvocationsPerDay"
            )
        )

        print(
            f"Average duration: "
            f"{average_duration}"
        )

        print(
            f"Average invocations/day: "
            f"{average_invocations_per_day}"
        )

        # ----------------------------------------------------
        # Determine policy conditions
        # ----------------------------------------------------

        low_usage = is_low_usage(
            average_invocations_per_day
        )

        high_duration = is_high_duration(
            average_duration
        )

        # ----------------------------------------------------
        # Only create finding if at least
        # one policy condition is met.
        # ----------------------------------------------------

        if not (
            low_usage
            or high_duration
        ):

            print(
                "No finding."
            )

            continue

        # ----------------------------------------------------
        # Build finding
        # ----------------------------------------------------

        finding = build_lambda_finding(

            function=
                function,

            configuration=
                configuration,

            metrics=
                metrics,

            account_id=
                account_id,

            region_name=
                region_name,
        )

        findings.append(
            finding
        )

        print(
            "Finding created."
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    return {

        "accountId":
            account_id,

        "region":
            region_name,

        "totalFunctionsScanned":
            len(functions),

        "totalFindings":
            len(findings),

        "findings":
            findings,
    }


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
):

    # --------------------------------------------------------
    # Guarantee exact standard schema
    # --------------------------------------------------------

    normalized_findings = []

    for finding in findings:

        normalized_finding = {}

        for column in STANDARD_COLUMNS:

            normalized_finding[
                column
            ] = finding.get(
                column,
                ""
            )

        normalized_findings.append(
            normalized_finding
        )

    # --------------------------------------------------------
    # Create DataFrame
    # --------------------------------------------------------

    df = pd.DataFrame(
        normalized_findings,
        columns=STANDARD_COLUMNS,
    )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    df.to_excel(
        filename,
        index=False
    )

    print(
        f"\nExcel report successfully "
        f"created: {filename}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Only REGION is supplied.
    #
    # Lambda function IDs/names are discovered
    # automatically.
    # --------------------------------------------------------

    region = "us-east-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS LAMBDA FINOPS SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Lookback: "
        f"{LOOKBACK_DAYS} days"
    )

    print(
        f"Low usage threshold: "
        f"{LOW_INVOCATIONS_PER_DAY} "
        f"invocations/day"
    )

    print(
        f"High duration threshold: "
        f"{HIGH_DURATION_MS} ms"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_lambda_functions(
        region
    )

    # --------------------------------------------------------
    # Print JSON
    # --------------------------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "SCAN RESULT"
    )

    print(
        "=========================================="
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "SUMMARY"
    )

    print(
        "=========================================="
    )

    print(
        "Account ID:",
        result.get(
            "accountId"
        )
    )

    print(
        "Region:",
        result.get(
            "region"
        )
    )

    print(
        "Functions scanned:",
        result.get(
            "totalFunctionsScanned"
        )
    )

    print(
        "Findings:",
        result.get(
            "totalFindings"
        )
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Findings
    # --------------------------------------------------------

    findings = result.get(
        "findings",
        []
    )

    if not findings:

        print(
            "\nNo Lambda FinOps findings "
            "found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "lambda_cold_start_low_usage_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

