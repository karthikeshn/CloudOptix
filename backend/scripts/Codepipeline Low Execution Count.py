from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import boto3

from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd

import json


# ============================================================
# 1. IMPORTS
# ============================================================


# ============================================================
# 2. AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)




# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "CodePipeline Low Execution Count"

CATEGORY = "CodePipeline Low Execution Count"

SERVICE_NAME = "CodePipeline"

EFFORT_LEVEL = "Low"


# ------------------------------------------------------------
# Multi-account configuration
# ------------------------------------------------------------

ACCOUNT_IDS: List[str] = [
    "675134942214",
]


ASSUME_ROLE_NAME = "FinOpsReadOnlyRole"

ASSUME_ROLE_SESSION_NAME = (
    "FinOpsCodePipelineScanner"
)


# ------------------------------------------------------------
# Policy thresholds
# ------------------------------------------------------------

# Number of days to look back when checking pipeline
# executions.
LOOKBACK_DAYS = 90


# Maximum number of executions allowed for a pipeline to
# qualify as a low-execution candidate.
#
# 0 means only pipelines with zero executions will qualify.
#
# 1 means pipelines with 0 or 1 execution qualify.
#
# 2 means pipelines with 0, 1, or 2 executions qualify.
#
MAX_EXECUTION_COUNT = 1


# ============================================================
# 4. STANDARD EXCEL COLUMNS
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
# 5. BASE AWS CLIENT
# ============================================================

def create_base_sts_client():
    """
    Create STS client using the credentials that execute
    this scanner.

    These credentials are used to assume the FinOpsReadOnlyRole
    in each target account.
    """

    return boto3.client(
        "sts",
        config=AWS_CONFIG,
    )


# ============================================================
# 6. ASSUME TARGET ACCOUNT ROLE
# ============================================================

def assume_target_account_role(
    base_sts,
    account_id: str,
):
    """
    Assume FinOpsReadOnlyRole in the target AWS account.
    """

    role_arn = (
        f"arn:aws:iam::{account_id}:role/"
        f"{ASSUME_ROLE_NAME}"
    )

    try:

        response = base_sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=(
                f"{ASSUME_ROLE_SESSION_NAME}-"
                f"{account_id}"
            ),
        )

        return response["Credentials"]

    except ClientError as exc:

        print(
            f"[ERROR] Unable to assume role in "
            f"account {account_id}: {exc}"
        )

        return None


# ============================================================
# 7. CREATE TARGET ACCOUNT CLIENTS
# ============================================================

