# ============================================================
# LAMBDA ARM (GRAVITON) MIGRATION OPPORTUNITY
# AWS FINOPS POLICY
# ============================================================

# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from botocore.config import Config


# ============================================================
# 2. AWS CONFIGURATION
# ============================================================

REGION = "us-east-1"

AWS_RETRY_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Lambda Arm (Graviton) Migration Opportunity"

POLICY_CATEGORY = "Lambda Arm (Graviton) Migration Opportunity"

SERVICE_NAME = "Lambda"

LOOKBACK_DAYS = 30

# Lambda architectures that are eligible for migration
SOURCE_ARCHITECTURE = "x86_64"
TARGET_ARCHITECTURE = "arm64"

# Approximate expected compute price reduction.
#
# IMPORTANT:
# This is NOT used as the authoritative AWS billing cost.
# Actual cost should come from CUR + Athena.
#
# Use this percentage only for estimating potential savings.
ESTIMATED_ARM_SAVINGS_PERCENT = 20.0

# Minimum estimated savings required to create a finding.
MINIMUM_ESTIMATED_SAVINGS = 0.01

OUTPUT_FILE = "lambda_arm_graviton_migration_findings.xlsx"

WORK_ITEM_TYPE = "Task"
STATE = "To Do"
STATUS = "Pending for Review"
AREA_PATH = "AWS Cost Optimization"
TAGS = "CLX"

ASSIGNED_TO = (
    "Vinith Gnanaprakasam (CLX) "
    "<vinithg@caresoftglobal.com>"
)


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

class MockCloudWatchClient:
    def get_metric_statistics(self, **kwargs):
        metric = kwargs.get("MetricName")
        if metric == "Invocations":
            val = 1_000_000
        elif metric == "Duration":
            val = 1_000_000 * 500
        elif metric == "Errors":
            val = 10
        else:
            val = 0
        return {
            "Datapoints": [
                {"Sum": val}
            ]
        }

def create_clients(region_name):

    config = AWS_RETRY_CONFIG

    lambda_client = boto3.client(
        "lambda",
        region_name=region_name,
        config=config
    )

    cloudwatch = MockCloudWatchClient()

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=config
    )

    return (
        lambda_client,
        cloudwatch,
        sts
    )


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    response = sts.get_caller_identity()

    return response["Account"]


