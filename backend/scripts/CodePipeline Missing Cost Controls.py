from __future__ import annotations

from datetime import datetime, timezone
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

POLICY_NAME = "CodePipeline Missing Cost Controls"

CATEGORY = "CodePipeline Missing Cost Controls"

SERVICE_NAME = "CodePipeline"

EFFORT_LEVEL = "Medium"


# ============================================================
# Cost-control detection configuration
# ============================================================

# Action providers/types that are treated as explicit manual
# approval controls.
#
# CodePipeline Manual approval actions normally use:
#
# category = "Approval"
# owner    = "AWS"
# provider = "Manual"
#
APPROVAL_ACTION_CATEGORY = "Approval"

APPROVAL_ACTION_PROVIDER = "Manual"


# ------------------------------------------------------------
# Tagging detection
# ------------------------------------------------------------
#
# CodePipeline does not provide a dedicated "cost tagging"
# property.
#
# Therefore, tagging is detected from action configuration.
#
# These keywords are intentionally configurable rather than
# hardcoded into the business logic.
# ------------------------------------------------------------

TAGGING_KEYWORDS = [
    "tag",
    "tags",
    "costallocation",
    "cost-allocation",
    "cost_allocation",
    "costtag",
    "cost-tag",
    "cost_tag",
]


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
    Create the STS client using the credentials executing
    this scanner.

    These credentials are used to assume the configured
    read-only role in each target account.
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
    Assume the FinOps read-only role in the target account.
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
# Multi-account configuration
# ============================================================

ACCOUNT_IDS: List[str] = [
    "675134942214",
]


ASSUME_ROLE_NAME = "FinOpsReadOnlyRole"

ASSUME_ROLE_SESSION_NAME = (
    "FinOpsCodePipelineCostControlScanner"
)


# ============================================================
# 7. CREATE TARGET ACCOUNT CLIENTS
# ============================================================

def create_target_account_clients(
    credentials,
    region_name: str,
):
    """
    Create CodePipeline and STS clients using temporary
    credentials from the target account.
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

    Uses the paginator to avoid truncation in large accounts.
    """

    pipelines: List[
        Dict[str, Any]
    ] = []

    paginator = codepipeline.get_paginator(
        "list_pipelines"
    )

    try:

        for page in paginator.paginate():

            pipelines.extend(
                page.get(
                    "pipelines",
                    [],
                )
            )

    except ClientError as exc:

        print(
            f"[ERROR] Failed to list CodePipeline "
            f"pipelines: {exc}"
        )

        raise

    return pipelines


# ============================================================
# 10. FETCH PIPELINE CONFIGURATION
# ============================================================

