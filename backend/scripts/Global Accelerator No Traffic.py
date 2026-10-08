# ============================================================
# AWS FINOPS POLICY
# Global Accelerator No Traffic
#
# Policy:
# Identify AWS Global Accelerators that have received
# zero new flows during the configured lookback period.
#
# Recommended action:
# Review and disable/delete the accelerator after approval
# and during an appropriate maintenance/downtime window.
# ============================================================


# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import io
import logging
import time
import pandas as pd

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2. AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

# Global Accelerator CloudWatch metrics are available
# through US West (Oregon).
GLOBAL_ACCELERATOR_METRICS_REGION = "us-west-2"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

# Output file
OUTPUT_FILE = "global_accelerator_no_traffic.xlsx"

# Policy lookback period
LOOKBACK_DAYS = 30

# CloudWatch metric configuration
CLOUDWATCH_NAMESPACE = "AWS/GlobalAccelerator"
TRAFFIC_METRIC_NAME = "NewFlowCount"

# CloudWatch period.
# One hour gives a reasonable balance between API calls
# and sufficient traffic visibility for a 30-day policy.
CLOUDWATCH_PERIOD_SECONDS = 3600

# Global Accelerator standard accelerator approximate
# fixed hourly accelerator charge.
#
# This is NOT used as the authoritative current cost.
# Current cost should come from CUR + Athena.
ESTIMATED_ACCELERATOR_HOURLY_COST = Decimal("0.025")


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Global Accelerator No Traffic"

POLICY_CATEGORY = "Global Accelerator No Traffic"

POLICY_SERVICE = "Global Accelerator"

POLICY_DESCRIPTION_TEMPLATE = (
    "Global Accelerator '{accelerator_name}' had "
    "{total_new_flows} new flows in the last {lookback_days} days. "
    "Disable or delete the accelerator to stop ongoing hourly fees. "
    "Estimated annual savings based on the accelerator hourly charge: "
    "~${estimated_annual_savings:.2f}."
)

