# ============================================================
# AWS FinOps Policy: Glue ETL Rightsizing
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

OUTPUT_FILE = "glue_etl_rightsizing.xlsx"

# Lookback period used to determine whether the Glue ETL Job
# has actually been executed recently.
LOOKBACK_DAYS = 30

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

POLICY_TITLE = "Glue ETL Rightsizing"
POLICY_CATEGORY = "Glue ETL Rightsizing"
POLICY_SERVICE = "Glue"
POLICY_TAG = "Cloud Roar"

POLICY_DESCRIPTION = (
    "Glue ETL Job '{job_name}' has no job runs in the last "
    f"{LOOKBACK_DAYS} days. Review the job and its triggering "
    "dependencies before deleting it. Jobs may be triggered "
    "externally through event-driven workflows."
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
    Fetch all Glue ETL Jobs using pagination.
    """

    jobs = []

    paginator = glue.get_paginator("get_jobs")

    try:
        for page in paginator.paginate():
            page_jobs = page.get("Jobs", [])

            jobs.extend(page_jobs)

    except ClientError as e:
        logger.error(
            "Failed to fetch Glue Jobs: %s",
            e
        )

    logger.info(
        "Total Glue ETL Jobs fetched: %d",
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
    Fetch Glue Job Runs using pagination and return
    runs that fall inside the configured lookback period.
    """

    runs = []

    paginator = glue.get_paginator("get_job_runs")

    try:
        for page in paginator.paginate(
            JobName=job_name
        ):
            page_runs = page.get("JobRuns", [])

            for run in page_runs:

                started_on = run.get("StartedOn")

                if not started_on:
                    continue

                # AWS returns timezone-aware datetime values.
                if started_on.tzinfo is None:
                    started_on = started_on.replace(
                        tzinfo=timezone.utc
                    )

                if start_time <= started_on <= end_time:
                    runs.append(run)

                # Glue returns runs in reverse chronological
                # order. Once we reach runs older than the
                # lookback period, we can stop processing.
                elif started_on < start_time:
                    return runs

    except ClientError as e:
        logger.error(
            "Failed to fetch job runs for '%s': %s",
            job_name,
            e
        )

    return runs


def get_glue_job_usage(
    glue,
    job_name
):
    """
    Determine actual Glue ETL Job usage based on job-run history.

    A job is considered unused for this FinOps policy when
    there are zero job runs during the configured lookback period.
    """

    end_time = datetime.now(timezone.utc)

    start_time = end_time - timedelta(
        days=LOOKBACK_DAYS
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

    last_run_time = None
    last_run_state = None

    for run in runs:

        state = run.get("JobRunState")

        if state == "SUCCEEDED":
            successful_runs += 1

        elif state == "FAILED":
            failed_runs += 1

        elif state in (
            "STOPPED",
            "TIMEOUT",
            "ERROR"
        ):
            stopped_runs += 1

        started_on = run.get("StartedOn")

        if started_on:

            if (
                last_run_time is None
                or started_on > last_run_time
            ):
                last_run_time = started_on
                last_run_state = state

    return {
        "lookback_days": LOOKBACK_DAYS,
        "total_runs": len(runs),
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "stopped_runs": stopped_runs,
        "last_run_time": last_run_time,
        "last_run_state": last_run_state
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
    Evaluate whether a Glue ETL Job is a rightsizing candidate.

    Finding condition:
        No Glue Job Runs during the configured lookback period.

    Important:
        This does NOT automatically mean the job can be deleted.
        External/event-driven dependencies must be reviewed first.
    """

    job_name = job.get("Name", "")

    job_arn = (
        f"arn:aws:glue:{region_name}:"
        f"{account_id}:job/{job_name}"
    )

    usage = get_glue_job_usage(
        glue,
        job_name
    )

    total_runs = usage["total_runs"]

    # --------------------------------------------------------
    # Job has recent usage
    # --------------------------------------------------------

    if total_runs > 0:
        return None

    # --------------------------------------------------------
    # No runs during lookback period
    # --------------------------------------------------------

    description = POLICY_DESCRIPTION.format(
        job_name=job_name
    )

    description += (
        f" Job ARN: {job_arn}."
        f" Job runs in last {LOOKBACK_DAYS} days: "
        f"{usage['total_runs']}."
        f" Successful runs: {usage['successful_runs']}."
        f" Failed runs: {usage['failed_runs']}."
        f" Stopped/timeout/error runs: "
        f"{usage['stopped_runs']}."
        " Review CloudTrail/EventBridge and other "
        "orchestration dependencies before removal."
    )

    # --------------------------------------------------------
    # Additional Glue Job details
    # --------------------------------------------------------

    glue_version = job.get("GlueVersion", "")

    worker_type = job.get("WorkerType", "")

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

    command = job.get(
        "Command",
        {}
    )

    script_location = command.get(
        "ScriptLocation",
        ""
    )

    description += (
        f" Glue Version: {glue_version}."
        f" Worker Type: {worker_type}."
        f" Number of Workers: {number_of_workers}."
        f" Max Capacity: {max_capacity}."
        f" Execution Class: {execution_class}."
        f" Script Location: {script_location}."
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
    Placeholder for CUR + Athena resource-level cost lookup.

    Resource-level cost should come from the FinOps Tool's
    centralized CUR + Athena implementation.

    Do not invent cost values when CUR data is unavailable.
    """

    # --------------------------------------------------------
    # IMPORTANT:
    # Glue ETL job cost is generated primarily when the job
    # actually executes. Therefore, a job with no runs during
    # the lookback period may have no current execution cost.
    #
    # The authoritative monthly/daily cost should still be
    # retrieved from CUR + Athena.
    # --------------------------------------------------------

    current_daily_cost = 0
    current_monthly_cost = 0

    return current_daily_cost, current_monthly_cost


# ============================================================
# 10) GENERATE EXCEL / OUTPUT
# ============================================================

def export_to_excel(
    findings,
    output_file
):
    """
    Write FinOps findings to Excel using the standard
    FinOps work-item schema.
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
            "type": "Glue ETL Job",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Glue ETL Job '{finding['job_name']}' has no job runs in the last {LOOKBACK_DAYS} days.",
            "recommendation": "Review the job and its triggering dependencies before deleting it. Jobs may be triggered externally through event-driven workflows.",
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
        "Starting Glue ETL Rightsizing scan"
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

    account_id = get_account_id(sts)

    logger.info(
        "AWS Account ID: %s",
        account_id
    )

    # --------------------------------------------------------
    # Fetch all Glue ETL Jobs
    # --------------------------------------------------------

    jobs = fetch_all_glue_jobs(
        glue
    )

    total_jobs_scanned = len(jobs)

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
            # Cost
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
                "Finding detected: Glue Job '%s'",
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
        "Glue ETL Rightsizing Scan Completed"
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
        "Rightsizing Candidates  : %d",
        len(findings)
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