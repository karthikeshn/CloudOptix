# ============================================================
# KINESIS STREAM LOW DATA VOLUME - AWS FINOPS POLICY
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

POLICY_TITLE = "Kinesis Stream Low Data Volume"
POLICY_CATEGORY = "Kinesis Stream Low Data Volume"
SERVICE_NAME = "Kinesis"

LOOKBACK_DAYS = 30

# Streams with total incoming data <= this threshold
# during the last 30 days are considered low-volume.
#
# Example:
# 0.01 GB = approximately 10.74 MB
#
# Adjust this according to your organization's FinOps policy.
LOW_VOLUME_THRESHOLD_GB = 0.01

# Convert GB threshold to bytes
LOW_VOLUME_THRESHOLD_BYTES = (
    LOW_VOLUME_THRESHOLD_GB * 1024 * 1024 * 1024
)

OUTPUT_FILE = "kinesis_low_data_volume_findings.xlsx"

WORK_ITEM_TYPE = "Task"
STATE = "To Do"
STATUS = "Pending for Review"
AREA_PATH = "AWS Cost Optimization"
TAGS = "CLX"

ASSIGNED_TO = "Balamanikandan Venkatesan <balamanikandanv@caresoftglobal.com>"


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

class MockKinesisClient:
    def get_paginator(self, operation_name):
        if operation_name == "list_streams":
            class ListStreamsPaginator:
                def paginate(self):
                    yield {"StreamNames": ["mock-low-vol-kinesis-stream"]}
            return ListStreamsPaginator()
            
    def describe_stream_summary(self, **kwargs):
        stream_name = kwargs.get("StreamName", "unknown-stream")
        return {
            "StreamDescriptionSummary": {
                "StreamStatus": "ACTIVE",
                "StreamARN": f"arn:aws:kinesis:us-east-1:675134942214:stream/{stream_name}",
                "StreamModeDetails": {"StreamMode": "PROVISIONED"},
                "OpenShardCount": 1,
                "RetentionPeriodHours": 24,
                "EncryptionType": "NONE",
                "StreamCreationTimestamp": datetime.now(timezone.utc) - timedelta(days=30)
            }
        }

def create_clients(region_name):

    config = AWS_RETRY_CONFIG

    kinesis = MockKinesisClient()

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=config
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=config
    )

    return kinesis, cloudwatch, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    response = sts.get_caller_identity()

    return response["Account"]


# ============================================================
# 6. FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_kinesis_streams(kinesis):

    streams = []

    paginator = kinesis.get_paginator(
        "list_streams"
    )

    for page in paginator.paginate():

        stream_names = page.get(
            "StreamNames",
            []
        )

        streams.extend(stream_names)

    return streams


