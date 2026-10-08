from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# 1. AWS CLIENT CONFIGURATION
# ============================================================

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)


# ============================================================
# 2. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "Cloudfront Vpc Origin Idle"

CATEGORY = "Cloudfront Vpc Origin Idle"

SERVICE_NAME = "CloudFront"

EFFORT_LEVEL = "Low"


# CloudFront is a global service.
# CloudFront API operations are normally performed through
# us-east-1.
CLOUDFRONT_REGION = "us-east-1"

GLOBAL_REGION = "global"


# ============================================================
# 3. STANDARD EXCEL COLUMNS
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
# 4. AWS CLIENT CONFIGURATION
# ============================================================

def create_clients(
    region_name: str,
):
    """
    Create CloudFront and STS clients.
    """

    cloudfront = boto3.client(
        "cloudfront",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return cloudfront, sts


def get_account_id(sts) -> str:
    """
    Fetch the AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 5. FETCH ALL CLOUDFRONT DISTRIBUTIONS
# ============================================================

def fetch_all_distributions(
    cloudfront,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudFront distributions using a paginator.
    """

    distributions: List[Dict[str, Any]] = []

    paginator = cloudfront.get_paginator(
        "list_distributions"
    )

    for page in paginator.paginate():

        distribution_list = page.get(
            "DistributionList",
            {},
        )

        items = distribution_list.get(
            "Items",
            [],
        )

        distributions.extend(items)

    return distributions


# ============================================================
# 6. FETCH ALL VPC ORIGINS
# ============================================================

def fetch_all_vpc_origins(
    cloudfront,
) -> List[Dict[str, Any]]:
    """
    Fetch all CloudFront VPC origins.

    Uses the CloudFront list_vpc_origins paginator.
    """

    vpc_origins: List[Dict[str, Any]] = []

    paginator = cloudfront.get_paginator(
        "list_vpc_origins"
    )

    for page in paginator.paginate():

        items = page.get(
            "VpcOriginList",
            {},
        ).get(
            "Items",
            [],
        )

        vpc_origins.extend(
            items
        )

    return vpc_origins


# ============================================================
# 7. FETCH DISTRIBUTION CONFIGURATION
# ============================================================

def get_distribution_config(
    cloudfront,
    distribution_id: str,
) -> Dict[str, Any]:
    """
    Fetch the complete CloudFront distribution configuration.

    The configuration is required because VPC origin references
    are stored in the distribution's origin configuration.
    """

    response = cloudfront.get_distribution_config(
        Id=distribution_id,
    )

    return response.get(
        "DistributionConfig",
        {},
    )


# ============================================================
# 8. EXTRACT VPC ORIGIN REFERENCES
# ============================================================

def extract_vpc_origin_references(
    distribution_config: Dict[str, Any],
) -> List[str]:
    """
    Extract VPC origin IDs referenced by a CloudFront
    distribution.

    CloudFront distributions reference origins through:

        DistributionConfig
            -> Origins
                -> Items
                    -> VpcOriginConfig
                        -> VpcOriginId

    Returns a list of referenced VPC origin IDs.
    """

    referenced_ids: List[str] = []

    origins = (
        distribution_config
        .get("Origins", {})
        .get("Items", [])
    )

    for origin in origins:

        vpc_origin_config = origin.get(
            "VpcOriginConfig"
        )

        if not vpc_origin_config:
            continue

        vpc_origin_id = vpc_origin_config.get(
            "VpcOriginId"
        )

        if vpc_origin_id:
            referenced_ids.append(
                vpc_origin_id
            )

    return referenced_ids


# ============================================================
# 9. BUILD VPC ORIGIN REFERENCE MAP
# ============================================================

def build_vpc_origin_reference_map(
    cloudfront,
    distributions: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """
    Build a mapping:

        VPC Origin ID
            ->
        List of CloudFront Distribution IDs

    Example:

        {
            "vpc-origin-123": [
                "E123ABC",
                "E456XYZ"
            ]
        }

    An empty list means that the VPC origin is not referenced
    by any distribution.
    """

    reference_map: Dict[str, List[str]] = {}

    for distribution in distributions:

        distribution_id = distribution.get(
            "Id"
        )

        if not distribution_id:
            continue

        try:

            distribution_config = (
                get_distribution_config(
                    cloudfront=cloudfront,
                    distribution_id=distribution_id,
                )
            )

            referenced_ids = (
                extract_vpc_origin_references(
                    distribution_config
                )
            )

            for vpc_origin_id in referenced_ids:

                if vpc_origin_id not in reference_map:

                    reference_map[vpc_origin_id] = []

                if (
                    distribution_id
                    not in reference_map[vpc_origin_id]
                ):

                    reference_map[
                        vpc_origin_id
                    ].append(
                        distribution_id
                    )

        except ClientError as exc:

            print(
                f"[ERROR] Unable to inspect distribution "
                f"{distribution_id}: {exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error inspecting "
                f"distribution {distribution_id}: {exc}"
            )

            continue

    return reference_map


# ============================================================
# 10. BUSINESS LOGIC
# ============================================================

def is_candidate(
    vpc_origin: Dict[str, Any],
    reference_map: Dict[str, List[str]],
) -> bool:
    """
    Determine whether a VPC origin is idle.

    Candidate condition:

        VPC Origin exists
        AND
        VPC Origin is not referenced by any distribution
    """

    vpc_origin_id = vpc_origin.get(
        "Id"
    )

    if not vpc_origin_id:
        return False

    referenced_distributions = (
        reference_map.get(
            vpc_origin_id,
            [],
        )
    )

    return len(
        referenced_distributions
    ) == 0


# ============================================================
# 11. BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    vpc_origin: Dict[str, Any],
) -> str:
    """
    Build the human-readable remediation recommendation.
    """

    vpc_origin_id = vpc_origin.get(
        "Id",
        "unknown",
    )

    name = vpc_origin.get(
        "Name",
        vpc_origin_id,
    )

    return (
        f"CloudFront VPC Origin '{name}' "
        f"({vpc_origin_id}) is not attached to any "
        f"CloudFront distribution. Validate that the origin "
        f"is no longer required and delete the unused VPC "
        f"origin."
    )


# ============================================================
# 12. BUILD MESSAGE
# ============================================================

def build_message(
    vpc_origin: Dict[str, Any],
) -> str:
    """
    Build the explanation for why the resource was detected.
    """

    vpc_origin_id = vpc_origin.get(
        "Id",
        "unknown",
    )

    name = vpc_origin.get(
        "Name",
        vpc_origin_id,
    )

    return (
        f"CloudFront VPC Origin '{name}' "
        f"({vpc_origin_id}) is not referenced by any "
        f"CloudFront distribution and may be idle."
    )


# ============================================================
# 13. BUILD FINDING
# ============================================================

def build_finding(
    account_id: str,
    region_name: str,
    vpc_origin: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the standardized FinOps finding.

    Service-specific attributes are retained here and will be
    moved into the description column by export_to_excel().
    """

    vpc_origin_id = vpc_origin.get(
        "Id"
    )

    vpc_origin_name = vpc_origin.get(
        "Name",
        vpc_origin_id,
    )

    vpc_origin_arn = vpc_origin.get(
        "Arn"
    )

    vpc_origin_endpoint_config = (
        vpc_origin.get(
            "VpcOriginEndpointConfig",
            {}
        )
    )

    arn = vpc_origin_endpoint_config.get(
        "Arn"
    )

    http_port = vpc_origin_endpoint_config.get(
        "HTTPPort"
    )

    https_port = vpc_origin_endpoint_config.get(
        "HTTPSPort"
    )

    origin_protocol_policy = (
        vpc_origin_endpoint_config.get(
            "OriginProtocolPolicy"
        )
    )

    creation_time = vpc_origin.get(
        "CreatedTime"
    )

    last_modified_time = vpc_origin.get(
        "LastModifiedTime"
    )

    return {
        # ----------------------------------------------------
        # Standard workflow fields
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": None,

        "title": CATEGORY,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": "AWS Cost Optimization",

        "tags": "CLX",

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS identification
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": vpc_origin_name,

        "resourceId": vpc_origin_id,

        "resourceArn": (
            vpc_origin_arn
            or arn
        ),

        # ----------------------------------------------------
        # Service information
        # ----------------------------------------------------

        "service": SERVICE_NAME,

        "type": "Optimization Description",

        "policy": POLICY_NAME,

        "effortLevel": EFFORT_LEVEL,

        # ----------------------------------------------------
        # Finding explanation
        # ----------------------------------------------------

        "message": build_message(
            vpc_origin
        ),

        "recommendation": build_recommendation(
            vpc_origin
        ),

        # ----------------------------------------------------
        # Cost information
        #
        # CUR/Athena intentionally NOT used.
        # ----------------------------------------------------

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        # ----------------------------------------------------
        # Workflow fields
        # ----------------------------------------------------

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",

        # ----------------------------------------------------
        # Service-specific attributes
        # These will be bundled into description.
        # ----------------------------------------------------

        "vpcOriginId": vpc_origin_id,

        "vpcOriginName": vpc_origin_name,

        "vpcOriginArn": vpc_origin_arn,

        "originArn": arn,

        "httpPort": http_port,

        "httpsPort": https_port,

        "originProtocolPolicy": (
            origin_protocol_policy
        ),

        "creationTime": creation_time,

        "lastModifiedTime": last_modified_time,

        "statusDetails": vpc_origin.get(
            "Status"
        ),
    }


# ============================================================
# 14. EXCEL EXPORTER
# ============================================================

def export_to_excel(
    findings: List[Dict[str, Any]],
    filename: str,
) -> None:
    """
    Export findings using exactly the 30 standard columns.

    Any service-specific attributes are dynamically added to
    the description column.
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
# 15. MAIN SCANNER
# ============================================================

def scan_service(
    region_name: str = CLOUDFRONT_REGION,
) -> Dict[str, Any]:
    """
    Main CloudFront VPC Origin Idle scanner.
    """

    cloudfront, sts = create_clients(
        region_name=region_name,
    )

    account_id = get_account_id(
        sts
    )

    print(
        "[INFO] Fetching CloudFront VPC origins..."
    )

    vpc_origins = fetch_all_vpc_origins(
        cloudfront
    )

    print(
        f"[INFO] VPC origins found: "
        f"{len(vpc_origins)}"
    )

    print(
        "[INFO] Fetching CloudFront distributions..."
    )

    distributions = fetch_all_distributions(
        cloudfront
    )

    print(
        f"[INFO] Distributions found: "
        f"{len(distributions)}"
    )

    print(
        "[INFO] Building VPC origin reference map..."
    )

    reference_map = (
        build_vpc_origin_reference_map(
            cloudfront=cloudfront,
            distributions=distributions,
        )
    )

    findings: List[
        Dict[str, Any]
    ] = []

    candidates = 0

    for vpc_origin in vpc_origins:

        vpc_origin_id = vpc_origin.get(
            "Id"
        )

        try:

            if not is_candidate(
                vpc_origin=vpc_origin,
                reference_map=reference_map,
            ):

                continue

            finding = build_finding(
                account_id=account_id,
                region_name=GLOBAL_REGION,
                vpc_origin=vpc_origin,
            )

            findings.append(
                finding
            )

            candidates += 1

            print(
                f"[FINDING] Idle VPC Origin: "
                f"{vpc_origin_id}"
            )

        except ClientError as exc:

            print(
                f"[ERROR] Failed processing VPC origin "
                f"{vpc_origin_id}: {exc}"
            )

            continue

        except Exception as exc:

            print(
                f"[ERROR] Unexpected error processing "
                f"VPC origin {vpc_origin_id}: {exc}"
            )

            continue

    return {
        "accountId": account_id,

        "region": GLOBAL_REGION,

        "service": SERVICE_NAME,

        "policy": POLICY_NAME,

        "totalVpcOriginsScanned": len(
            vpc_origins
        ),

        "totalDistributionsScanned": len(
            distributions
        ),

        "totalCandidates": candidates,

        "findings": findings,
    }


# ============================================================
# 16. ENTRY POINT
# ============================================================

if __name__ == "__main__":

    region = CLOUDFRONT_REGION

    result = scan_service(
        region_name=region,
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
            "cloudfront_vpc_origin_idle.xlsx"
        ),
    )