def create_target_account_clients(
    credentials,
    region_name: str,
):
    """
    Create CodePipeline and STS clients using the temporary
    credentials obtained from the target account.

    CodePipeline is Region-specific, therefore the caller
    supplies the Region being scanned.
    """

    if credentials is None:
        session = boto3.Session()
    else:
        session = boto3.Session(
            aws_access_key_id=(
                credentials["AccessKeyId"]
            ),
            aws_secret_access_key=(
                credentials["SecretAccessKey"]
            ),
            aws_session_token=(
                credentials["SessionToken"]
            ),
        )

    codepipeline = session.client(
        "codepipeline",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = session.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return codepipeline, sts


# ============================================================
# 8. GET ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:
    """
    Return the account ID associated with the assumed role.
    """

    return sts.get_caller_identity()[
        "Account"
    ]


# ============================================================
# 9. FETCH ALL PIPELINES
# ============================================================

def fetch_all_pipelines(
    codepipeline,
) -> List[Dict[str, Any]]:
    """
    Fetch all CodePipeline pipelines in the Region.

    Uses the Boto3 paginator so large environments are fully
    scanned.
    """

    pipelines: List[
        Dict[str, Any]
    ] = []

    paginator = codepipeline.get_paginator(
        "list_pipelines"
    )

    try:

        for page in paginator.paginate():

            page_pipelines = page.get(
                "pipelines",
                [],
            )

            pipelines.extend(
                page_pipelines
            )

    except ClientError as exc:

        print(
            f"[ERROR] Failed to list CodePipeline "
            f"pipelines: {exc}"
        )

        raise

    return pipelines


# ============================================================
# 10. GET PIPELINE EXECUTION HISTORY
# ============================================================

def fetch_pipeline_executions(
    codepipeline,
    pipeline_name: str,
    start_time: datetime,
) -> List[Dict[str, Any]]:
    """
    Fetch pipeline executions that fall within the configured
    lookback window.

    CodePipeline returns execution summaries through
    ListPipelineExecutions.
    """

    executions: List[
        Dict[str, Any]
    ] = []

    paginator = codepipeline.get_paginator(
        "list_pipeline_executions"
    )

    try:

        for page in paginator.paginate(
            pipelineName=pipeline_name
        ):

            page_executions = page.get(
                "pipelineExecutionSummaries",
                [],
            )

            for execution in page_executions:

                execution_start_time = (
                    execution.get(
                        "startTime"
                    )
                )

                if execution_start_time is None:
                    continue

                execution_start_time = (
                    normalize_datetime(
                        execution_start_time
                    )
                )

                if execution_start_time is None:
                    continue

                # ------------------------------------------------
                # The API results are normally newest first.
                #
                # Once an execution is older than the
                # lookback period, stop processing additional
                # executions from this page sequence.
                # ------------------------------------------------

                if execution_start_time < start_time:

                    return executions

                executions.append(
                    execution
                )

    except ClientError as exc:

        print(
            f"[ERROR] Failed to fetch executions for "
            f"pipeline '{pipeline_name}': {exc}"
        )

        raise

    return executions


# ============================================================
# 11. DATETIME NORMALIZATION
# ============================================================

def normalize_datetime(
    value: Any,
) -> Optional[datetime]:
    """
    Convert AWS datetime/string values into timezone-aware
    UTC datetime values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):

        if value.tzinfo is None:

            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    if isinstance(
        value,
        str,
    ):

        try:

            parsed = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except ValueError:

            return None

    return None


# ============================================================
# 12. BUSINESS LOGIC
# ============================================================

def count_pipeline_executions(
    executions: List[Dict[str, Any]],
) -> int:
    """
    Return the number of executions discovered within the
    configured lookback period.
    """

    return len(
        executions
    )


def is_candidate(
    execution_count: int,
) -> bool:
    """
    Determine whether a pipeline qualifies as a
    low-execution candidate.
    """

    return (
        execution_count
        <= MAX_EXECUTION_COUNT
    )


# ============================================================
# 13. BUILD MESSAGE
# ============================================================

def build_message(
    pipeline_name: str,
    execution_count: int,
) -> str:
    """
    Build human-readable finding message.
    """

    if execution_count == 0:

        execution_text = (
            "approximately 0 times"
        )

    elif execution_count == 1:

        execution_text = (
            "1 time"
        )

    else:

        execution_text = (
            f"{execution_count} times"
        )

    return (
        f"CodePipeline pipeline "
        f"{pipeline_name} has run "
        f"{execution_text} over the last "
        f"{LOOKBACK_DAYS} days. "
        f"This pipeline appears to have very low "
        f"execution activity and should be reviewed "
        f"for potential retirement."
    )


# ============================================================
# 14. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    pipeline_name: str,
) -> str:
    """
    Build human-readable remediation instructions.
    """

    return (
        f"Review CodePipeline '{pipeline_name}' with "
        f"the DevOps, application, and pipeline owners. "
        f"Confirm whether the pipeline is still required "
        f"for scheduled, manual, vendor, client, disaster "
        f"recovery, or infrequent release activities. "
        f"If it is confirmed to be permanently unused, "
        f"delete the pipeline using the CodePipeline "
        f"DeletePipeline API."
    )


# ============================================================
# 15. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    pipeline: Dict[str, Any],
    execution_count: int,
    lookback_start: datetime,
) -> Dict[str, Any]:
    """
    Build standardized FinOps finding.

    Service-specific fields are intentionally kept as root
    JSON fields and will be bundled into description by the
    Excel exporter.
    """

    pipeline_name = pipeline.get(
        "name"
    )

    pipeline_version = pipeline.get(
        "version"
    )

    pipeline_type = pipeline.get(
        "pipelineType"
    )

    pipeline_arn = (
        f"arn:aws:codepipeline:"
        f"{region_name}:"
        f"{account_id}:"
        f"{pipeline_name}"
    )

    return {
        # ====================================================
        # Workflow
        # ====================================================

        "workItemType": "Task",

        "state": "To Do",

        "id": None,

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": "Cloud Roar",

        "commentCount": 0,

        # ====================================================
        # AWS
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": pipeline_name,

        "resourceId": pipeline_name,

        "resourceArn": pipeline_arn,

        # ====================================================
        # Service
        # ====================================================

        "service": SERVICE_NAME,

        "type": "Optimization Description",

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        # ====================================================
        # Finding
        # ====================================================

        "message": build_message(
            pipeline_name=pipeline_name,
            execution_count=execution_count,
        ),

        "recommendation": build_recommendation(
            pipeline_name=pipeline_name
        ),

        # ====================================================
        # Cost
        #
        # CUR/Athena intentionally not used.
        # ====================================================

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        # ====================================================
        # Workflow
        # ====================================================

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",

        # ====================================================
        # Service-specific fields
        # ====================================================

        "pipelineName": pipeline_name,

        "pipelineVersion": pipeline_version,

        "pipelineType": pipeline_type,

        "executionCount": execution_count,

        "lookbackDays": LOOKBACK_DAYS,

        "lookbackStart": lookback_start,

        "maxExecutionCount": MAX_EXECUTION_COUNT,
    }


# ============================================================
# 16. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the standard Excel schema.

    Any service-specific fields are dynamically appended to
    the description column as pipe-separated attributes.
    """

    flat_findings: List[
        Dict[str, Any]
    ] = []

    for finding in findings:

        standard_data: Dict[
            str,
            Any,
        ] = {}

        extra_attributes: List[
            str
        ] = []

        for key, value in finding.items():

            if key in STANDARD_COLUMNS:

                standard_data[key] = value

            else:

                if value is None:
                    continue

                if isinstance(
                    value,
                    (dict, list),
                ):

                    value_string = json.dumps(
                        value,
                        default=str,
                    )

                else:

                    value_string = str(
                        value
                    )

                extra_attributes.append(
                    f"{key}: {value_string}"
                )

        existing_description = (
            standard_data.get(
                "description",
                "",
            )
        )

        if extra_attributes:

            extra_description = (
                " | ".join(
                    extra_attributes
                )
            )

            if existing_description:

                standard_data[
                    "description"
                ] = (
                    f"{existing_description} | "
                    f"{extra_description}"
                )

            else:

                standard_data[
                    "description"
                ] = extra_description

        else:

            standard_data[
                "description"
            ] = existing_description

        flat_findings.append(
            standard_data
        )

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS,
    )

    df.to_excel(
        filename,
        index=False,
    )

    print(
        f"[INFO] Excel report generated: "
        f"{filename}"
    )