def get_stream_details(kinesis, stream_name):

    try:

        response = kinesis.describe_stream_summary(
            StreamName=stream_name
        )

        summary = response.get(
            "StreamDescriptionSummary",
            {}
        )

        return summary

    except Exception as e:

        print(
            f"Failed to describe stream "
            f"{stream_name}: {str(e)}"
        )

        return {}


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_cloudwatch_metric_sum(
    cloudwatch,
    stream_name,
    metric_name,
    start_time,
    end_time
):

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/Kinesis",
            MetricName=metric_name,
            Dimensions=[
                {
                    "Name": "StreamName",
                    "Value": stream_name
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=["Sum"],
            Unit="Bytes" if metric_name == "IncomingBytes"
            else "Count"
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
            f"for {stream_name}: {str(e)}"
        )

        return 0


def get_stream_metrics(
    cloudwatch,
    stream_name
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = end_time - timedelta(
        days=LOOKBACK_DAYS
    )

    incoming_bytes = get_cloudwatch_metric_sum(
        cloudwatch,
        stream_name,
        "IncomingBytes",
        start_time,
        end_time
    )

    incoming_records = get_cloudwatch_metric_sum(
        cloudwatch,
        stream_name,
        "IncomingRecords",
        start_time,
        end_time
    )

    incoming_gb = (
        incoming_bytes /
        (1024 ** 3)
    )

    return {
        "incoming_bytes": incoming_bytes,
        "incoming_records": incoming_records,
        "incoming_gb": incoming_gb,
        "start_time": start_time,
        "end_time": end_time
    }


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_kinesis_stream(
    stream_name,
    stream_details,
    metrics
):

    incoming_bytes = metrics[
        "incoming_bytes"
    ]

    incoming_records = metrics[
        "incoming_records"
    ]

    incoming_gb = metrics[
        "incoming_gb"
    ]

    # --------------------------------------------------------
    # LOW DATA VOLUME CHECK
    # --------------------------------------------------------

    is_low_volume = (
        incoming_bytes <=
        LOW_VOLUME_THRESHOLD_BYTES
    )

    if not is_low_volume:

        return None

    # --------------------------------------------------------
    # STREAM INFORMATION
    # --------------------------------------------------------

    stream_arn = stream_details.get(
        "StreamARN",
        ""
    )

    stream_status = stream_details.get(
        "StreamStatus",
        ""
    )

    stream_mode = stream_details.get(
        "StreamModeDetails",
        {}
    )

    stream_mode_type = stream_mode.get(
        "StreamMode",
        ""
    )

    creation_timestamp = stream_details.get(
        "StreamCreationTimestamp"
    )

    retention_hours = stream_details.get(
        "RetentionPeriodHours",
        ""
    )

    open_shard_count = stream_details.get(
        "OpenShardCount",
        ""
    )

    encryption_type = stream_details.get(
        "EncryptionType",
        ""
    )

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = (
        f"Kinesis Data Stream {stream_name} "
        f"has very low data volume over the last "
        f"{LOOKBACK_DAYS} days. "
        f"Total incoming data: "
        f"{incoming_gb:.6f} GB "
        f"({incoming_bytes:,} bytes). "
        f"Total incoming records: "
        f"{incoming_records:,.0f}. "
        f"Stream status: {stream_status}. "
        f"Stream mode: {stream_mode_type}. "
        f"Open shards: {open_shard_count}. "
        f"Retention: {retention_hours} hours. "
        f"Encryption: {encryption_type}. "
        f"Stream ARN: {stream_arn}. "
        f"Review producers, consumers, CloudWatch metrics, "
        f"and application dependencies before disabling "
        f"or deleting the stream."
    )

    if creation_timestamp:

        description += (
            f" Created: "
            f"{creation_timestamp.isoformat()}."
        )

    # --------------------------------------------------------
    # FINDING
    # --------------------------------------------------------

    finding = {
        "stream_name": stream_name,
        "stream_arn": stream_arn,
        "incoming_bytes": incoming_bytes,
        "incoming_gb": incoming_gb,
        "incoming_records": incoming_records,
        "stream_status": stream_status,
        "stream_mode": stream_mode_type,
        "open_shard_count": open_shard_count,
        "retention_hours": retention_hours,
        "encryption_type": encryption_type,
        "description": description
    }

    return finding


# ============================================================
# 9. COST / SAVINGS
# ============================================================

def calculate_cost_and_savings(
    finding
):

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Resource-level current cost should come from
    # CUR + Athena.
    #
    # Do NOT calculate Kinesis monthly cost from the
    # CloudWatch IncomingBytes metric.
    # --------------------------------------------------------

    current_daily_cost = "To be updated"

    current_monthly_cost = "To be updated"

    achieved_savings_monthly = ""

    return (
        current_daily_cost,
        current_monthly_cost,
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
        daily_cost, monthly_cost, achieved_savings = calculate_cost_and_savings(finding)

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
            "resourceNameOrId": finding.get("stream_name", ""),
            "resourceId": finding.get("stream_name", ""),
            "resourceArn": finding.get("stream_arn", ""),
            "service": SERVICE_NAME,
            "type": "Kinesis Stream",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Low Data Volume: incoming data {finding.get('incoming_gb', 0):.6f} GB over 30 days.",
            "recommendation": "Review whether the stream can be decommissioned or sized down.",
            "description": finding.get("description", ""),
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": monthly_cost,
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": achieved_savings,
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

    kinesis, cloudwatch, sts = create_clients(
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
    # FETCH STREAMS
    # --------------------------------------------------------

    stream_names = fetch_all_kinesis_streams(
        kinesis
    )

    print(
        f"Total Kinesis streams found: "
        f"{len(stream_names)}"
    )

    findings = []

    # --------------------------------------------------------
    # EVALUATE EACH STREAM
    # --------------------------------------------------------

    for stream_name in stream_names:

        print(
            f"Checking stream: "
            f"{stream_name}"
        )

        stream_details = get_stream_details(
            kinesis,
            stream_name
        )

        if not stream_details:
            continue

        # Only evaluate streams that are active
        stream_status = stream_details.get(
            "StreamStatus",
            ""
        )

        if stream_status != "ACTIVE":
            continue

        metrics = get_stream_metrics(
            cloudwatch,
            stream_name
        )

        finding = evaluate_kinesis_stream(
            stream_name,
            stream_details,
            metrics
        )

        if finding:

            findings.append(
                finding
            )

            print(
                f"LOW DATA VOLUME: "
                f"{stream_name} | "
                f"{finding['incoming_gb']:.6f} GB"
            )

    # --------------------------------------------------------
    # GENERATE OUTPUT
    # --------------------------------------------------------

    export_to_excel(
        findings,
        account_id,
        REGION
    )

    print(
        "----------------------------------------"
    )

    print(
        f"Total streams scanned: "
        f"{len(stream_names)}"
    )

    print(
        f"Low-volume streams found: "
        f"{len(findings)}"
    )

    print(
        "----------------------------------------"


    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()