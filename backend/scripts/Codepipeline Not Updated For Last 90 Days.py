
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

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
    "Codepipeline Not Updated For Last 90 Days"
)

POLICY_NAME = (
    "codepipeline-not-used-for-90-days"
)

SERVICE_NAME = "CodePipeline"

AREA_PATH = (
    "AWS Cost Optimization"
)

TAGS = "Cloud Roar"

EFFORT_LEVEL = "Low"

LOOKBACK_DAYS = 0.5


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

    codepipeline = boto3.client(
        "codepipeline",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return (
        codepipeline,
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
# FETCH ALL CODEPIPELINES
# ============================================================

def fetch_all_pipelines(
    codepipeline,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL CodePipeline
    pipelines in the selected region.

    Pagination is handled using the boto3
    paginator.
    """

    pipelines = []

    paginator = (
        codepipeline.get_paginator(
            "list_pipelines"
        )
    )

    for page in paginator.paginate():

        page_pipelines = page.get(
            "pipelines",
            []
        )

        pipelines.extend(
            page_pipelines
        )

    return pipelines


# ============================================================
# FETCH PIPELINE DETAILS
# ============================================================

def fetch_pipeline_details(
    codepipeline,
    pipeline_name: str,
) -> Dict[str, Any]:
    """
    Fetch detailed information about a
    CodePipeline.
    """

    try:

        response = (
            codepipeline.get_pipeline(
                name=pipeline_name
            )
        )

        return response.get(
            "pipeline",
            {}
        )

    except ClientError as e:

        print(
            f"Could not fetch details "
            f"for pipeline "
            f"{pipeline_name}: {e}"
        )

        return {}


# ============================================================
# FETCH PIPELINE EXECUTIONS
# ============================================================

def fetch_all_pipeline_executions(
    codepipeline,
    pipeline_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch pipeline execution history.

    The paginator automatically handles
    multiple pages.
    """

    executions = []

    try:

        paginator = (
            codepipeline.get_paginator(
                "list_pipeline_executions"
            )
        )

        for page in paginator.paginate(
            pipelineName=pipeline_name
        ):

            page_executions = page.get(
                "pipelineExecutionSummaries",
                []
            )

            executions.extend(
                page_executions
            )

    except ClientError as e:

        print(
            f"Could not fetch execution "
            f"history for pipeline "
            f"{pipeline_name}: {e}"
        )

    return executions


# ============================================================
# FIND MOST RECENT EXECUTION
# ============================================================

def find_latest_execution(
    executions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Find the most recent pipeline execution.
    """

    if not executions:

        return None

    valid_executions = []

    for execution in executions:

        start_time = execution.get(
            "startTime"
        )

        if start_time:

            valid_executions.append(
                execution
            )

    if not valid_executions:

        return None

    return max(
        valid_executions,
        key=lambda execution:
            execution.get(
                "startTime"
            )
    )


# ============================================================
# CALCULATE DAYS SINCE EXECUTION
# ============================================================

def calculate_days_since(
    execution_time: Optional[datetime],
) -> Optional[float]:

    if execution_time is None:

        return None

    if execution_time.tzinfo is None:

        execution_time = (
            execution_time.replace(
                tzinfo=timezone.utc
            )
        )

    now = datetime.now(
        timezone.utc
    )

    return round(
        (
            now - execution_time
        ).total_seconds()
        / 86400,
        2,
    )


# ============================================================
# CHECK WHETHER PIPELINE IS INACTIVE
# ============================================================

def is_inactive_pipeline(
    latest_execution: Optional[Dict[str, Any]],
) -> bool:
    """
    Returns True when:

    1. Pipeline has never executed
       OR
    2. Last execution is older than
       LOOKBACK_DAYS.
    """

    if latest_execution is None:

        return True

    start_time = latest_execution.get(
        "startTime"
    )

    if start_time is None:

        return True

    days_since_execution = (
        calculate_days_since(
            start_time
        )
    )

    if days_since_execution is None:

        return True

    return (
        days_since_execution
        > LOOKBACK_DAYS
    )


# ============================================================
# EXTRACT TAGS
# ============================================================

def fetch_pipeline_tags(
    codepipeline,
    pipeline_arn: Optional[str],
) -> Dict[str, str]:
    """
    Fetch CodePipeline tags.
    """

    if not pipeline_arn:

        return {}

    try:

        response = (
            codepipeline.list_tags_for_resource(
                resourceArn=pipeline_arn
            )
        )

        tags = response.get(
            "tags",
            []
        )

        return {
            tag.get("key"):
                tag.get("value")
            for tag in tags
            if tag.get("key")
        }

    except ClientError:

        return {}


# ============================================================
# BUILD MESSAGE
# ============================================================

def build_message(
    pipeline_name: str,
    latest_execution: Optional[
        Dict[str, Any]
    ],
    days_since_execution: Optional[
        float
    ],
) -> str:

    if latest_execution is None:

        return (

            f"CodePipeline "
            f"'{pipeline_name}' has no "
            f"recorded pipeline executions. "
            f"The pipeline should be reviewed "
            f"to determine whether it is still "
            f"required."
        )

    status = latest_execution.get(
        "status",
        "Unknown"
    )

    if days_since_execution is None:

        return (

            f"CodePipeline "
            f"'{pipeline_name}' has not had "
            f"a recent execution. "
            f"Review whether the pipeline "
            f"is still required."
        )

    return (

        f"CodePipeline "
        f"'{pipeline_name}' was last "
        f"executed {days_since_execution:.0f} "
        f"days ago with status "
        f"'{status}'. "
        f"It has not been actively used "
        f"within the last "
        f"{LOOKBACK_DAYS} days."
    )


# ============================================================
# BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    pipeline_name: str,
) -> str:

    return (

        f"Review CodePipeline "
        f"'{pipeline_name}' with the "
        f"DevOps/application owner. "

        f"If the pipeline is no longer "
        f"required, consider deleting it. "

        f"If it is intentionally retained "
        f"for occasional or emergency use, "
        f"document the requirement instead "
        f"of deleting it."
    )


# ============================================================
# BUILD DESCRIPTION
# ============================================================

def build_description(
    account_id: str,
    region_name: str,
    pipeline_name: str,
    pipeline_arn: Optional[str],
    pipeline_details: Dict[str, Any],
    executions: List[Dict[str, Any]],
    latest_execution: Optional[
        Dict[str, Any]
    ],
    days_since_execution: Optional[
        float
    ],
    tags: Dict[str, str],
) -> str:

    pipeline_version = (
        pipeline_details.get(
            "version"
        )
    )

    execution_count = len(
        executions
    )

    latest_execution_id = None

    latest_execution_status = None

    latest_execution_start = None

    latest_execution_end = None

    latest_execution_trigger = None

    if latest_execution:

        latest_execution_id = (
            latest_execution.get(
                "pipelineExecutionId"
            )
        )

        latest_execution_status = (
            latest_execution.get(
                "status"
            )
        )

        latest_execution_start = (
            latest_execution.get(
                "startTime"
            )
        )

        latest_execution_end = (
            latest_execution.get(
                "lastUpdateTime"
            )
        )

        latest_execution_trigger = (
            latest_execution.get(
                "trigger"
            )
        )

    return (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {pipeline_name} | "

        f"resourceArn: {pipeline_arn} | "

        f"pipelineVersion: "
        f"{pipeline_version} | "

        f"executionCountFetched: "
        f"{execution_count} | "

        f"lookbackDays: "
        f"{LOOKBACK_DAYS} | "

        f"latestExecutionId: "
        f"{latest_execution_id} | "

        f"latestExecutionStatus: "
        f"{latest_execution_status} | "

        f"latestExecutionStart: "
        f"{latest_execution_start} | "

        f"latestExecutionLastUpdate: "
        f"{latest_execution_end} | "

        f"latestExecutionTrigger: "
        f"{latest_execution_trigger} | "

        f"daysSinceLastExecution: "
        f"{days_since_execution} | "

        f"tags: "
        f"{json.dumps(tags)} | "

        f"type: Inactive | "

        f"policy: "
        f"{POLICY_NAME}"
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_pipeline_finding(
    pipeline_name: str,
    pipeline_details: Dict[str, Any],
    executions: List[Dict[str, Any]],
    latest_execution: Optional[
        Dict[str, Any]
    ],
    days_since_execution: Optional[
        float
    ],
    account_id: str,
    region_name: str,
    tags: Dict[str, str],
) -> Dict[str, Any]:

    pipeline_arn = pipeline_details.get(
        "arn"
    )

    message = build_message(

        pipeline_name=
            pipeline_name,

        latest_execution=
            latest_execution,

        days_since_execution=
            days_since_execution,
    )

    recommendation = (
        build_recommendation(
            pipeline_name
        )
    )

    description = build_description(

        account_id=
            account_id,

        region_name=
            region_name,

        pipeline_name=
            pipeline_name,

        pipeline_arn=
            pipeline_arn,

        pipeline_details=
            pipeline_details,

        executions=
            executions,

        latest_execution=
            latest_execution,

        days_since_execution=
            days_since_execution,

        tags=
            tags,
    )

    # --------------------------------------------------------
    # Standardized finding
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
            pipeline_name,

        "resourceId":
            pipeline_name,

        "resourceArn":
            pipeline_arn,

        "service":
            SERVICE_NAME,

        "type":
            "Inactive",

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
        # Cost intentionally not calculated yet.
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
# SCAN ALL CODEPIPELINES
# ============================================================

def scan_codepipelines(
    region_name: str,
) -> Dict[str, Any]:

    (
        codepipeline,
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
    # Fetch all pipelines
    # --------------------------------------------------------

    pipelines = fetch_all_pipelines(
        codepipeline
    )

    print(
        f"Total CodePipelines: "
        f"{len(pipelines)}"
    )

    findings = []

    # --------------------------------------------------------
    # Scan every pipeline
    # --------------------------------------------------------

    for pipeline in pipelines:

        pipeline_name = pipeline.get(
            "name"
        )

        print(
            f"\nScanning pipeline: "
            f"{pipeline_name}"
        )

        # ----------------------------------------------------
        # Fetch detailed pipeline data
        # ----------------------------------------------------

        pipeline_details = (
            fetch_pipeline_details(

                codepipeline,

                pipeline_name,
            )
        )

        # ----------------------------------------------------
        # Fetch execution history
        # ----------------------------------------------------

        executions = (
            fetch_all_pipeline_executions(

                codepipeline,

                pipeline_name,
            )
        )

        # ----------------------------------------------------
        # Find latest execution
        # ----------------------------------------------------

        latest_execution = (
            find_latest_execution(
                executions
            )
        )

        # ----------------------------------------------------
        # Calculate age of latest execution
        # ----------------------------------------------------

        days_since_execution = None

        if latest_execution:

            start_time = (
                latest_execution.get(
                    "startTime"
                )
            )

            days_since_execution = (
                calculate_days_since(
                    start_time
                )
            )

        # ----------------------------------------------------
        # Print diagnostic information
        # ----------------------------------------------------

        print(
            f"Executions fetched: "
            f"{len(executions)}"
        )

        print(
            f"Last execution: "
            f"{days_since_execution} "
            f"days ago"
        )

        # ----------------------------------------------------
        # Check policy
        # ----------------------------------------------------

        inactive = (
            is_inactive_pipeline(
                latest_execution
            )
        )

        if not inactive:

            print(
                "Pipeline is active."
            )

            continue

        # ----------------------------------------------------
        # Fetch tags
        # ----------------------------------------------------

        pipeline_arn = (
            pipeline_details.get(
                "arn"
            )
        )

        tags = fetch_pipeline_tags(

            codepipeline,

            pipeline_arn,
        )

        # ----------------------------------------------------
        # Build finding
        # ----------------------------------------------------

        finding = build_pipeline_finding(

            pipeline_name=
                pipeline_name,

            pipeline_details=
                pipeline_details,

            executions=
                executions,

            latest_execution=
                latest_execution,

            days_since_execution=
                days_since_execution,

            account_id=
                account_id,

            region_name=
                region_name,

            tags=
                tags,
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

        "totalPipelinesScanned":
            len(pipelines),

        "totalInactivePipelines":
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

        index=False,
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
    # Pipeline names are discovered
    # automatically.
    # --------------------------------------------------------

    region = "us-east-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS CODEPIPELINE FINOPS SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Inactivity threshold: "
        f"{LOOKBACK_DAYS} days"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_codepipelines(
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
        "Pipelines scanned:",
        result.get(
            "totalPipelinesScanned"
        )
    )

    print(
        "Inactive pipelines:",
        result.get(
            "totalInactivePipelines"
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
            "\nNo inactive CodePipeline "
            "findings found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "codepipeline_not_updated_90_days_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )
