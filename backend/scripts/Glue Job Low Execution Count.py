# ============================================================
# AWS FinOps Policy: Glue Job Low Execution Count
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

OUTPUT_FILE = "glue_job_low_execution_count.xlsx"

# Number of days used to evaluate job execution frequency
LOOKBACK_DAYS = 90

# Jobs with execution count <= this value are candidates
LOW_EXECUTION_THRESHOLD = 5

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

POLICY_TITLE = "Glue Job Low Execution Count"

POLICY_CATEGORY = "Glue Job Low Execution Count"

POLICY_SERVICE = "Glue"

POLICY_TAG = "Cloud Roar"

POLICY_DESCRIPTION = (
    "Glue job '{job_name}' has a low execution frequency. "
    f"Only {LOW_EXECUTION_THRESHOLD} or fewer runs were detected "
    f"in the last {LOOKBACK_DAYS} days. Review whether the job "
    "is still required, consolidate its logic, or consider "
    "on-demand/event-driven execution."
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
    Fetch all Glue jobs using pagination.
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
    Fetch Glue Job Runs for a specific job.

    Glue returns job runs in reverse chronological order.
    Pagination is used to retrieve all relevant runs.
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
            "Failed to fetch runs for Glue Job '%s': %s",
            job_name,
            e
        )

    return runs


def get_glue_job_usage(
    glue,
    job_name
):
    """
    Calculate Glue Job execution frequency during
    the configured lookback period.
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

    successful_runs = 0
    failed_runs = 0
    stopped_runs = 0
    timeout_runs = 0
    error_runs = 0

    last_run_time = None
    last_run_state = None

    for run in runs:

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

    return {
        "total_runs": len(runs),
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "stopped_runs": stopped_runs,
        "timeout_runs": timeout_runs,
        "error_runs": error_runs,
        "last_run_time": last_run_time,
        "last_run_state": last_run_state,
        "lookback_days": LOOKBACK_DAYS
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
    Evaluate Glue Job execution frequency.

    Candidate condition:

        Total job runs in the last 90 days
        <= LOW_EXECUTION_THRESHOLD

    Default threshold:
        5 runs or fewer in 90 days.
    """

    job_name = job.get(
        "Name",
        ""
    )

    if not job_name:
        return None

    # --------------------------------------------------------
    # Get execution history
    # --------------------------------------------------------

    usage = get_glue_job_usage(
        glue,
        job_name
    )

    total_runs = usage[
        "total_runs"
    ]

    # --------------------------------------------------------
    # Job is executing frequently enough
    # --------------------------------------------------------

    if total_runs > LOW_EXECUTION_THRESHOLD:

        return None

    # --------------------------------------------------------
    # Build Job ARN
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

    # --------------------------------------------------------
    # Build description
    # --------------------------------------------------------

    description = (
        f"Glue job '{job_name}' has very low execution "
        f"frequency. Only {total_runs} runs were detected "
        f"in the last {LOOKBACK_DAYS} days. "
    )

    description += (
        f"Successful runs: "
        f"{usage['successful_runs']}. "
        f"Failed runs: "
        f"{usage['failed_runs']}. "
        f"Stopped runs: "
        f"{usage['stopped_runs']}. "
        f"Timeout runs: "
        f"{usage['timeout_runs']}. "
        f"Error runs: "
        f"{usage['error_runs']}. "
    )

    description += (
        f"Job ARN: {job_arn}. "
        f"Glue Version: {glue_version}. "
        f"Worker Type: {worker_type}. "
        f"Number of Workers: {number_of_workers}. "
        f"Max Capacity: {max_capacity}. "
        f"Execution Class: {execution_class}. "
        f"Script Location: {script_location}. "
    )

    if usage["last_run_time"]:

        description += (
            f"Last Run: "
            f"{usage['last_run_time'].isoformat()}. "
            f"Last Run State: "
            f"{usage['last_run_state']}. "
        )

    else:

        description += (
            "The job has no recorded runs during "
            f"the last {LOOKBACK_DAYS} days. "
        )

    description += (
        "Recommendation: review the job's business purpose "
        "and trigger configuration before deletion. "
        "Consider consolidating low-frequency jobs or "
        "switching to on-demand/event-driven execution "
        "where appropriate."
    )

    return {
        "job_name": job_name,
        "job_arn": job_arn,
        "description": description,
        "usage": usage
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

    Do not estimate cost from DPU configuration alone because
    allocated capacity is not the same as actual billed usage.
    """

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Current Daily Cost and Current Monthly Cost should be
    # retrieved from CUR + Athena.
    #
    # The sample work items contain estimated monthly cost,
    # but this script does not fabricate that value.
    # --------------------------------------------------------

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
            "message": f"Glue job '{finding['job_name']}' has a low execution frequency.",
            "recommendation": "Review whether the job is still required, consolidate its logic, or consider on-demand/event-driven execution.",
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
        "Starting Glue Job Low Execution Count scan"
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
            # Get cost
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
                "with low execution count",
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
        "Glue Job Low Execution Count Scan Completed"
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
        "Low Execution Candidates: %d",
        len(findings)
    )

    logger.info(
        "Lookback Period         : %d days",
        LOOKBACK_DAYS
    )

    logger.info(
        "Execution Threshold     : <= %d runs",
        LOW_EXECUTION_THRESHOLD
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
    