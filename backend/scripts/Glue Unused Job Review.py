# ============================================================
# AWS FinOps Policy: Glue Unused Job Review
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

OUTPUT_FILE = "glue_unused_job_review.xlsx"

# Period over which Glue Job execution is evaluated
LOOKBACK_DAYS = 90

# Jobs whose total execution time is less than or equal to
# this threshold are considered low-usage candidates.
#
# 1 hour over 90 days is approximately 0.067%
# utilization of the 90-day period.
MAX_EXECUTION_HOURS = 1.0

# Boto3 retry configuration
BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# 3) FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Glue Unused Job Review"

POLICY_CATEGORY = "Glue Unused Job Review"

POLICY_SERVICE = "Glue"

POLICY_TAG = "Cloud Roar"

POLICY_DESCRIPTION = (
    "AWS Glue job '{job_name}' has very low execution time "
    f"over the last {LOOKBACK_DAYS} days. Review whether the "
    "job is still required. Unused Glue job definitions do "
    "not typically create direct idle charges, but removing "
    "stale jobs can reduce operational clutter and "
    "misconfiguration risk."
)


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients for the configured region.
    """

    glue = boto3.client(
        "glue",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return glue, sts


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

def fetch_all_glue_jobs(glue):
    """
    Fetch all Glue Jobs using pagination.
    """

    jobs = []

    paginator = glue.get_paginator(
        "get_jobs"
    )

    try:

        for page in paginator.paginate():

            page_jobs = page.get(
                "Jobs",
                []
            )

            jobs.extend(
                page_jobs
            )

    except ClientError as e:

        logger.error(
            "Failed to fetch Glue Jobs: %s",
            e
        )

    logger.info(
        "Total Glue Jobs fetched: %d",
        len(jobs)
    )

    return jobs


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_job_runs_in_period(
    glue,
    job_name,
    start_time,
    end_time
):
    """
    Fetch Glue Job Runs within the configured period.

    Glue returns job runs in reverse chronological order,
    so pagination can stop once runs older than start_time
    are reached.
    """

    runs = []

    paginator = glue.get_paginator(
        "get_job_runs"
    )

    try:

        for page in paginator.paginate(
            JobName=job_name
        ):

            page_runs = page.get(
                "JobRuns",
                []
            )

            for run in page_runs:

                started_on = run.get(
                    "StartedOn"
                )

                if not started_on:
                    continue

                if started_on.tzinfo is None:

                    started_on = started_on.replace(
                        tzinfo=timezone.utc
                    )

                # Job runs are returned newest first.
                if started_on < start_time:

                    return runs

                if started_on <= end_time:

                    runs.append(
                        run
                    )

    except ClientError as e:

        logger.error(
            "Failed to fetch Job Runs for '%s': %s",
            job_name,
            e
        )

    return runs


def get_glue_job_execution_metrics(
    glue,
    job_name
):
    """
    Calculate actual Glue Job execution statistics
    over the configured lookback period.

    ExecutionTime from Glue JobRun is used as the actual
    execution duration.

    Returns:
        total runs
        total execution seconds
        total execution hours
        successful runs
        failed runs
        stopped runs
        timeout runs
        last run information
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time -
        timedelta(
            days=LOOKBACK_DAYS
        )
    )

    runs = get_job_runs_in_period(
        glue,
        job_name,
        start_time,
        end_time
    )

    total_execution_seconds = 0

    successful_runs = 0
    failed_runs = 0
    stopped_runs = 0
    timeout_runs = 0
    error_runs = 0

    total_dpu_seconds = 0

    last_run_time = None
    last_run_state = None

    for run in runs:

        # ----------------------------------------------------
        # Execution time
        # ----------------------------------------------------

        execution_time = run.get(
            "ExecutionTime",
            0
        )

        if execution_time is None:
            execution_time = 0

        total_execution_seconds += (
            execution_time
        )

        # ----------------------------------------------------
        # DPU seconds
        # ----------------------------------------------------

        dpu_seconds = run.get(
            "DPUSeconds",
            0
        )

        if dpu_seconds is None:
            dpu_seconds = 0

        total_dpu_seconds += (
            dpu_seconds
        )

        # ----------------------------------------------------
        # Run state
        # ----------------------------------------------------

        state = run.get(
            "JobRunState"
        )

        if state == "SUCCEEDED":

            successful_runs += 1

        elif state == "FAILED":

            failed_runs += 1

        elif state == "STOPPED":

            stopped_runs += 1

        elif state == "TIMEOUT":

            timeout_runs += 1

        elif state == "ERROR":

            error_runs += 1

        # ----------------------------------------------------
        # Last run
        # ----------------------------------------------------

        started_on = run.get(
            "StartedOn"
        )

        if started_on:

            if (
                last_run_time is None
                or started_on > last_run_time
            ):

                last_run_time = started_on

                last_run_state = state

    total_execution_hours = (
        total_execution_seconds / 3600
    )

    return {
        "total_runs": len(runs),
        "total_execution_seconds":
            total_execution_seconds,
        "total_execution_hours":
            total_execution_hours,
        "successful_runs":
            successful_runs,
        "failed_runs":
            failed_runs,
        "stopped_runs":
            stopped_runs,
        "timeout_runs":
            timeout_runs,
        "error_runs":
            error_runs,
        "total_dpu_seconds":
            total_dpu_seconds,
        "last_run_time":
            last_run_time,
        "last_run_state":
            last_run_state
    }


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_glue_job(
    glue,
    job,
    account_id,
    region_name
):
    """
    Evaluate Glue Job for very low execution time.

    Candidate condition:

        Total execution hours over the last 90 days
        <= MAX_EXECUTION_HOURS

    Default:

        <= 1 hour over 90 days
    """

    job_name = job.get(
        "Name",
        ""
    )

    if not job_name:
        return None

    # --------------------------------------------------------
    # Get actual execution metrics
    # --------------------------------------------------------

    metrics = get_glue_job_execution_metrics(
        glue,
        job_name
    )

    total_execution_hours = metrics[
        "total_execution_hours"
    ]

    # --------------------------------------------------------
    # Job has meaningful execution activity
    # --------------------------------------------------------

    if total_execution_hours > MAX_EXECUTION_HOURS:

        return None

    # --------------------------------------------------------
    # Construct Job ARN
    # --------------------------------------------------------

    job_arn = (
        f"arn:aws:glue:{region_name}:"
        f"{account_id}:job/{job_name}"
    )

    # --------------------------------------------------------
    # Get Glue Job configuration
    # --------------------------------------------------------

    command = job.get(
        "Command",
        {}
    )

    script_location = command.get(
        "ScriptLocation",
        ""
    )

    glue_version = job.get(
        "GlueVersion",
        ""
    )

    worker_type = job.get(
        "WorkerType",
        ""
    )

    number_of_workers = job.get(
        "NumberOfWorkers",
        ""
    )

    max_capacity = job.get(
        "MaxCapacity",
        ""
    )

    execution_class = job.get(
        "ExecutionClass",
        ""
    )

    timeout = job.get(
        "Timeout",
        ""
    )

    max_retries = job.get(
        "MaxRetries",
        ""
    )

    # --------------------------------------------------------
    # Build description
    # --------------------------------------------------------

    description = POLICY_DESCRIPTION.format(
        job_name=job_name
    )

    description += (
        f" Job ARN: {job_arn}."
        f" Total runs in last {LOOKBACK_DAYS} days: "
        f"{metrics['total_runs']}."
        f" Total execution time: "
        f"{total_execution_hours:.4f} hours."
        f" Total execution seconds: "
        f"{metrics['total_execution_seconds']}."
        f" Successful runs: "
        f"{metrics['successful_runs']}."
        f" Failed runs: "
        f"{metrics['failed_runs']}."
        f" Stopped runs: "
        f"{metrics['stopped_runs']}."
        f" Timeout runs: "
        f"{metrics['timeout_runs']}."
        f" Error runs: "
        f"{metrics['error_runs']}."
        f" Total DPU seconds: "
        f"{metrics['total_dpu_seconds']}."
    )

    # --------------------------------------------------------
    # Job configuration details
    # --------------------------------------------------------

    description += (
        f" Glue Version: {glue_version}."
        f" Worker Type: {worker_type}."
        f" Number of Workers: {number_of_workers}."
        f" Max Capacity: {max_capacity}."
        f" Execution Class: {execution_class}."
        f" Timeout: {timeout} minutes."
        f" Max Retries: {max_retries}."
        f" Script Location: {script_location}."
    )

    # --------------------------------------------------------
    # Last execution
    # --------------------------------------------------------

    if metrics["last_run_time"]:

        description += (
            f" Last Run: "
            f"{metrics['last_run_time'].isoformat()}."
            f" Last Run State: "
            f"{metrics['last_run_state']}."
        )

    else:

        description += (
            f" No Job Run was detected during "
            f"the last {LOOKBACK_DAYS} days."
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    description += (
        " Recommendation: review whether the Glue job "
        "is still required. Check production schedules, "
        "CloudTrail activity, EventBridge rules, Step "
        "Functions, Glue Workflows, Lambda functions, "
        "or other orchestration dependencies before "
        "deleting the job. If the job is required but "
        "runs infrequently, consider keeping it or "
        "moving to an appropriate event-driven/on-demand "
        "execution model."
    )

    return {
        "job_name": job_name,
        "job_arn": job_arn,
        "description": description,
        "metrics": metrics
    }


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_arn,
    account_id,
    region_name
):
    """
    Get current resource-level cost from CUR + Athena.

    The FinOps Tool should connect this function to the
    centralized CUR + Athena implementation.

    IMPORTANT:
        Do not calculate current cost from MaxCapacity,
        NumberOfWorkers, or WorkerType.

        Allocated capacity is not the same as actual
        billed usage.

        Actual cost should come from CUR + Athena.
    """

    current_daily_cost = 0
    current_monthly_cost = 0

    return (
        current_daily_cost,
        current_monthly_cost
    )