# Policy condition
#
# Finding:
# NewFlowCount == 0 for the complete lookback period.
#
# Important:
# Global Accelerator does not publish zero-valued NewFlowCount
# datapoints. Therefore, no datapoints for this metric during
# the lookback period means no reported traffic.


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients required by the policy.
    """

    globalaccelerator = boto3.client(
        "globalaccelerator",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=GLOBAL_ACCELERATOR_METRICS_REGION,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return globalaccelerator, cloudwatch, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    response = sts.get_caller_identity()

    return response["Account"]


# ============================================================
# 6. FETCH ALL GLOBAL ACCELERATORS
# ============================================================

def fetch_all_global_accelerators(globalaccelerator):
    """
    Fetch all Global Accelerators using pagination.
    """

    accelerators = []

    try:

        paginator = globalaccelerator.get_paginator(
            "list_accelerators"
        )

        for page in paginator.paginate():

            page_accelerators = page.get(
                "Accelerators",
                []
            )

            accelerators.extend(page_accelerators)

    except ClientError as e:

        logging.error(
            "Failed to fetch Global Accelerators: %s",
            e
        )

    return accelerators


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_new_flow_count(
    cloudwatch,
    accelerator_id,
    start_time,
    end_time
):
    """
    Fetch total NewFlowCount for the accelerator.

    Global Accelerator publishes NewFlowCount only when
    the value is non-zero.

    Therefore:
        - datapoints returned -> traffic occurred
        - no datapoints       -> no reported traffic

    CloudWatch metrics for Global Accelerator must be queried
    from us-west-2.
    """
        
    total_new_flows = Decimal("0")

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricName=TRAFFIC_METRIC_NAME,
            Dimensions=[
                {
                    "Name": "Accelerator",
                    "Value": accelerator_id
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=CLOUDWATCH_PERIOD_SECONDS,
            Statistics=[
                "Sum"
            ],
            Unit="Count"
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        for datapoint in datapoints:

            value = datapoint.get(
                "Sum",
                0
            )

            total_new_flows += Decimal(
                str(value)
            )

    except ClientError as e:

        logging.error(
            "CloudWatch metric retrieval failed for "
            "accelerator %s: %s",
            accelerator_id,
            e
        )

        return None

    return total_new_flows


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_global_accelerator(
    accelerator,
    cloudwatch,
    lookback_days
):
    """
    Evaluate Global Accelerator against the
    No Traffic policy.
    """

    accelerator_id = accelerator.get(
        "AcceleratorId",
        ""
    )

    accelerator_name = accelerator.get(
        "Name",
        accelerator_id
    )

    accelerator_arn = accelerator.get(
        "AcceleratorArn",
        ""
    )

    status = accelerator.get(
        "Status",
        ""
    )

    enabled = accelerator.get(
        "Enabled",
        False
    )

    accelerator_type = accelerator.get(
        "Type",
        ""
    )

    created_time = accelerator.get(
        "CreatedTime"
    )

    last_modified_time = accelerator.get(
        "LastModifiedTime"
    )

    end_time = datetime.now(
        timezone.utc
    )

    start_time = end_time - timedelta(
        days=lookback_days
    )

    total_new_flows = get_new_flow_count(
        cloudwatch=cloudwatch,
        accelerator_id=accelerator_id,
        start_time=start_time,
        end_time=end_time
    )

    # None means metric retrieval failed.
    # Do NOT classify it as a FinOps finding.
    if total_new_flows is None:

        return {
            "is_finding": False,
            "metric_error": True,
            "accelerator_id": accelerator_id
        }

    # --------------------------------------------------------
    # POLICY CONDITION
    # --------------------------------------------------------

    is_no_traffic = (
        total_new_flows == Decimal("0")
    )

    if not is_no_traffic:

        return {
            "is_finding": False,
            "metric_error": False,
            "accelerator_id": accelerator_id,
            "accelerator_name": accelerator_name,
            "total_new_flows": total_new_flows
        }

    # --------------------------------------------------------
    # ESTIMATED SAVINGS
    # --------------------------------------------------------

    # Approximate fixed accelerator cost.
    #
    # This is only an estimate.
    # Authoritative cost should come from CUR + Athena.
    monthly_estimated_cost = (
        ESTIMATED_ACCELERATOR_HOURLY_COST
        * Decimal("24")
        * Decimal(str(30))
    )

    annual_estimated_savings = (
        ESTIMATED_ACCELERATOR_HOURLY_COST
        * Decimal("24")
        * Decimal("365")
    )

    description = POLICY_DESCRIPTION_TEMPLATE.format(
        accelerator_name=accelerator_name,
        total_new_flows=total_new_flows,
        lookback_days=lookback_days,
        estimated_annual_savings=float(
            annual_estimated_savings
        )
    )

    return {
        "is_finding": True,
        "metric_error": False,

        "accelerator_id": accelerator_id,
        "accelerator_name": accelerator_name,
        "accelerator_arn": accelerator_arn,

        "status": status,
        "enabled": enabled,
        "accelerator_type": accelerator_type,

        "created_time": created_time,
        "last_modified_time": last_modified_time,

        "lookback_days": lookback_days,
        "start_time": start_time,
        "end_time": end_time,

        "total_new_flows": total_new_flows,

        "estimated_monthly_savings":
            monthly_estimated_cost,

        "estimated_annual_savings":
            annual_estimated_savings,

        "description": description
    }


# ============================================================
# 9. COST / SAVINGS
# ============================================================

def get_cur_athena_cost(
    athena,
    database,
    output_location,
    table_name,
    accelerator_arn,
    start_date,
    end_date
):
    """
    Retrieve resource-level cost using CUR + Athena.

    IMPORTANT:
    CUR schemas differ between environments.
    The query below assumes the standard CUR columns:

        line_item_resource_id
        line_item_unblended_cost
        line_item_usage_start_date

    Global Accelerator resource-level billing may not always
    expose the accelerator ARN in line_item_resource_id.

    If CUR does not contain the resource ARN, this function
    returns None rather than inventing a cost.
    """

    query = f"""
    SELECT
        SUM(line_item_unblended_cost) AS total_cost
    FROM {table_name}
    WHERE
        line_item_usage_start_date >= DATE '{start_date}'
        AND line_item_usage_start_date < DATE '{end_date}'
        AND line_item_resource_id = '{accelerator_arn}'
    """

    try:

        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={
                "Database": database
            },
            ResultConfiguration={
                "OutputLocation": output_location
            }
        )

        query_execution_id = response[
            "QueryExecutionId"
        ]

        # Wait for Athena
        while True:

            query_status = athena.get_query_execution(
                QueryExecutionId=query_execution_id
            )

            state = query_status[
                "QueryExecution"
            ][
                "Status"
            ][
                "State"
            ]

            if state in [
                "SUCCEEDED",
                "FAILED",
                "CANCELLED"
            ]:
                break

            time.sleep(2)

        if state != "SUCCEEDED":

            logging.warning(
                "Athena query failed for %s",
                accelerator_arn
            )

            return None

        result = athena.get_query_results(
            QueryExecutionId=query_execution_id
        )

        rows = result.get(
            "ResultSet",
            {}
        ).get(
            "Rows",
            []
        )

        if len(rows) < 2:
            return None

        value = rows[1].get(
            "Data",
            [{}]
        )[0].get(
            "VarCharValue"
        )

        if value is None:
            return None

        return Decimal(value)

    except ClientError as e:

        logging.error(
            "CUR/Athena cost retrieval failed: %s",
            e
        )

        return None


# ============================================================
# 10. GENERATE EXCEL / CSV OUTPUT
# ============================================================

def export_to_excel(
    findings,
    account_id,
    region
):
    """
    Export findings using the exact fixed 30-column schema.
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

    rows = []

    for finding in findings:
        monthly_cost = finding.get("cur_monthly_cost")

        if monthly_cost is not None:
            daily_cost = monthly_cost / Decimal("30")
        else:
            daily_cost = ESTIMATED_ACCELERATOR_HOURLY_COST * Decimal("24")

        monthly_savings = finding.get("estimated_monthly_savings", Decimal("0"))

        rows.append({
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": "Pending for Review",
            "areaPath": "AWS Cost Optimization",
            "tags": "",
            "commentCount": 0,
            "accountId": account_id,
            "region": region,
            "resourceNameOrId": finding.get("accelerator_name"),
            "resourceId": finding.get("accelerator_id"),
            "resourceArn": finding.get("accelerator_arn"),
            "service": POLICY_SERVICE,
            "type": "Global Accelerator",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Global Accelerator '{finding.get('accelerator_name')}' had zero new flows in the last {LOOKBACK_DAYS} days.",
            "recommendation": "Review and disable/delete the accelerator after approval and during an appropriate maintenance/downtime window.",
            "description": finding.get("description", ""),
            "currentDailyCost": round(float(daily_cost), 4) if daily_cost is not None else "To be updated",
            "currentMonthlyCost": round(float(monthly_cost), 2) if monthly_cost is not None else "To be updated",
            "estimatedMonthlySavings": round(float(monthly_savings), 2),
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": "",
            "month": ""
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(OUTPUT_FILE, index=False)
    
    logging.info("Excel report generated: %s", OUTPUT_FILE)


# ============================================================
# MAIN
# ============================================================

def main():

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - "
            "%(levelname)s - "
            "%(message)s"
        )
    )

    scan_start = time.time()

    logging.info(
        "Starting policy: %s",
        POLICY_TITLE
    )

    # --------------------------------------------------------
    # CREATE CLIENTS
    # --------------------------------------------------------

    (
        globalaccelerator,
        cloudwatch,
        sts
    ) = create_clients(
        AWS_REGION
    )

    # --------------------------------------------------------
    # ACCOUNT ID
    # --------------------------------------------------------

    account_id = get_account_id(sts)

    logging.info(
        "Account ID: %s",
        account_id
    )

    # --------------------------------------------------------
    # FETCH ALL GLOBAL ACCELERATORS
    # --------------------------------------------------------

    accelerators = (
        fetch_all_global_accelerators(
            globalaccelerator
        )
    )

    logging.info(
        "Total Global Accelerators scanned: %d",
        len(accelerators)
    )

    # --------------------------------------------------------
    # EVALUATE EACH ACCELERATOR
    # --------------------------------------------------------

    findings = []

    for accelerator in accelerators:

        accelerator_id = accelerator.get(
            "AcceleratorId",
            ""
        )

        accelerator_name = accelerator.get(
            "Name",
            accelerator_id
        )

        logging.info(
            "Evaluating accelerator: %s (%s)",
            accelerator_name,
            accelerator_id
        )

        result = evaluate_global_accelerator(
            accelerator=accelerator,
            cloudwatch=cloudwatch,
            lookback_days=LOOKBACK_DAYS
        )

        # Metric retrieval failure
        if result.get(
            "metric_error",
            False
        ):

            logging.warning(
                "Metric retrieval failed for %s. "
                "Skipping finding.",
                accelerator_name
            )

            continue

        # No finding
        if not result.get(
            "is_finding",
            False
        ):

            logging.info(
                "Traffic detected for %s. "
                "No finding.",
                accelerator_name
            )

            continue

        # ----------------------------------------------------
        # FINDING
        # ----------------------------------------------------

        logging.info(
            "FINDING: %s has zero new flows "
            "for the last %d days.",
            accelerator_name,
            LOOKBACK_DAYS
        )

        findings.append(
            result
        )

    # --------------------------------------------------------
    # CREATE OUTPUT
    # --------------------------------------------------------

    export_to_excel(
        findings=findings,
        account_id=account_id,
        region=AWS_REGION
    )

    # --------------------------------------------------------
    # SCAN SUMMARY
    # --------------------------------------------------------

    scan_duration = (
        time.time() -
        scan_start
    )

    logging.info(
        "=================================================="
    )

    logging.info(
        "Policy: %s",
        POLICY_TITLE
    )

    logging.info(
        "Account ID: %s",
        account_id
    )

    logging.info(
        "Region: %s",
        AWS_REGION
    )

    logging.info(
        "Global Accelerators scanned: %d",
        len(accelerators)
    )

    logging.info(
        "No Traffic findings: %d",
        len(findings)
    )

    logging.info(
        "Lookback period: %d days",
        LOOKBACK_DAYS
    )

    logging.info(
        "Scan duration: %.2f seconds",
        scan_duration
    )
    logging.info(
        "Output: %s",
        OUTPUT_FILE
    )

    logging.info(
        "=================================================="
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()