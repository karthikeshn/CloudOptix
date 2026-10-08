# ============================================================
# AWS FinOps Policy: Idle Kinesis Stream
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd

from datetime import datetime, timedelta, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

OUTPUT_FILE = "idle_kinesis_stream.xlsx"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

# Number of days used to determine inactivity
LOOKBACK_DAYS = 7


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

POLICY_TITLE = "Idle Kinesis Stream"

POLICY_CATEGORY = "Idle Kinesis Stream"

POLICY_SERVICE = "Kinesis"

POLICY_TAG = "CLX"

POLICY_AREA_PATH = "AWS Cost Optimization"

POLICY_STATUS = "Pending for Review"


# CloudWatch metrics used to determine Kinesis activity
KINESIS_METRICS = [
    "IncomingRecords",
    "IncomingBytes",
    "GetRecords.Records",
    "GetRecords.Bytes"
]


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

class MockKinesisClient:
    def get_paginator(self, operation_name):
        if operation_name == "list_streams":
            class ListStreamsPaginator:
                def paginate(self):
                    yield {"StreamNames": ["mock-idle-kinesis-stream"]}
            return ListStreamsPaginator()
            
    def describe_stream_summary(self, **kwargs):
        stream_name = kwargs.get("StreamName", "unknown-stream")
        return {
            "StreamDescriptionSummary": {
                "StreamStatus": "ACTIVE",
                "OpenShardCount": 1,
                "StreamARN": f"arn:aws:kinesis:us-east-1:675134942214:stream/{stream_name}",
                "StreamCreationTimestamp": datetime.now(timezone.utc) - timedelta(days=30)
            }
        }

def create_clients(region_name):

    kinesis = MockKinesisClient()

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return kinesis, cloudwatch, sts


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_kinesis_streams(kinesis):

    streams = []

    try:

        paginator = kinesis.get_paginator(
            "list_streams"
        )

        for page in paginator.paginate():

            streams.extend(
                page.get(
                    "StreamNames",
                    []
                )
            )

    except ClientError as e:

        logger.error(
            "Failed to fetch Kinesis streams: %s",
            e
        )

    logger.info(
        "Total Kinesis streams discovered: %d",
        len(streams)
    )

    return streams


def get_stream_summary(
    kinesis,
    stream_name
):

    try:

        response = kinesis.describe_stream_summary(
            StreamName=stream_name
        )

        return response.get(
            "StreamDescriptionSummary",
            {}
        )

    except ClientError as e:

        logger.warning(
            "Unable to describe Kinesis stream %s: %s",
            stream_name,
            e
        )

        return {}


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_metric_sum(
    cloudwatch,
    stream_name,
    metric_name,
    start_time,
    end_time
):

    """
    Fetch the total value of a Kinesis CloudWatch metric
    over the configured lookback period.
    """

    total_value = 0.0

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

            Statistics=[
                "Sum"
            ]
        )

        for datapoint in response.get(
            "Datapoints",
            []
        ):

            total_value += datapoint.get(
                "Sum",
                0
            )

    except ClientError as e:

        logger.warning(
            "Unable to fetch metric %s for stream %s: %s",
            metric_name,
            stream_name,
            e
        )

    return total_value


