# ============================================================
# AWS FinOps Policy
# Policy: DynamoDB Unused Low Table Activity
# Service: DynamoDB
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone, timedelta
from botocore.config import Config


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = (
    "dynamodb_unused_low_table_activity.xlsx"
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
    "DynamoDB Unused Low Table Activity"
)

CATEGORY = (
    "DynamoDB Unused Low Table Activity"
)

SERVICE = "DynamoDB"

ACTIVITY_LOOKBACK_DAYS = 30

# A table is considered a candidate when its
# total consumed capacity over the lookback
# period is at or below this threshold.
#
# 0 means no consumed read/write capacity.
LOW_ACTIVITY_THRESHOLD = 0


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    dynamodb = boto3.client(
        "dynamodb",
        region_name=region_name,
        config=AWS_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return (
        dynamodb,
        cloudwatch,
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

def fetch_all_dynamodb_tables(
    dynamodb
):

    tables = []

    paginator = dynamodb.get_paginator(
        "list_tables"
    )

    pages = paginator.paginate()

    for page in pages:

        tables.extend(
            page.get(
                "TableNames",
                []
            )
        )

    return tables


def fetch_table_details(
    dynamodb,
    table_name
):

    try:
        response = dynamodb.describe_table(
            TableName=table_name
        )

        return response.get(
            "Table",
            {}
        )
    except Exception as error:
        print(f"Error fetching details for {table_name}: {error}")
        return {}


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_table_tags(
    dynamodb,
    table_arn
):

    try:

        response = dynamodb.list_tags_of_resource(
            ResourceArn=table_arn
        )

        tags = {}

        for tag in response.get(
            "Tags",
            []
        ):

            key = tag.get("Key")
            value = tag.get("Value")

            if key:

                tags[key] = value

        return tags

    except Exception as error:

        print(
            f"Unable to fetch tags for "
            f"{table_arn}: {error}"
        )

        return {}


def get_cloudwatch_metric_sum(
    cloudwatch,
    table_name,
    metric_name,
    start_time,
    end_time
):

    """
    Get the total consumed capacity for
    a DynamoDB table during the lookback
    period.

    DynamoDB publishes:

        ConsumedReadCapacityUnits
        ConsumedWriteCapacityUnits

    in the AWS/DynamoDB namespace.
    """

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName=metric_name,
            Dimensions=[
                {
                    "Name": "TableName",
                    "Value": table_name
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=[
                "Sum"
            ]
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        total = 0.0

        for datapoint in datapoints:

            value = datapoint.get(
                "Sum"
            )

            if value is not None:

                total += float(value)

        return total, len(datapoints)

    except Exception as error:

        print(
            f"CloudWatch metric failed for "
            f"{table_name} / {metric_name}: "
            f"{error}"
        )

        return None, 0


def get_table_activity(
    cloudwatch,
    table_name
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=ACTIVITY_LOOKBACK_DAYS
        )
    )

    # --------------------------------------------------------
    # Read activity
    # --------------------------------------------------------

    read_units, read_datapoints = (
        get_cloudwatch_metric_sum(
            cloudwatch,
            table_name,
            "ConsumedReadCapacityUnits",
            start_time,
            end_time
        )
    )

    # --------------------------------------------------------
    # Write activity
    # --------------------------------------------------------

    write_units, write_datapoints = (
        get_cloudwatch_metric_sum(
            cloudwatch,
            table_name,
            "ConsumedWriteCapacityUnits",
            start_time,
            end_time
        )
    )

    if (
        read_units is None
        or write_units is None
    ):

        return {
            "available": False,
            "read_units": read_units,
            "write_units": write_units,
            "total_units": None,
            "read_datapoints": read_datapoints,
            "write_datapoints": write_datapoints,
            "start_time": start_time,
            "end_time": end_time
        }

    total_units = (
        read_units +
        write_units
    )

    return {
        "available": True,
        "read_units": read_units,
        "write_units": write_units,
        "total_units": total_units,
        "read_datapoints": read_datapoints,
        "write_datapoints": write_datapoints,
        "start_time": start_time,
        "end_time": end_time
    }


def get_billing_mode(
    table_details
):

    billing_mode_summary = (
        table_details.get(
            "BillingModeSummary"
        )
    )

    if not billing_mode_summary:

        return "PROVISIONED"

    billing_mode = (
        billing_mode_summary.get(
            "BillingMode"
        )
    )

    return (
        billing_mode
        if billing_mode
        else "PROVISIONED"
    )


def get_table_environment(
    table_details,
    tags
):

    """
    Identify environment from table tags/name.

    This is informational only. The primary
    policy decision is based on activity.
    """

    text_parts = [
        table_details.get(
            "TableName",
            ""
        )
    ]

    for key, value in tags.items():

        text_parts.append(
            str(key)
        )

        text_parts.append(
            str(value)
        )

    text = " ".join(
        text_parts
    ).lower()

    if "production" in text:
        return "Production"

    if "prod" in text:
        return "Production"

    if "non-production" in text:
        return "Non-Production"

    if "nonprod" in text:
        return "Non-Production"

    if "dev" in text:
        return "Non-Production"

    if "test" in text:
        return "Non-Production"

    if "qa" in text:
        return "Non-Production"

    if "stage" in text:
        return "Non-Production"

    if "staging" in text:
        return "Non-Production"

    return "Unknown"


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_table(
    dynamodb,
    cloudwatch,
    table_name,
    account_id,
    region
):

    # --------------------------------------------------------
    # Fetch table details
    # --------------------------------------------------------

    table_details = fetch_table_details(
        dynamodb,
        table_name
    )

    table_arn = table_details.get(
        "TableArn"
    )

    table_status = table_details.get(
        "TableStatus"
    )

    creation_time = table_details.get(
        "CreationDateTime"
    )

    item_count = table_details.get(
        "ItemCount"
    )

    table_size_bytes = table_details.get(
        "TableSizeBytes"
    )

    billing_mode = get_billing_mode(
        table_details
    )

    provisioned_throughput = (
        table_details.get(
            "ProvisionedThroughput",
            {}
        )
    )

    read_capacity = (
        provisioned_throughput.get(
            "ReadCapacityUnits"
        )
    )

    write_capacity = (
        provisioned_throughput.get(
            "WriteCapacityUnits"
        )
    )

    # --------------------------------------------------------
    # Fetch tags
    # --------------------------------------------------------

    tags = {}

    if table_arn:

        tags = get_table_tags(
            dynamodb,
            table_arn
        )

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    environment = get_table_environment(
        table_details,
        tags
    )

    # --------------------------------------------------------
    # Fetch CloudWatch activity
    # --------------------------------------------------------

    activity = get_table_activity(
        cloudwatch,
        table_name
    )

    if not activity[
        "available"
    ]:

        return {
            "candidate": False,
            "reason": (
                "CloudWatch consumed capacity "
                "metrics are not available."
            ),
            "account_id": account_id,
            "region": region,
            "table_name": table_name,
            "table_arn": table_arn,
            "table_status": table_status,
            "creation_time": creation_time,
            "item_count": item_count,
            "table_size_bytes": table_size_bytes,
            "billing_mode": billing_mode,
            "read_capacity": read_capacity,
            "write_capacity": write_capacity,
            "environment": environment,
            "tags": tags,
            "activity": activity
        }

    read_units = activity[
        "read_units"
    ]

    write_units = activity[
        "write_units"
    ]

    total_units = activity[
        "total_units"
    ]

    # --------------------------------------------------------
    # Evaluate low activity
    # --------------------------------------------------------

    if total_units <= LOW_ACTIVITY_THRESHOLD:

        candidate = True

        reason = (
            f"Very low/zero DynamoDB activity "
            f"observed over the last "
            f"{ACTIVITY_LOOKBACK_DAYS} days."
        )

    else:

        candidate = False

        reason = (
            f"Table consumed "
            f"{total_units:.2f} capacity units "
            f"over the last "
            f"{ACTIVITY_LOOKBACK_DAYS} days."
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    if candidate:

        recommendation = (
            "Review the table with the application "
            "owner. If the table is no longer required, "
            "take an appropriate backup/export and "
            "delete the table. If the table is required "
            "but has very low activity, evaluate whether "
            "its current capacity/billing configuration "
            "should be changed."
        )

    else:

        recommendation = (
            "No low-activity optimization candidate "
            "identified based on the configured "
            "threshold."
        )

    return {
        "candidate": candidate,
        "reason": reason,
        "recommendation": recommendation,
        "account_id": account_id,
        "region": region,
        "table_name": table_name,
        "table_arn": table_arn,
        "table_status": table_status,
        "creation_time": creation_time,
        "item_count": item_count,
        "table_size_bytes": table_size_bytes,
        "billing_mode": billing_mode,
        "read_capacity": read_capacity,
        "write_capacity": write_capacity,
        "environment": environment,
        "tags": tags,
        "activity": activity
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

    table_name = evaluation[
        "table_name"
    ]

    table_arn = evaluation[
        "table_arn"
    ]

    table_status = evaluation[
        "table_status"
    ]

    creation_time = evaluation[
        "creation_time"
    ]

    item_count = evaluation[
        "item_count"
    ]

    table_size_bytes = evaluation[
        "table_size_bytes"
    ]

    billing_mode = evaluation[
        "billing_mode"
    ]

    read_capacity = evaluation[
        "read_capacity"
    ]

    write_capacity = evaluation[
        "write_capacity"
    ]

    environment = evaluation[
        "environment"
    ]

    tags = evaluation[
        "tags"
    ]

    activity = evaluation[
        "activity"
    ]

    candidate = evaluation[
        "candidate"
    ]

    recommendation = evaluation[
        "recommendation"
    ]

    reason = evaluation[
        "reason"
    ]

    # --------------------------------------------------------
    # Activity values
    # --------------------------------------------------------

    read_units = activity[
        "read_units"
    ]

    write_units = activity[
        "write_units"
    ]

    total_units = activity[
        "total_units"
    ]

    read_datapoints = activity[
        "read_datapoints"
    ]

    write_datapoints = activity[
        "write_datapoints"
    ]

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    created_date_text = ""

    if creation_time:

        created_date_text = (
            creation_time.strftime(
                "%d-%m-%Y"
            )
        )

    # --------------------------------------------------------
    # Table size
    # --------------------------------------------------------

    table_size_gb = None

    if table_size_bytes is not None:

        table_size_gb = (
            table_size_bytes /
            (
                1024 ** 3
            )
        )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (
        f"TableStatus: {table_status} | "
        f"CreatedDate: {created_date_text} | "
        f"AgeDays: "
        f"{calculate_age_days(creation_time)} | "
        f"BillingMode: {billing_mode} | "
        f"ProvisionedReadCapacity: "
        f"{read_capacity} | "
        f"ProvisionedWriteCapacity: "
        f"{write_capacity} | "
        f"ItemCount: {item_count} | "
        f"TableSizeGB: "
        f"{table_size_gb:.4f} "
        f"if table_size_gb is not None "
        f"else 'Unknown' | "
        f"ActivityWindowDays: "
        f"{ACTIVITY_LOOKBACK_DAYS} | "
        f"ConsumedReadCapacityUnits: "
        f"{read_units:.2f} | "
        f"ConsumedWriteCapacityUnits: "
        f"{write_units:.2f} | "
        f"TotalConsumedCapacityUnits: "
        f"{total_units:.2f} | "
        f"ReadMetricDatapoints: "
        f"{read_datapoints} | "
        f"WriteMetricDatapoints: "
        f"{write_datapoints} | "
        f"Environment: {environment} | "
        f"TableArn: {table_arn} | "
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
        "resourceNameOrId": table_name,
        "resourceId": table_name,
        "resourceArn": "",
        "service": SERVICE,
        "type": "DynamoDB Table",
        "policy": POLICY_TITLE,
        "effortLevel": "Medium",
        "message": "DynamoDB table has very low activity.",
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

def calculate_age_days(
    creation_time
):

    if not creation_time:

        return None

    if creation_time.tzinfo is None:

        creation_time = creation_time.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(
        timezone.utc
    )

    return (
        now - creation_time
    ).days


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
        f"Activity Lookback: "
        f"{ACTIVITY_LOOKBACK_DAYS} days"
    )

    print(
        f"Low Activity Threshold: "
        f"{LOW_ACTIVITY_THRESHOLD}"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        dynamodb,
        cloudwatch,
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
    # Fetch tables
    # --------------------------------------------------------

    print(
        "Fetching DynamoDB tables..."
    )

    tables = fetch_all_dynamodb_tables(
        dynamodb
    )

    print(
        f"DynamoDB tables scanned: "
        f"{len(tables)}"
    )

    # --------------------------------------------------------
    # Evaluate tables
    # --------------------------------------------------------

    findings = []

    candidate_count = 0

    metric_missing_count = 0

    for table_name in tables:

        print(
            f"Evaluating: {table_name}"
        )

        evaluation = evaluate_table(
            dynamodb,
            cloudwatch,
            table_name,
            account_id,
            REGION
        )

        if not evaluation:

            continue

        if not evaluation[
            "activity"
        ][
            "available"
        ]:

            metric_missing_count += 1

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
        f"Account ID             : "
        f"{account_id}"
    )

    print(
        f"Region                 : "
        f"{REGION}"
    )

    print(
        f"DynamoDB Tables Scanned: "
        f"{len(tables)}"
    )

    print(
        f"FinOps Candidates      : "
        f"{candidate_count}"
    )

    print(
        f"Missing CloudWatch     : "
        f"{metric_missing_count}"
    )

    print(
        f"Scan Duration          : "
        f"{scan_duration:.2f} seconds"
    )

    print(
        f"Excel Output           : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()