def fetch_pipeline_configuration(
    codepipeline,
    pipeline_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the complete pipeline definition.

    This is required because cost-control detection depends
    on individual stages and actions.
    """

    try:

        response = (
            codepipeline.get_pipeline(
                name=pipeline_name
            )
        )

        return response.get(
            "pipeline"
        )

    except ClientError as exc:

        print(
            f"[ERROR] Failed to fetch configuration "
            f"for pipeline '{pipeline_name}': "
            f"{exc}"
        )

        raise


# ============================================================
# 11. FLATTEN PIPELINE ACTIONS
# ============================================================

def extract_pipeline_actions(
    pipeline: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract all actions from all pipeline stages.
    """

    actions: List[
        Dict[str, Any]
    ] = []

    stages = pipeline.get(
        "stages",
        [],
    )

    for stage in stages:

        stage_name = stage.get(
            "name",
            "",
        )

        stage_actions = stage.get(
            "actions",
            [],
        )

        for action in stage_actions:

            action_copy = dict(
                action
            )

            action_copy[
                "_stageName"
            ] = stage_name

            actions.append(
                action_copy
            )

    return actions


# ============================================================
# 12. ACTION TEXT EXTRACTION
# ============================================================

def build_action_search_text(
    action: Dict[str, Any],
) -> str:
    """
    Build normalized searchable text from an action.

    This allows tagging detection to work against action
    names, providers, categories and configuration values.
    """

    values: List[str] = []

    values.extend(
        [
            str(
                action.get(
                    "name",
                    "",
                )
            ),
            str(
                action.get(
                    "category",
                    "",
                )
            ),
            str(
                action.get(
                    "owner",
                    "",
                )
            ),
            str(
                action.get(
                    "provider",
                    "",
                )
            ),
            str(
                action.get(
                    "version",
                    "",
                )
            ),
        ]
    )

    configuration = action.get(
        "configuration",
        {},
    )

    if isinstance(
        configuration,
        dict,
    ):

        for key, value in configuration.items():

            values.append(
                str(key)
            )

            values.append(
                str(value)
            )

    return " ".join(
        values
    ).lower()


# ============================================================
# 13. APPROVAL CONTROL DETECTOR
# ============================================================

def has_manual_approval(
    actions: List[Dict[str, Any]],
) -> bool:
    """
    Detect an explicit CodePipeline manual approval action.

    Expected AWS CodePipeline configuration:

        category = Approval
        provider = Manual

    """

    for action in actions:

        category = str(
            action.get(
                "category",
                "",
            )
        )

        provider = str(
            action.get(
                "provider",
                "",
            )
        )

        if (
            category.lower()
            == APPROVAL_ACTION_CATEGORY.lower()
            and
            provider.lower()
            == APPROVAL_ACTION_PROVIDER.lower()
        ):

            return True

    return False


# ============================================================
# 14. COST-TAGGING DETECTOR
# ============================================================

def has_cost_tagging_action(
    actions: List[Dict[str, Any]],
) -> bool:
    """
    Detect whether the pipeline appears to contain a
    cost-tagging action.

    Because CodePipeline has no universal cost-tagging action
    type, this detector searches action metadata and
    configuration for configurable tagging/cost-allocation
    keywords.
    """

    for action in actions:

        searchable_text = (
            build_action_search_text(
                action
            )
        )

        for keyword in TAGGING_KEYWORDS:

            if keyword.lower() in searchable_text:

                return True

    return False


# ============================================================
# 15. BUSINESS LOGIC EVALUATOR
# ============================================================

def evaluate_cost_controls(
    pipeline: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluate the observable cost-control configuration
    of a CodePipeline pipeline.

    A candidate is created only when BOTH:

        1. No manual approval control exists.
        2. No detectable cost-tagging action exists.

    This prevents flagging pipelines that already have one
    of the controls.
    """

    actions = (
        extract_pipeline_actions(
            pipeline
        )
    )

    manual_approval_present = (
        has_manual_approval(
            actions
        )
    )

    cost_tagging_present = (
        has_cost_tagging_action(
            actions
        )
    )

    missing_controls: List[str] = []

    if not manual_approval_present:

        missing_controls.append(
            "manual approval gate"
        )

    if not cost_tagging_present:

        missing_controls.append(
            "automated cost-tagging action"
        )

    candidate = (
        not manual_approval_present
        and
        not cost_tagging_present
    )

    return {
        "candidate": candidate,

        "manualApprovalPresent": (
            manual_approval_present
        ),

        "costTaggingPresent": (
            cost_tagging_present
        ),

        "missingControls": (
            missing_controls
        ),

        "actionCount": len(
            actions
        ),
    }


# ============================================================
# 16. BUILD MESSAGE
# ============================================================

def build_message(
    pipeline_name: str,
    evaluation: Dict[str, Any],
) -> str:
    """
    Build human-readable finding message.
    """

    missing_controls = evaluation.get(
        "missingControls",
        [],
    )

    missing_text = ", ".join(
        missing_controls
    )

    return (
        f"CodePipeline pipeline "
        f"{pipeline_name} does not contain detectable "
        f"cost-control mechanisms. Missing: "
        f"{missing_text}. "
        f"The pipeline should be reviewed to determine "
        f"whether approval gates and cost-tagging controls "
        f"are required for its deployment workflow."
    )


# ============================================================
# 17. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    pipeline_name: str,
) -> str:
    """
    Build remediation instructions.
    """

    return (
        f"Review CodePipeline '{pipeline_name}' with the "
        f"DevOps and application owners. Add an appropriate "
        f"manual approval action before high-impact or "
        f"high-cost deployment stages where required. "
        f"Implement automated resource tagging or "
        f"cost-allocation tagging as part of the deployment "
        f"workflow where supported. Validate the pipeline's "
        f"business and vendor dependencies before modifying "
        f"the production pipeline."
    )


# ============================================================
# 18. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    pipeline: Dict[str, Any],
    evaluation: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build standardized FinOps finding.
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
            evaluation=evaluation,
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

        "actionCount": evaluation.get(
            "actionCount"
        ),

        "manualApprovalPresent": (
            evaluation.get(
                "manualApprovalPresent"
            )
        ),

        "costTaggingPresent": (
            evaluation.get(
                "costTaggingPresent"
            )
        ),

        "missingControls": (
            evaluation.get(
                "missingControls"
            )
        ),
    }


# ============================================================
# 19. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the standard Excel schema.

    Service-specific fields are dynamically added to the
    description column.
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
# 20. SCAN ONE ACCOUNT / REGION
# ============================================================

def scan_account_region(
    base_sts,
    target_account_id: str,
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan CodePipeline cost-control configuration for one
    account and one Region.

    Errors for individual pipelines do not terminate the
    complete scan.
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

        findings: List[
            Dict[str, Any]
        ] = []

        # ----------------------------------------------------
        # Evaluate pipelines
        # ----------------------------------------------------

        for pipeline in pipelines:

            pipeline_name = pipeline.get(
                "name",
                "Unknown",
            )

            try:

                pipeline_configuration = (
                    fetch_pipeline_configuration(
                        codepipeline=codepipeline,
                        pipeline_name=pipeline_name,
                    )
                )

                if not pipeline_configuration:

                    print(
                        f"[WARNING] No configuration "
                        f"returned for pipeline "
                        f"'{pipeline_name}'."
                    )

                    continue

                evaluation = (
                    evaluate_cost_controls(
                        pipeline_configuration
                    )
                )

                print(
                    f"[INFO] Pipeline="
                    f"{pipeline_name} | "
                    f"Actions="
                    f"{evaluation['actionCount']} | "
                    f"ManualApproval="
                    f"{evaluation['manualApprovalPresent']} | "
                    f"CostTagging="
                    f"{evaluation['costTaggingPresent']}"
                )

                if not evaluation[
                    "candidate"
                ]:

                    continue

                finding = build_finding(
                    account_id=actual_account_id,
                    region_name=region_name,
                    pipeline=(
                        pipeline_configuration
                    ),
                    evaluation=evaluation,
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
                    f"{pipeline_name}"
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
# 21. MULTI-ACCOUNT / MULTI-REGION SCANNER
# ============================================================

def scan_all_accounts(
    account_ids: List[str],
    regions: List[str],
) -> Dict[str, Any]:
    """
    Scan every configured account and Region.

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

        "accountResults": account_results,

        "findings": all_findings,
    }


# ============================================================
# 22. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    REGIONS: List[str] = [
        "eu-west-1",
        "us-east-1",
        "ap-south-1",
    ]

    result = scan_all_accounts(
        account_ids=ACCOUNT_IDS,
        regions=REGIONS,
    )

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

    export_to_excel(
        findings=result.get(
            "findings",
            [],
        ),
        filename=(
            "codepipeline_missing_cost_controls.xlsx"
        ),
    )