def fetch_kinesis_metrics(
    cloudwatch,
    stream_name
):

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    metrics = {}

    for metric_name in KINESIS_METRICS:

        metrics[metric_name] = get_metric_sum(

            cloudwatch=cloudwatch,

            stream_name=stream_name,

            metric_name=metric_name,

            start_time=start_time,

            end_time=end_time
        )

    return metrics


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_stream(
    kinesis,
    cloudwatch,
    stream_name,
    account_id,
    region_name
):

    # --------------------------------------------------------
    # Get stream information
    # --------------------------------------------------------

    stream_summary = get_stream_summary(
        kinesis,
        stream_name
    )

    if not stream_summary:

        return None

    stream_status = stream_summary.get(
        "StreamStatus"
    )

    shard_count = stream_summary.get(
        "OpenShardCount",
        0
    )

    stream_arn = stream_summary.get(
        "StreamARN",
        ""
    )

    stream_creation_timestamp = (
        stream_summary.get(
            "StreamCreationTimestamp"
        )
    )

    # --------------------------------------------------------
    # Only evaluate active streams
    # --------------------------------------------------------

    if stream_status != "ACTIVE":

        logger.info(
            "Skipping stream %s because status is %s",
            stream_name,
            stream_status
        )

        return None

    # --------------------------------------------------------
    # A stream with no shards cannot be treated as an
    # idle provisioned stream.
    # --------------------------------------------------------

    if shard_count <= 0:

        logger.info(
            "Skipping stream %s because shard count is %d",
            stream_name,
            shard_count
        )

        return None

    # --------------------------------------------------------
    # Fetch CloudWatch activity
    # --------------------------------------------------------

    metrics = fetch_kinesis_metrics(

        cloudwatch=cloudwatch,

        stream_name=stream_name
    )

    incoming_records = metrics.get(
        "IncomingRecords",
        0
    )

    incoming_bytes = metrics.get(
        "IncomingBytes",
        0
    )

    get_records = metrics.get(
        "GetRecords.Records",
        0
    )

    get_records_bytes = metrics.get(
        "GetRecords.Bytes",
        0
    )

    # --------------------------------------------------------
    # Determine whether the stream is idle
    # --------------------------------------------------------

    no_incoming_activity = (
        incoming_records == 0
        and
        incoming_bytes == 0
    )

    no_read_activity = (
        get_records == 0
        and
        get_records_bytes == 0
    )

    is_idle = (
        no_incoming_activity
        and
        no_read_activity
    )

    logger.info(
        "Stream: %s | Shards: %d | "
        "IncomingRecords: %.0f | "
        "IncomingBytes: %.0f | "
        "GetRecords: %.0f | "
        "GetRecordsBytes: %.0f | "
        "Idle: %s",
        stream_name,
        shard_count,
        incoming_records,
        incoming_bytes,
        get_records,
        get_records_bytes,
        is_idle
    )

    # --------------------------------------------------------
    # If there is activity, do not create finding
    # --------------------------------------------------------

    if not is_idle:

        return None

    # --------------------------------------------------------
    # Creation age
    # --------------------------------------------------------

    age_days = ""

    if stream_creation_timestamp:

        age_days = (
            datetime.now(
                timezone.utc
            ) -
            stream_creation_timestamp
        ).days

    # --------------------------------------------------------
    # Build description
    # --------------------------------------------------------

    description = (

        f"Amazon Kinesis Data Stream "
        f"'{stream_name}' has {shard_count} "
        f"open shard(s) and no detected incoming "
        f"or read activity during the last "
        f"{LOOKBACK_DAYS} days. "

        f"IncomingRecords: {incoming_records:.0f}. "

        f"IncomingBytes: {incoming_bytes:.0f}. "

        f"GetRecords.Records: {get_records:.0f}. "

        f"GetRecords.Bytes: {get_records_bytes:.0f}. "

        f"Stream age: {age_days} days. "

        f"Recommendation: review whether the stream "
        f"is still required. If confirmed unused, "
        f"delete the stream or otherwise reduce its "
        f"provisioned shard capacity."
    )

    # --------------------------------------------------------
    # Finding
    # --------------------------------------------------------

    finding = {

        "account_id":
            account_id,

        "region":
            region_name,

        "resource_id":
            stream_name,

        "stream_arn":
            stream_arn,

        "stream_name":
            stream_name,

        "stream_status":
            stream_status,

        "shard_count":
            shard_count,

        "incoming_records":
            incoming_records,

        "incoming_bytes":
            incoming_bytes,

        "get_records":
            get_records,

        "get_records_bytes":
            get_records_bytes,

        "age_days":
            age_days,

        "description":
            description
    }

    return finding


def evaluate_policy(
    kinesis,
    cloudwatch,
    account_id,
    region_name
):

    # --------------------------------------------------------
    # Fetch all streams
    # --------------------------------------------------------

    streams = fetch_all_kinesis_streams(
        kinesis
    )

    findings = []

    # --------------------------------------------------------
    # Evaluate every stream
    # --------------------------------------------------------

    for stream_name in streams:

        finding = evaluate_stream(

            kinesis=kinesis,

            cloudwatch=cloudwatch,

            stream_name=stream_name,

            account_id=account_id,

            region_name=region_name
        )

        if finding:

            findings.append(
                finding
            )

    return findings


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_id,
    account_id,
    region_name
):

    """
    Current Kinesis cost should come from
    CUR + Athena.

    The primary provisioned cost driver for the
    traditional Kinesis Data Stream model is the
    provisioned shard capacity.

    Do not calculate the final financial value only
    from the number of shards because pricing can vary
    by Region and usage components.
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
    Potential savings should be populated using
    actual CUR + Athena cost data.

    Example:

        monthly stream cost
        =
        current monthly avoidable cost

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
            "resourceArn": finding.get("stream_arn", ""),
            "service": POLICY_SERVICE,
            "type": "Kinesis Stream",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Idle Kinesis Stream: '{resource_id}' has had no activity for {LOOKBACK_DAYS} days.",
            "recommendation": "Review whether the stream is still required. Delete or reduce provisioned shards if unused.",
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

    logger.info(
        "Lookback period: %d days",
        LOOKBACK_DAYS
    )

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    (
        kinesis,
        cloudwatch,
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
    # Evaluate policy
    # --------------------------------------------------------

    findings = evaluate_policy(

        kinesis=kinesis,

        cloudwatch=cloudwatch,

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
        "Idle Kinesis Stream Scan Completed"
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