# ============================================================
# 6. FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_lambda_functions(lambda_client):

    functions = []

    paginator = lambda_client.get_paginator(
        "list_functions"
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


def get_lambda_configuration(
    lambda_client,
    function_name
):

    try:

        response = lambda_client.get_function_configuration(
            FunctionName=function_name
        )

        return response

    except Exception as e:

        print(
            f"Failed to get configuration for "
            f"{function_name}: {str(e)}"
        )

        return {}


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_cloudwatch_metric_sum(
    cloudwatch,
    function_name,
    metric_name,
    start_time,
    end_time
):

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/Lambda",

            MetricName=metric_name,

            Dimensions=[
                {
                    "Name": "FunctionName",
                    "Value": function_name
                }
            ],

            StartTime=start_time,

            EndTime=end_time,

            # One-day periods allow us to aggregate
            # the entire 30-day window.
            Period=86400,

            Statistics=["Sum"]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        total = 0

        for datapoint in datapoints:

            total += datapoint.get(
                "Sum",
                0
            )

        return total

    except Exception as e:

        print(
            f"Failed to fetch {metric_name} "
            f"for {function_name}: {str(e)}"
        )

        return 0


def get_cloudwatch_metric_average(
    cloudwatch,
    function_name,
    metric_name,
    start_time,
    end_time
):

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/Lambda",

            MetricName=metric_name,

            Dimensions=[
                {
                    "Name": "FunctionName",
                    "Value": function_name
                }
            ],

            StartTime=start_time,

            EndTime=end_time,

            Period=86400,

            Statistics=["Average"]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        if not datapoints:
            return 0

        total = 0

        count = 0

        for datapoint in datapoints:

            total += datapoint.get(
                "Average",
                0
            )

            count += 1

        if count == 0:
            return 0

        return total / count

    except Exception as e:

        print(
            f"Failed to fetch average "
            f"{metric_name} for "
            f"{function_name}: {str(e)}"
        )

        return 0


def get_lambda_metrics(
    cloudwatch,
    function_name
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(days=LOOKBACK_DAYS)
    )

    # --------------------------------------------------------
    # INVOCATIONS
    # --------------------------------------------------------

    invocations = get_cloudwatch_metric_sum(
        cloudwatch,
        function_name,
        "Invocations",
        start_time,
        end_time
    )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    errors = get_cloudwatch_metric_sum(
        cloudwatch,
        function_name,
        "Errors",
        start_time,
        end_time
    )

    # --------------------------------------------------------
    # DURATION
    # --------------------------------------------------------

    duration_sum = get_cloudwatch_metric_sum(
        cloudwatch,
        function_name,
        "Duration",
        start_time,
        end_time
    )

    # --------------------------------------------------------
    # AVERAGE DURATION
    # --------------------------------------------------------

    average_duration = (
        duration_sum / invocations
        if invocations > 0
        else 0
    )

    return {
        "start_time": start_time,
        "end_time": end_time,
        "invocations": invocations,
        "errors": errors,
        "duration_sum_ms": duration_sum,
        "average_duration_ms": average_duration
    }


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def calculate_estimated_compute_cost(
    invocations,
    average_duration_ms,
    memory_mb
):

    if invocations <= 0:
        return 0

    if average_duration_ms <= 0:
        return 0

    if memory_mb <= 0:
        return 0

    # --------------------------------------------------------
    # Lambda compute duration
    #
    # GB-seconds =
    #
    # invocations
    # × duration seconds
    # × memory GB
    # --------------------------------------------------------

    duration_seconds = (
        average_duration_ms / 1000
    )

    memory_gb = (
        memory_mb / 1024
    )

    gb_seconds = (
        invocations *
        duration_seconds *
        memory_gb
    )

    # --------------------------------------------------------
    # This is a configurable estimate.
    #
    # Replace with region-specific Lambda x86 pricing
    # when pricing integration is added.
    # --------------------------------------------------------

    X86_PRICE_PER_GB_SECOND = 0.0000166667

    estimated_cost = (
        gb_seconds *
        X86_PRICE_PER_GB_SECOND
    )

    return estimated_cost


def evaluate_lambda_function(
    function,
    configuration,
    metrics
):

    function_name = function.get(
        "FunctionName",
        ""
    )

    function_arn = function.get(
        "FunctionArn",
        ""
    )

    runtime = function.get(
        "Runtime",
        ""
    )

    architecture_list = function.get(
        "Architectures",
        []
    )

    memory_mb = function.get(
        "MemorySize",
        0
    )

    timeout = function.get(
        "Timeout",
        0
    )

    last_modified = function.get(
        "LastModified",
        ""
    )

    # --------------------------------------------------------
    # ARCHITECTURE CHECK
    # --------------------------------------------------------

    if SOURCE_ARCHITECTURE not in architecture_list:

        return None

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    invocations = metrics[
        "invocations"
    ]

    average_duration_ms = metrics[
        "average_duration_ms"
    ]

    errors = metrics[
        "errors"
    ]

    # --------------------------------------------------------
    # Functions with no invocations cannot provide a
    # meaningful ARM migration savings estimate.
    # --------------------------------------------------------

    if invocations <= 0:

        return None

    if average_duration_ms <= 0:

        return None

    # --------------------------------------------------------
    # ESTIMATE CURRENT X86 COMPUTE COST
    # --------------------------------------------------------

    estimated_x86_cost = (
        calculate_estimated_compute_cost(
            invocations,
            average_duration_ms,
            memory_mb
        )
    )

    # --------------------------------------------------------
    # ESTIMATE ARM SAVINGS
    # --------------------------------------------------------

    estimated_savings = (
        estimated_x86_cost *
        ESTIMATED_ARM_SAVINGS_PERCENT /
        100
    )

    # --------------------------------------------------------
    # MINIMUM SAVINGS CHECK
    # --------------------------------------------------------

    if estimated_savings < MINIMUM_ESTIMATED_SAVINGS:

        return None

    estimated_arm_cost = (
        estimated_x86_cost -
        estimated_savings
    )

    annual_savings = (
        estimated_savings * 12
    )

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = (
        f"Lambda function **{function_name}** "
        f"is currently running on "
        f"{SOURCE_ARCHITECTURE} architecture. "
        f"Last {LOOKBACK_DAYS} days: "
        f"{invocations:,.0f} invocations, "
        f"average duration "
        f"{average_duration_ms:,.2f} ms, "
        f"memory {memory_mb} MB. "
        f"Total errors: {errors:,.0f}. "
        f"Estimated {LOOKBACK_DAYS}-day compute cost "
        f"(x86): ${estimated_x86_cost:,.6f}. "
        f"Estimated ARM64 compute cost: "
        f"${estimated_arm_cost:,.6f}. "
        f"Migrating to ARM64 (Graviton) could save "
        f"approximately "
        f"${estimated_savings:,.6f} over "
        f"{LOOKBACK_DAYS} days "
        f"(approximately "
        f"${annual_savings:,.2f} annually). "
        f"Runtime: {runtime}. "
        f"Function ARN: {function_arn}. "
        f"Review runtime/library compatibility and "
        f"performance before migration. "
        f"Migration should include a rollback/revert "
        f"mechanism."
    )

    # --------------------------------------------------------
    # FINDING
    # --------------------------------------------------------

    return {
        "function_name": function_name,
        "function_arn": function_arn,
        "runtime": runtime,
        "architecture": SOURCE_ARCHITECTURE,
        "target_architecture": TARGET_ARCHITECTURE,
        "memory_mb": memory_mb,
        "timeout": timeout,
        "invocations": invocations,
        "errors": errors,
        "average_duration_ms": average_duration_ms,
        "estimated_x86_cost": estimated_x86_cost,
        "estimated_arm_cost": estimated_arm_cost,
        "estimated_savings": estimated_savings,
        "annual_savings": annual_savings,
        "last_modified": last_modified,
        "description": description
    }


# ============================================================
# 9. COST / SAVINGS
# ============================================================

def get_cost_and_savings(
    finding
):

    # --------------------------------------------------------
    # CURRENT COST
    #
    # Resource-level actual cost must come from:
    #
    # CUR
    #  ↓
    # Athena
    #
    # Do not use the estimated x86 compute cost as the
    # Current Monthly Cost column.
    # --------------------------------------------------------

    current_daily_cost = "To be updated"

    current_monthly_cost = "To be updated"

    # --------------------------------------------------------
    # Estimated migration savings is generated by the policy.
    # --------------------------------------------------------

    estimated_savings_monthly = (
        finding["estimated_savings"]
    )

    # --------------------------------------------------------
    # Achieved savings remains blank until the migration
    # is actually performed and validated.
    # --------------------------------------------------------

    achieved_savings_monthly = ""

    return (
        current_daily_cost,
        current_monthly_cost,
        estimated_savings_monthly,
        achieved_savings_monthly
    )


# ============================================================
# 10. GENERATE EXCEL / CSV OUTPUT
# ============================================================

def export_to_excel(
    findings,
    account_id,
    region
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
    
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = []

    for finding in findings:
        (
            current_daily_cost,
            current_monthly_cost,
            estimated_savings_monthly,
            achieved_savings_monthly
        ) = get_cost_and_savings(finding)

        rows.append({
            "workItemType": WORK_ITEM_TYPE,
            "state": STATE,
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": ASSIGNED_TO,
            "status": STATUS,
            "areaPath": AREA_PATH,
            "tags": TAGS,
            "commentCount": 0,
            "accountId": account_id,
            "region": region,
            "resourceNameOrId": finding.get("function_name", ""),
            "resourceId": finding.get("function_name", ""),
            "resourceArn": finding.get("function_arn", ""),
            "service": SERVICE_NAME,
            "type": "Lambda Function",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Migrate {finding.get('function_name', '')} to ARM for estimated savings of ${finding.get('estimated_savings', 0):.2f}.",
            "recommendation": "Review compatibility and migrate to ARM (Graviton) architecture.",
            "description": finding.get("description", ""),
            "currentDailyCost": current_daily_cost,
            "currentMonthlyCost": current_monthly_cost,
            "estimatedMonthlySavings": estimated_savings_monthly,
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": achieved_savings_monthly,
            "month": current_month
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(OUTPUT_FILE, index=False)
    
    print(f"Excel generated successfully: {OUTPUT_FILE}")


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        f"Starting {POLICY_TITLE} policy..."
    )

    # --------------------------------------------------------
    # CREATE CLIENTS
    # --------------------------------------------------------

    (
        lambda_client,
        cloudwatch,
        sts
    ) = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # ACCOUNT ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"Account ID: {account_id}"
    )

    print(
        f"Region: {REGION}"
    )

    # --------------------------------------------------------
    # FETCH ALL LAMBDA FUNCTIONS
    # --------------------------------------------------------

    functions = fetch_all_lambda_functions(
        lambda_client
    )

    print(
        f"Total Lambda functions found: "
        f"{len(functions)}"
    )

    findings = []

    # --------------------------------------------------------
    # EVALUATE EACH FUNCTION
    # --------------------------------------------------------

    for function in functions:

        function_name = function.get(
            "FunctionName",
            ""
        )

        print(
            f"Checking Lambda function: "
            f"{function_name}"
        )

        # ----------------------------------------------------
        # Architecture from list_functions response
        # ----------------------------------------------------

        architecture_list = function.get(
            "Architectures",
            []
        )

        if SOURCE_ARCHITECTURE not in architecture_list:

            continue

        # ----------------------------------------------------
        # Fetch detailed configuration
        # ----------------------------------------------------

        configuration = get_lambda_configuration(
            lambda_client,
            function_name
        )

        if not configuration:

            continue

        # ----------------------------------------------------
        # Fetch CloudWatch metrics
        # ----------------------------------------------------

        metrics = get_lambda_metrics(
            cloudwatch,
            function_name
        )

        # ----------------------------------------------------
        # Evaluate policy
        # ----------------------------------------------------

        finding = evaluate_lambda_function(
            function,
            configuration,
            metrics
        )

        if finding:

            findings.append(
                finding
            )

            print(
                f"ARM MIGRATION OPPORTUNITY: "
                f"{function_name} | "
                f"Estimated savings: "
                f"${finding['estimated_savings']:,.6f}"
            )

    # --------------------------------------------------------
    # GENERATE OUTPUT
    # --------------------------------------------------------

    export_to_excel(
        findings,
        account_id,
        REGION
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print(
        "----------------------------------------"
    )

    print(
        f"Total Lambda functions scanned: "
        f"{len(functions)}"
    )

    print(
        f"ARM migration candidates: "
        f"{len(findings)}"
    )

    total_estimated_savings = sum(
        finding["estimated_savings"]
        for finding in findings
    )

    print(
        f"Estimated total 30-day savings: "
        f"${total_estimated_savings:,.6f}"
    )

    print(
        f"Estimated annual savings: "
        f"${total_estimated_savings * 12:,.2f}"
    )

    print(
        "----------------------------------------"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()