
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

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

POLICY_NAME = (
    "cloudformation-stack-with-failed-resources"
)

CATEGORY = (
    "CloudFormation Stack with Failed Resources"
)

SERVICE_NAME = "CloudFormation"

EFFORT_LEVEL = "Medium"


# ============================================================
# FAILED STACK STATES
# ============================================================

FAILED_STACK_STATES = {

    "DELETE_FAILED",

    "CREATE_FAILED",

    "UPDATE_ROLLBACK_FAILED",

    "IMPORT_ROLLBACK_FAILED",

    "UPDATE_FAILED",
}


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):

    cloudformation = boto3.client(
        "cloudformation",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return cloudformation, sts


# ============================================================
# GET ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL CLOUDFORMATION STACKS
# ============================================================

def fetch_all_stacks(
    cloudformation,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudFormation stacks in the region.

    Pagination is handled using the boto3 paginator.
    """

    stacks = []

    paginator = cloudformation.get_paginator(
        "list_stacks"
    )

    for page in paginator.paginate():

        stacks.extend(
            page.get(
                "StackSummaries",
                []
            )
        )

    return stacks


# ============================================================
# FETCH STACK RESOURCES
# ============================================================

def fetch_all_stack_resources(
    cloudformation,
    stack_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch all resources belonging to a CloudFormation stack.

    Pagination is handled automatically.
    """

    resources = []

    paginator = cloudformation.get_paginator(
        "list_stack_resources"
    )

    for page in paginator.paginate(
        StackName=stack_name
    ):

        resources.extend(
            page.get(
                "StackResourceSummaries",
                []
            )
        )

    return resources


# ============================================================
# FETCH STACK EVENTS
# ============================================================

def fetch_stack_events(
    cloudformation,
    stack_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch CloudFormation stack events.

    This is useful for identifying the resources/events
    responsible for DELETE_FAILED or other failures.
    """

    events = []

    paginator = cloudformation.get_paginator(
        "describe_stack_events"
    )

    try:

        for page in paginator.paginate(
            StackName=stack_name
        ):

            events.extend(
                page.get(
                    "StackEvents",
                    []
                )
            )

    except ClientError as e:

        print(
            f"Could not fetch events for "
            f"stack {stack_name}: {e}"
        )

    return events


# ============================================================
# FIND FAILED RESOURCES
# ============================================================

def find_failed_resources(
    resources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Identify resources that are currently in a failed state.

    Examples:

        DELETE_FAILED
        CREATE_FAILED
        UPDATE_FAILED
        IMPORT_FAILED
        DELETE_SKIPPED
    """

    failed_resources = []

    failed_statuses = {

        "DELETE_FAILED",

        "CREATE_FAILED",

        "UPDATE_FAILED",

        "IMPORT_FAILED",

        "UPDATE_ROLLBACK_FAILED",

        "DELETE_SKIPPED",
    }

    for resource in resources:

        status = resource.get(
            "ResourceStatus"
        )

        if status in failed_statuses:

            failed_resources.append(
                resource
            )

    return failed_resources


# ============================================================
# FIND FAILURE EVENTS
# ============================================================

def get_failure_events(
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract CloudFormation events indicating failures.
    """

    failure_events = []

    failure_statuses = {

        "DELETE_FAILED",

        "CREATE_FAILED",

        "UPDATE_FAILED",

        "IMPORT_FAILED",

        "UPDATE_ROLLBACK_FAILED",
    }

    for event in events:

        status = event.get(
            "ResourceStatus"
        )

        if status in failure_statuses:

            failure_events.append(
                event
            )

    return failure_events


# ============================================================
# CALCULATE STACK AGE
# ============================================================

def calculate_age_days(
    creation_time: datetime | None,
) -> float | None:

    if creation_time is None:
        return None

    if creation_time.tzinfo is None:

        creation_time = (
            creation_time.replace(
                tzinfo=timezone.utc
            )
        )

    now = datetime.now(
        timezone.utc
    )

    age_days = (
        now - creation_time
    ).total_seconds() / 86400

    if age_days < 0:
        return 0.0

    return round(
        age_days,
        2,
    )


# ============================================================
# GET STACK ARN
# ============================================================

def get_stack_arn(
    stack: Dict[str, Any],
) -> str | None:

    return stack.get(
        "StackId"
    )


# ============================================================
# GET RESOURCE ID
# ============================================================

def get_resource_id(
    resource: Dict[str, Any],
) -> str | None:

    physical_id = resource.get(
        "PhysicalResourceId"
    )

    if physical_id:
        return physical_id

    return resource.get(
        "LogicalResourceId"
    )


# ============================================================
# GET RESOURCE ARN
# ============================================================

def get_resource_arn(
    resource: Dict[str, Any],
) -> str | None:

    physical_id = resource.get(
        "PhysicalResourceId"
    )

    if not physical_id:
        return None

    # PhysicalResourceId is not always an ARN.
    # If it already is an ARN, return it directly.

    if physical_id.startswith(
        "arn:"
    ):

        return physical_id

    return None


# ============================================================
# COST PLACEHOLDER
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    resource_id: str | None,
    resource_arn: str | None,
) -> Dict[str, Any]:
    """
    Cost integration point.

    Cost should eventually come from:

        CUR
          ↓
        Athena
          ↓
        Resource-level cost

    Do not calculate CloudFormation cost itself.

    CloudFormation is primarily the orchestration layer.
    The actual cost normally belongs to the underlying
    AWS resource.
    """

    return {

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,
    }


# ============================================================
# BUILD FAILURE MESSAGE
# ============================================================

def build_failure_message(
    stack_name: str,
    stack_status: str,
    failed_resources: List[Dict[str, Any]],
) -> str:

    failed_count = len(
        failed_resources
    )

    if failed_count == 0:

        return (

            f"CloudFormation stack "
            f"{stack_name} "
            f"({stack_status}) has failed "
            f"resource state but no currently "
            f"identified failed resources."
        )

    resource_names = []

    for resource in failed_resources:

        logical_id = resource.get(
            "LogicalResourceId",
            "Unknown"
        )

        resource_type = resource.get(
            "ResourceType",
            "Unknown"
        )

        physical_id = resource.get(
            "PhysicalResourceId",
            "Unknown"
        )

        resource_names.append(

            f"{logical_id} "
            f"({resource_type}, "
            f"{physical_id})"
        )

    resources_text = (
        "; ".join(
            resource_names
        )
    )

    return (

        f"CloudFormation stack "
        f"{stack_name} "
        f"({stack_status}) has "
        f"{failed_count} failed resource(s): "
        f"{resources_text}. "
        f"Clean up failed resources, "
        f"delete the stack, or resolve the "
        f"underlying issue to avoid lingering "
        f"resources, costs, and infrastructure "
        f"complexity."
    )


# ============================================================
# BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    stack_name: str,
    stack_status: str,
    failed_resources: List[Dict[str, Any]],
) -> str:

    if stack_status == "DELETE_FAILED":

        return (

            f"CloudFormation stack {stack_name} "
            f"could not be deleted successfully. "
            f"Review the failed resource(s), "
            f"determine why deletion failed, and "
            f"manually clean up resources that are "
            f"no longer required. After cleanup, "
            f"remove or repair the CloudFormation "
            f"stack."
        )

    if stack_status == "CREATE_FAILED":

        return (

            f"CloudFormation stack {stack_name} "
            f"failed during creation. Review the "
            f"failed resources and CloudFormation "
            f"events. Delete unused resources and "
            f"repair the template before attempting "
            f"deployment again."
        )

    if stack_status == "UPDATE_ROLLBACK_FAILED":

        return (

            f"CloudFormation stack {stack_name} "
            f"is in UPDATE_ROLLBACK_FAILED state. "
            f"Review failed resources and stack "
            f"events, resolve the underlying issue, "
            f"and complete or continue the rollback "
            f"before leaving resources unmanaged."
        )

    return (

        f"CloudFormation stack {stack_name} "
        f"is in {stack_status} state. Review the "
        f"failed resources and CloudFormation "
        f"events, then clean up or repair resources "
        f"that are no longer required."
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_stack_finding(
    stack: Dict[str, Any],
    failed_resources: List[Dict[str, Any]],
    failure_events: List[Dict[str, Any]],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    stack_name = stack.get(
        "StackName"
    )

    stack_status = stack.get(
        "StackStatus"
    )

    stack_arn = get_stack_arn(
        stack
    )

    creation_time = stack.get(
        "CreationTime"
    )

    last_updated_time = stack.get(
        "LastUpdatedTime"
    )

    age_days = calculate_age_days(
        creation_time
    )

    # --------------------------------------------------------
    # Cost
    #
    # CloudFormation itself is not normally the cost-bearing
    # resource. The cost should be matched against the
    # underlying failed resources using CUR + Athena.
    # --------------------------------------------------------

    stack_cost = get_resource_cost(

        account_id=account_id,

        region_name=region_name,

        resource_id=stack_name,

        resource_arn=stack_arn,
    )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = build_recommendation(

        stack_name=stack_name,

        stack_status=stack_status,

        failed_resources=failed_resources,
    )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = build_failure_message(

        stack_name=stack_name,

        stack_status=stack_status,

        failed_resources=failed_resources,
    )

    # --------------------------------------------------------
    # Failed resource details
    # --------------------------------------------------------

    failed_resource_details = []

    for resource in failed_resources:

        failed_resource_details.append({

            "logicalResourceId": (
                resource.get(
                    "LogicalResourceId"
                )
            ),

            "physicalResourceId": (
                resource.get(
                    "PhysicalResourceId"
                )
            ),

            "resourceType": (
                resource.get(
                    "ResourceType"
                )
            ),

            "resourceStatus": (
                resource.get(
                    "ResourceStatus"
                )
            ),

            "resourceStatusReason": (
                resource.get(
                    "ResourceStatusReason"
                )
            ),
        })

    # --------------------------------------------------------
    # Failure event details
    # --------------------------------------------------------

    failure_event_details = []

    for event in failure_events:

        failure_event_details.append({

            "logicalResourceId": (
                event.get(
                    "LogicalResourceId"
                )
            ),

            "physicalResourceId": (
                event.get(
                    "PhysicalResourceId"
                )
            ),

            "resourceType": (
                event.get(
                    "ResourceType"
                )
            ),

            "resourceStatus": (
                event.get(
                    "ResourceStatus"
                )
            ),

            "resourceStatusReason": (
                event.get(
                    "ResourceStatusReason"
                )
            ),

            "timestamp": (
                event.get(
                    "Timestamp"
                ).isoformat()
                if event.get(
                    "Timestamp"
                )
                else None
            ),
        })

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceName: {stack_name} | "

        f"stackArn: {stack_arn} | "

        f"category: {CATEGORY} | "

        f"stackStatus: {stack_status} | "

        f"failedResources: "
        f"{len(failed_resources)} | "

        f"stackAgeDays: "
        f"{age_days} | "

        f"currentCostDaily: "
        f"{stack_cost['currentDailyCost']} | "

        f"currentCostMonthly: "
        f"{stack_cost['currentMonthlyCost']} | "

        f"type: CloudFormation Failed Resources | "

        f"policy: {POLICY_NAME} | "

        f"effortLevel: {EFFORT_LEVEL} | "

        f"message: {message} | "

        f"recommendation: {recommendation}"
    )

    # --------------------------------------------------------
    # Return finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORKFLOW
        # ====================================================

        "workItemType": "Task",

        "state": "To Do",

        "id": "",

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": (
            "AWS Cost Optimization"
        ),

        "tags": "",

        "commentCount": 0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": stack_name,

        "resourceId": stack_name,

        "resourceArn": stack_arn,

        "service": SERVICE_NAME,

        # ====================================================
        # CLOUDFORMATION
        # ====================================================

        "stackName": stack_name,

        "stackArn": stack_arn,

        "stackStatus": stack_status,

        "stackStatusReason": (
            stack.get(
                "StackStatusReason"
            )
        ),

        "creationTime": (

            creation_time.isoformat()

            if creation_time

            else None
        ),

        "lastUpdatedTime": (

            last_updated_time.isoformat()

            if last_updated_time

            else None
        ),

        "ageDays": age_days,

        # ====================================================
        # FAILED RESOURCES
        # ====================================================

        "failedResourceCount": (
            len(
                failed_resources
            )
        ),

        "failedResources": (
            failed_resource_details
        ),

        # ====================================================
        # FAILURE EVENTS
        # ====================================================

        "failureEventCount": (
            len(
                failure_events
            )
        ),

        "failureEvents": (
            failure_event_details
        ),

        # ====================================================
        # FINOPS
        # ====================================================

        "type": (
            "CloudFormation Failed Resources"
        ),

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        "message": message,

        "recommendation": recommendation,

        "description": description,

        # ====================================================
        # COST
        # ====================================================

        "currentDailyCost": (
            stack_cost[
                "currentDailyCost"
            ]
        ),

        "currentMonthlyCost": (
            stack_cost[
                "currentMonthlyCost"
            ]
        ),

        "estimatedMonthlySavings": (
            stack_cost[
                "estimatedMonthlySavings"
            ]
        ),

        # ====================================================
        # WORKFLOW
        # ====================================================

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": "",
    }


# ============================================================
# SCAN CLOUDFORMATION STACK
# ============================================================

def scan_stack(
    cloudformation,
    stack: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any] | None:

    stack_name = stack.get(
        "StackName"
    )

    stack_status = stack.get(
        "StackStatus"
    )

    # --------------------------------------------------------
    # Only inspect failed states
    # --------------------------------------------------------

    if stack_status not in (
        FAILED_STACK_STATES
    ):

        return None

    print(
        f"\nScanning failed stack: "
        f"{stack_name}"
    )

    print(
        f"Status: {stack_status}"
    )

    # --------------------------------------------------------
    # Fetch all stack resources
    # --------------------------------------------------------

    resources = (
        fetch_all_stack_resources(

            cloudformation,

            stack_name,
        )
    )

    print(
        f"Total resources: "
        f"{len(resources)}"
    )

    # --------------------------------------------------------
    # Find failed resources
    # --------------------------------------------------------

    failed_resources = (
        find_failed_resources(
            resources
        )
    )

    print(
        f"Failed resources: "
        f"{len(failed_resources)}"
    )

    # --------------------------------------------------------
    # Fetch stack events
    # --------------------------------------------------------

    events = fetch_stack_events(

        cloudformation,

        stack_name,
    )

    # --------------------------------------------------------
    # Extract failure events
    # --------------------------------------------------------

    failure_events = (
        get_failure_events(
            events
        )
    )

    print(
        f"Failure events: "
        f"{len(failure_events)}"
    )

    # --------------------------------------------------------
    # Build finding
    # --------------------------------------------------------

    finding = build_stack_finding(

        stack=stack,

        failed_resources=(
            failed_resources
        ),

        failure_events=(
            failure_events
        ),

        account_id=account_id,

        region_name=region_name,
    )

    return finding


# ============================================================
# SCAN ALL CLOUDFORMATION STACKS
# ============================================================

def scan_cloudformation_stacks(
    region_name: str,
) -> Dict[str, Any]:

    cloudformation, sts = (
        create_clients(
            region_name
        )
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"\nAccount ID: "
        f"{account_id}"
    )

    print(
        f"Region: "
        f"{region_name}"
    )

    # --------------------------------------------------------
    # Fetch ALL stacks
    # --------------------------------------------------------

    stacks = fetch_all_stacks(
        cloudformation
    )

    print(
        f"Total CloudFormation stacks: "
        f"{len(stacks)}"
    )

    findings = []

    failed_stacks_scanned = 0

    # --------------------------------------------------------
    # Process stacks
    # --------------------------------------------------------

    for stack in stacks:

        stack_status = stack.get(
            "StackStatus"
        )

        if stack_status not in (
            FAILED_STACK_STATES
        ):

            continue

        failed_stacks_scanned += 1

        try:

            finding = scan_stack(

                cloudformation=(
                    cloudformation
                ),

                stack=stack,

                account_id=(
                    account_id
                ),

                region_name=(
                    region_name
                ),
            )

            if finding:

                findings.append(
                    finding
                )

        except Exception as e:

            print(
                f"Error scanning stack "
                f"{stack.get('StackName')}: "
                f"{e}"
            )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalStacksScanned": (
            len(stacks)
        ),

        "failedStacksScanned": (
            failed_stacks_scanned
        ),

        "totalFindings": (
            len(findings)
        ),

        "findings": findings,
    }


# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
):
    STANDARD_COLUMNS = [
        "workItemType", "state", "id", "title", "category", "owner",
        "assignedTo", "status", "areaPath", "tags", "commentCount",
        "accountId", "region", "resourceNameOrId", "resourceId",
        "resourceArn", "service", "type", "policy", "effortLevel",
        "message", "recommendation", "description", "currentDailyCost",
        "currentMonthlyCost", "estimatedMonthlySavings", "approvalComments",
        "reasonForRejection", "achievedSavingsMonthly", "month"
    ]

    flat_findings = []
    
    # Handle single dictionary (like Snapshot.py) or list of dictionaries
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        # 1. Separate standard columns from extra attributes
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
                import json
                str_val = json.dumps(value, default=str)
            else:
                str_val = value

            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                # Capture extra attributes
                extra_attributes.append(f"{key}: {str_val}")
                
        # 2. Build final standard row
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        
        # Populate standard values
        for k, v in flat_finding.items():
            standard_row[k] = v
            
        # 3. Append extra attributes to description
        existing_desc = standard_row.get("description", "")
        if existing_desc is None:
            existing_desc = ""
            
        if extra_attributes:
            extra_str = " | ".join(extra_attributes)
            if existing_desc:
                standard_row["description"] = f"{existing_desc} | {extra_str}"
            else:
                standard_row["description"] = extra_str
                
        flat_findings.append(standard_row)

    import pandas as pd
    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)

    df.to_excel(
        filename,
        index=False
    )

    print(f"\\nExcel report created:\\n{filename}")


if __name__ == "__main__":

    # --------------------------------------------------------
    # Only REGION is supplied.
    #
    # CloudFormation stacks are discovered automatically.
    # --------------------------------------------------------

    region = "eu-west-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS CLOUDFORMATION FAILED STACK SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Policy: {POLICY_NAME}"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_cloudformation_stacks(
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
        "Total Stacks:",
        result.get(
            "totalStacksScanned"
        )
    )

    print(
        "Failed Stacks:",
        result.get(
            "failedStacksScanned"
        )
    )

    print(
        "Findings:",
        result.get(
            "totalFindings"
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
            "\nNo CloudFormation failed-resource "
            "findings found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "cloudformation_failed_resources_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