# ============================================================
# 10) GENERATE EXCEL / OUTPUT
# ============================================================

def export_to_excel(
    findings,
    output_file
):
    """
    Write findings using the standard FinOps work-item schema.
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
        rows.append({
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": "Review Required",
            "areaPath": "AWS Cost Optimization",
            "tags": POLICY_TAG,
            "commentCount": 0,
            "accountId": finding["account_id"],
            "region": finding["region"],
            "resourceNameOrId": finding["job_name"],
            "resourceId": finding["job_name"],
            "resourceArn": finding.get("job_arn", ""),
            "service": POLICY_SERVICE,
            "type": "Glue Job",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"AWS Glue job '{finding['job_name']}' has very low execution time over the last {LOOKBACK_DAYS} days.",
            "recommendation": "Review whether the job is still required. Unused Glue job definitions do not typically create direct idle charges, but removing stale jobs can reduce operational clutter and misconfiguration risk.",
            "description": finding["description"],
            "currentDailyCost": finding["current_daily_cost"],
            "currentMonthlyCost": finding["current_monthly_cost"],
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": "",
            "month": datetime.now(timezone.utc).strftime("%Y-%m")
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(output_file, index=False)
    
    logger.info("Output written to: %s", output_file)


# ============================================================
# MAIN
# ============================================================

def main():

    start_scan_time = datetime.now(
        timezone.utc
    )

    logger.info(
        "Starting Glue Unused Job Review scan"
    )

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    glue, sts = create_clients(
        AWS_REGION
    )

    # --------------------------------------------------------
    # Get Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    logger.info(
        "AWS Account ID: %s",
        account_id
    )

    # --------------------------------------------------------
    # Fetch all Glue Jobs
    # --------------------------------------------------------

    jobs = fetch_all_glue_jobs(
        glue
    )

    total_jobs_scanned = len(
        jobs
    )

    findings = []

    # --------------------------------------------------------
    # Evaluate every Glue Job
    # --------------------------------------------------------

    for job in jobs:

        job_name = job.get(
            "Name",
            ""
        )

        try:

            finding = evaluate_glue_job(
                glue,
                job,
                account_id,
                AWS_REGION
            )

            if not finding:
                continue

            # ------------------------------------------------
            # Get current cost
            # ------------------------------------------------

            (
                current_daily_cost,
                current_monthly_cost
            ) = get_current_cost(
                finding["job_arn"],
                account_id,
                AWS_REGION
            )

            findings.append({
                "account_id": account_id,
                "region": AWS_REGION,
                "job_name": finding["job_name"],
                "job_arn": finding["job_arn"],
                "description": finding["description"],
                "current_daily_cost": current_daily_cost,
                "current_monthly_cost": current_monthly_cost
            })

            logger.info(
                "Finding detected: Glue Job '%s' "
                "has low execution time",
                job_name
            )

        except Exception as e:

            logger.error(
                "Failed to evaluate Glue Job '%s': %s",
                job_name,
                e
            )

    # --------------------------------------------------------
    # Generate output
    # --------------------------------------------------------

    export_to_excel(
        findings,
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Scan summary
    # --------------------------------------------------------

    end_scan_time = datetime.now(
        timezone.utc
    )

    scan_duration = (
        end_scan_time - start_scan_time
    ).total_seconds()

    logger.info(
        "=================================================="
    )

    logger.info(
        "Glue Unused Job Review Scan Completed"
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
        "Total Jobs Scanned      : %d",
        total_jobs_scanned
    )

    logger.info(
        "Unused Job Candidates   : %d",
        len(findings)
    )

    logger.info(
        "Lookback Period         : %d days",
        LOOKBACK_DAYS
    )

    logger.info(
        "Execution Threshold     : <= %.2f hours",
        MAX_EXECUTION_HOURS
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