# ============================================================
# 17. SCAN ONE ACCOUNT / REGION
# ============================================================

def scan_account_region(
    base_sts,
    target_account_id: str,
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan CodePipeline pipelines for one account and one Region.

    One account may have CodePipeline pipelines in multiple
    Regions, therefore the caller controls the Region.
    """

    print()
    print(
        "=" * 70
    )

    print(
        f"[INFO] Account : {target_account_id}"
    )

    print(
        f"[INFO] Region  : {region_name}"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Assume target account (skip for local account)
    # --------------------------------------------------------
    
    base_account_id = get_account_id(base_sts)
    
    if target_account_id == base_account_id:
        print(f"[INFO] Bypassing AssumeRole for local account {target_account_id}")
        credentials = None
    else:
        credentials = (
            assume_target_account_role(
                base_sts=base_sts,
                account_id=target_account_id,
            )
        )

        if credentials is None:

            return {
                "accountId": target_account_id,
                "region": region_name,
                "success": False,
                "totalPipelinesScanned": 0,
                "totalCandidates": 0,
                "findings": [],
                "error": (
                    "Unable to assume target account role"
                ),
            }

    try:

        codepipeline, sts = (
            create_target_account_clients(
                credentials=credentials,
                region_name=region_name,
            )
        )

        actual_account_id = get_account_id(
            sts
        )

        # ----------------------------------------------------
        # Account safety check
        # ----------------------------------------------------

        if actual_account_id != (
            target_account_id
        ):

            error_message = (
                f"Account mismatch. Requested "
                f"{target_account_id}, but assumed "
                f"credentials belong to "
                f"{actual_account_id}."
            )

            print(
                f"[ERROR] {error_message}"
            )

            return {
                "accountId": target_account_id,
                "region": region_name,
                "success": False,
                "totalPipelinesScanned": 0,
                "totalCandidates": 0,
                "findings": [],
                "error": error_message,
            }

        # ----------------------------------------------------
        # Fetch pipelines
        # ----------------------------------------------------

        pipelines = fetch_all_pipelines(
            codepipeline
        )

        print(
            f"[INFO] Pipelines discovered: "
            f"{len(pipelines)}"
        )

        # ----------------------------------------------------
        # Lookback period
        # ----------------------------------------------------

        now = datetime.now(
            timezone.utc
        )

        lookback_start = (
            now
            - timedelta(
                days=LOOKBACK_DAYS
            )
        )

        findings: List[
            Dict[str, Any]
        ] = []

        # ----------------------------------------------------
        # Process each pipeline
        # ----------------------------------------------------

        for pipeline in pipelines:

            pipeline_name = pipeline.get(
                "name",
                "Unknown",
            )

            try:

                executions = (
                    fetch_pipeline_executions(
                        codepipeline=codepipeline,
                        pipeline_name=pipeline_name,
                        start_time=lookback_start,
                    )
                )

                execution_count = (
                    count_pipeline_executions(
                        executions
                    )
                )

                print(
                    f"[INFO] Pipeline="
                    f"{pipeline_name} | "
                    f"Executions="
                    f"{execution_count} | "
                    f"Lookback="
                    f"{LOOKBACK_DAYS} days"
                )

                # ------------------------------------------------
                # Candidate evaluation
                # ------------------------------------------------

                if not is_candidate(
                    execution_count
                ):

                    continue

                finding = build_finding(
                    account_id=actual_account_id,
                    region_name=region_name,
                    pipeline=pipeline,
                    execution_count=(
                        execution_count
                    ),
                    lookback_start=(
                        lookback_start
                    ),
                )

                findings.append(
                    finding
                )

                print(
                    f"[FINDING] Account="
                    f"{actual_account_id} | "
                    f"Region="
                    f"{region_name} | "
                    f"Pipeline="
                    f"{pipeline_name} | "
                    f"Executions="
                    f"{execution_count}"
                )

            except ClientError as exc:

                print(
                    f"[ERROR] AWS error processing "
                    f"pipeline '{pipeline_name}' "
                    f"in account "
                    f"{actual_account_id}: "
                    f"{exc}"
                )

                continue

            except Exception as exc:

                print(
                    f"[ERROR] Unexpected error processing "
                    f"pipeline '{pipeline_name}' "
                    f"in account "
                    f"{actual_account_id}: "
                    f"{exc}"
                )

                continue

        print(
            f"[INFO] Account/Region scan completed: "
            f"{actual_account_id}/"
            f"{region_name} | "
            f"Candidates="
            f"{len(findings)}"
        )

        return {
            "accountId": actual_account_id,

            "region": region_name,

            "success": True,

            "totalPipelinesScanned": len(
                pipelines
            ),

            "totalCandidates": len(
                findings
            ),

            "lookbackDays": LOOKBACK_DAYS,

            "maxExecutionCount": (
                MAX_EXECUTION_COUNT
            ),

            "findings": findings,
        }

    except ClientError as exc:

        print(
            f"[ERROR] AWS error while scanning "
            f"account={target_account_id}, "
            f"region={region_name}: "
            f"{exc}"
        )

        return {
            "accountId": target_account_id,
            "region": region_name,
            "success": False,
            "totalPipelinesScanned": 0,
            "totalCandidates": 0,
            "findings": [],
            "error": str(exc),
        }

    except Exception as exc:

        print(
            f"[ERROR] Unexpected error while scanning "
            f"account={target_account_id}, "
            f"region={region_name}: "
            f"{exc}"
        )

        return {
            "accountId": target_account_id,
            "region": region_name,
            "success": False,
            "totalPipelinesScanned": 0,
            "totalCandidates": 0,
            "findings": [],
            "error": str(exc),
        }


# ============================================================
# 18. MULTI-ACCOUNT / MULTI-REGION SCANNER
# ============================================================

def scan_all_accounts(
    account_ids: List[str],
    regions: List[str],
) -> Dict[str, Any]:
    """
    Scan all configured accounts and Regions.

    Failure in one account/Region does not stop the remaining
    scans.
    """

    base_sts = create_base_sts_client()

    all_findings: List[
        Dict[str, Any]
    ] = []

    account_results: List[
        Dict[str, Any]
    ] = []

    successful_scans = 0

    failed_scans = 0

    total_pipelines = 0

    total_candidates = 0

    # --------------------------------------------------------
    # Remove duplicate accounts and Regions.
    # --------------------------------------------------------

    unique_account_ids = list(
        dict.fromkeys(
            account_ids
        )
    )

    unique_regions = list(
        dict.fromkeys(
            regions
        )
    )

    print(
        f"[INFO] Accounts configured: "
        f"{len(unique_account_ids)}"
    )

    print(
        f"[INFO] Regions configured: "
        f"{len(unique_regions)}"
    )

    # --------------------------------------------------------
    # Scan account -> Region
    # --------------------------------------------------------

    for account_id in unique_account_ids:

        for region_name in unique_regions:

            result = scan_account_region(
                base_sts=base_sts,
                target_account_id=account_id,
                region_name=region_name,
            )

            account_results.append(
                result
            )

            if result.get(
                "success",
                False,
            ):

                successful_scans += 1

                total_pipelines += (
                    result.get(
                        "totalPipelinesScanned",
                        0,
                    )
                )

                total_candidates += (
                    result.get(
                        "totalCandidates",
                        0,
                    )
                )

                all_findings.extend(
                    result.get(
                        "findings",
                        [],
                    )
                )

            else:

                failed_scans += 1

    return {
        "policy": POLICY_NAME,

        "service": SERVICE_NAME,

        "accountsRequested": len(
            unique_account_ids
        ),

        "regionsRequested": len(
            unique_regions
        ),

        "successfulScans": (
            successful_scans
        ),

        "failedScans": (
            failed_scans
        ),

        "totalPipelinesScanned": (
            total_pipelines
        ),

        "totalCandidates": (
            total_candidates
        ),

        "lookbackDays": LOOKBACK_DAYS,

        "maxExecutionCount": (
            MAX_EXECUTION_COUNT
        ),

        "accountResults": account_results,

        "findings": all_findings,
    }


# ============================================================
# 19. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Configure Regions.
    #
    # CodePipeline is Region-specific.
    #
    # Add every Region that needs to be scanned.
    # --------------------------------------------------------

    REGIONS: List[str] = [
        "eu-west-1",
        "us-east-1",
        "ap-south-1",
    ]

    # --------------------------------------------------------
    # Run multi-account / multi-region scan
    # --------------------------------------------------------

    result = scan_all_accounts(
        account_ids=ACCOUNT_IDS,
        regions=REGIONS,
    )

    # --------------------------------------------------------
    # Print raw JSON
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    print(
        "[INFO] FINAL SCAN RESULT"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    export_to_excel(
        findings=result.get(
            "findings",
            [],
        ),
        filename=(
            "codepipeline_low_execution_count.xlsx"
        ),
    )