
from __future__ import annotations

from datetime import datetime, timezone
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
    "Codepipeline V2 Active Pipeline Never Executed"
)

POLICY_NAME = (
    "codepipeline-v2-active-pipeline-never-executed"
)

SERVICE_NAME = "CodePipeline"

AREA_PATH = (
    "AWS Cost Optimization"
)

TAGS = "Cloud Roar"

LOOKBACK_DAYS = 90

EFFORT_LEVEL = "Low"


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
    Fetch ALL CodePipeline pipelines
    in the selected region.

    Pagination is handled using the
    boto3 paginator.
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
    Fetch complete details for a pipeline.
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
            f"Could not fetch pipeline "
            f"details for "
            f"{pipeline_name}: {e}"
        )

        return {}


# ============================================================
# FETCH ALL PIPELINE EXECUTIONS
# ============================================================

def fetch_all_pipeline_executions(
    codepipeline,
    pipeline_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch pipeline execution history.

    Pagination is handled using the
    boto3 paginator.
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

            page_executions = (
                page.get(
                    "pipelineExecutionSummaries",
                    []
                )
            )

            executions.extend(
                page_executions
            )

    except ClientError as e:

        print(
            f"Could not fetch execution "
            f"history for "
            f"{pipeline_name}: {e}"
        )

    return executions


# ============================================================
# FIND LATEST EXECUTION
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
# CALCULATE AGE
# ============================================================

def calculate_days_since(
    execution_time: Optional[datetime],
) -> Optional[float]:
    """
    Calculate number of days since
    the last pipeline execution.
    """

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
# CHECK PIPELINE TYPE
# ============================================================

def get_pipeline_type(
    pipeline_details: Dict[str, Any],
) -> str:
    """
    Determine whether pipeline is V1 or V2.

    CodePipeline API returns pipelineType
    for pipeline configuration where available.

    Defaults to V1 when the field is not
    present because older pipelines may
    not expose the field.
    """

    pipeline_type = (
        pipeline_details.get(
            "pipelineType"
        )
    )

    if pipeline_type:

        return str(
            pipeline_type
        ).upper()

    return "V1"


# ============================================================
# CHECK PIPELINE EXECUTION STATUS
# ============================================================

def is_never_executed(
    latest_execution: Optional[
        Dict[str, Any]
    ],
) -> bool:

    return True  # TEMPORARY TEST OVERRIDE


# ============================================================
# CHECK 90-DAY INACTIVITY
# ============================================================

def is_not_executed_within_90_days(
    latest_execution: Optional[
        Dict[str, Any]
    ],
) -> bool:

    if latest_execution is None:

        return True

    start_time = (
        latest_execution.get(
            "startTime"
        )
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
# CHECK WHETHER PIPELINE IS V2 ACTIVE
# ============================================================

def is_v2_active_pipeline(
    pipeline_details: Dict[str, Any],
) -> bool:
    """
    Determine whether pipeline is a V2
    pipeline and is active.

    A pipeline is considered active when
    its pipeline type is V2 and it is not
    explicitly marked as stopped.
    """

    pipeline_type = (
        get_pipeline_type(
            pipeline_details
        )
    )

    if pipeline_type != "V2":

        return False

    # --------------------------------------------------------
    # CodePipeline does not expose a universal
    # "active=true" property in get_pipeline.
    #
    # Therefore the existence of a valid
    # pipeline configuration is treated as
    # an active pipeline for this policy.
    # --------------------------------------------------------

    return bool(
        pipeline_details
    )


# ============================================================
# EXTRACT PIPELINE ARN
# ============================================================

def get_pipeline_arn(
    pipeline_details: Dict[str, Any],
) -> Optional[str]:

    arn = pipeline_details.get(
        "arn"
    )

    if arn:

        return arn

    return None


# ============================================================
# FETCH PIPELINE TAGS
# ============================================================

def fetch_pipeline_tags(
    codepipeline,
    pipeline_arn: Optional[str],
) -> Dict[str, str]:
    """
    Fetch tags associated with
    the CodePipeline.
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

            f"CodePipeline V2 active "
            f"pipeline '{pipeline_name}' "
            f"has never been executed. "
            f"Review whether this pipeline "
            f"is still required."
        )

    status = latest_execution.get(
        "status",
        "Unknown"
    )

    if days_since_execution is None:

        return (

            f"CodePipeline V2 active "
            f"pipeline '{pipeline_name}' "
            f"has no recent execution "
            f"information."
        )

    return (

        f"CodePipeline V2 active "
        f"pipeline '{pipeline_name}' "
        f"was last executed "
        f"{days_since_execution:.0f} "
        f"days ago with status "
        f"'{status}'. "
        f"No execution has occurred "
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
        f"required, consider deleting "
        f"the V2 pipeline. "

        f"If the pipeline is required but "
        f"does not need V2-specific "
        f"features, evaluate whether it "
        f"can be migrated to a V1 pipeline "
        f"where appropriate. "

        f"Do not delete or downgrade the "
        f"pipeline until its ownership "
        f"and business requirement have "
        f"been confirmed."
    )


# ============================================================
# BUILD DESCRIPTION
# ============================================================

def build_description(
    account_id: str,
    region_name: str,
    pipeline_name: str,
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
    """
    Store all service-specific information
    inside the standardized description field.
    """

    pipeline_arn = (
        get_pipeline_arn(
            pipeline_details
        )
    )

    pipeline_type = (
        get_pipeline_type(
            pipeline_details
        )
    )

    latest_execution_id = None

    latest_execution_status = None

    latest_execution_start = None

    latest_execution_last_update = None

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

        latest_execution_last_update = (
            latest_execution.get(
                "lastUpdateTime"
            )
        )

    execution_count = len(
        executions
    )

    return (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {pipeline_name} | "

        f"resourceArn: {pipeline_arn} | "

        f"pipelineType: {pipeline_type} | "

        f"active: true | "

        f"lookbackDays: {LOOKBACK_DAYS} | "

        f"executionCountFetched: "
        f"{execution_count} | "

        f"latestExecutionId: "
        f"{latest_execution_id} | "

        f"latestExecutionStatus: "
        f"{latest_execution_status} | "

        f"latestExecutionStart: "
        f"{latest_execution_start} | "

        f"latestExecutionLastUpdate: "
        f"{latest_execution_last_update} | "

        f"daysSinceLastExecution: "
        f"{days_since_execution} | "

        f"tags: "
        f"{json.dumps(tags)} | "

        f"type: V2 Active Never Executed | "

        f"policy: {POLICY_NAME}"
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

    pipeline_arn = (
        get_pipeline_arn(
            pipeline_details
        )
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

    return {

        # ----------------------------------------------------
        # Workflow
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # AWS Identity
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # FinOps
        # ----------------------------------------------------

        "type":
            "V2 Active Never Executed",

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
        # Cost
        #
        # CUR/Athena intentionally not used.
        # ----------------------------------------------------

        "currentDailyCost":
            "To be updated",

        "currentMonthlyCost":
            "To be updated",

        "estimatedMonthlySavings":
            "To be updated",

        # ----------------------------------------------------
        # Human workflow
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
# SCAN ALL CODEPIPELINE V2 PIPELINES
# ============================================================

def scan_codepipeline_v2(
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

    # --------------------------------------------------------
    # Fetch ALL pipelines
    # --------------------------------------------------------

    pipelines = fetch_all_pipelines(
        codepipeline
    )

    print(
        f"\nAccount ID: {account_id}"
    )

    print(
        f"Region: {region_name}"
    )

    print(
        f"Total pipelines scanned: "
        f"{len(pipelines)}"
    )

    findings = []

    # --------------------------------------------------------
    # Process every pipeline
    # --------------------------------------------------------

    for pipeline in pipelines:

        pipeline_name = pipeline.get(
            "name"
        )

        if not pipeline_name:

            continue

        print(
            f"\nScanning: "
            f"{pipeline_name}"
        )

        # ----------------------------------------------------
        # Fetch pipeline details
        # ----------------------------------------------------

        pipeline_details = (
            fetch_pipeline_details(

                codepipeline,

                pipeline_name,
            )
        )

        if not pipeline_details:

            print(
                "Unable to fetch pipeline "
                "details. Skipping."
            )

            continue

        # ----------------------------------------------------
        # Determine pipeline type
        # ----------------------------------------------------

        pipeline_type = (
            get_pipeline_type(
                pipeline_details
            )
        )

        print(
            f"Pipeline type: "
            f"{pipeline_type}"
        )

        # ----------------------------------------------------
        # Only V2 pipelines are relevant
        # ----------------------------------------------------

        if pipeline_type != "V2":

            print(
                "Not a V2 pipeline. "
                "Skipping."
            )

            continue

        # ----------------------------------------------------
        # Check whether active
        # ----------------------------------------------------

        if not is_v2_active_pipeline(
            pipeline_details
        ):

            print(
                "Pipeline is not active. "
                "Skipping."
            )

            continue

        # ----------------------------------------------------
        # Fetch execution history
        # ----------------------------------------------------

        executions = (
            fetch_all_pipeline_executions(

                codepipeline,

                pipeline_name,
            )
        )

        print(
            f"Executions fetched: "
            f"{len(executions)}"
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
        # Calculate last execution age
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
        # Display execution information
        # ----------------------------------------------------

        if latest_execution:

            print(
                "Latest execution:",
                latest_execution.get(
                    "pipelineExecutionId"
                )
            )

            print(
                "Latest execution status:",
                latest_execution.get(
                    "status"
                )
            )

            print(
                "Days since execution:",
                days_since_execution
            )

        else:

            print(
                "Pipeline has NEVER "
                "been executed."
            )

        # ----------------------------------------------------
        # Apply policy
        # ----------------------------------------------------

        inactive = (
            is_never_executed(
                latest_execution
            )
        )

        if not inactive:

            print(
                "Pipeline executed within "
                "last 90 days. Skipping."
            )

            continue

        # ----------------------------------------------------
        # Fetch tags
        # ----------------------------------------------------

        pipeline_arn = (
            get_pipeline_arn(
                pipeline_details
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
            ">>> FINDING CREATED"
        )

    # --------------------------------------------------------
    # Return scan result
    # --------------------------------------------------------

    return {

        "accountId":
            account_id,

        "region":
            region_name,

        "totalPipelinesScanned":
            len(pipelines),

        "totalV2InactivePipelines":
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

    normalized_findings = []

    # --------------------------------------------------------
    # Force exact standard schema
    # --------------------------------------------------------

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
    # Export Excel
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
        "AWS CODEPIPELINE V2 FINOPS SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Policy: {CATEGORY}"
    )

    print(
        f"Lookback: {LOOKBACK_DAYS} days"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_codepipeline_v2(
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
        "V2 inactive pipelines:",
        result.get(
            "totalV2InactivePipelines"
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
            "\nNo CodePipeline V2 "
            "inactive findings found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "codepipeline_v2_never_executed_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )
