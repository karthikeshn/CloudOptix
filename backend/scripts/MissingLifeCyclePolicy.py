
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# CONFIGURATION
# ============================================================

IMAGE_AGE_THRESHOLD_DAYS = 90


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
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):

    ecr = boto3.client(
        "ecr",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return ecr, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL ECR REPOSITORIES
# ============================================================

def fetch_all_ecr_repositories(
    ecr,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL ECR repositories
    in the specified region.

    Pagination is handled using boto3 paginator.
    """

    repositories = []

    paginator = ecr.get_paginator(
        "describe_repositories"
    )

    for page in paginator.paginate():

        page_repositories = page.get(
            "repositories",
            []
        )

        repositories.extend(
            page_repositories
        )

    return repositories


# ============================================================
# FETCH ALL IMAGES IN A REPOSITORY
# ============================================================

def fetch_all_repository_images(
    ecr,
    repository_name: str,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL images in an ECR repository.

    Pagination is handled using boto3 paginator.
    """

    images = []

    paginator = ecr.get_paginator(
        "describe_images"
    )

    for page in paginator.paginate(
        repositoryName=repository_name
    ):

        page_images = page.get(
            "imageDetails",
            []
        )

        images.extend(
            page_images
        )

    return images


# ============================================================
# FETCH REPOSITORY TAGS
# ============================================================

def fetch_repository_tags(
    ecr,
    repository_arn: str,
) -> Dict[str, str]:
    """
    Fetch tags attached to an ECR repository.
    """

    try:

        response = ecr.list_tags_for_resource(
            resourceArn=repository_arn
        )

        tags = response.get(
            "tags",
            []
        )

        return {
            tag["Key"]: tag.get(
                "Value",
                ""
            )
            for tag in tags
            if "Key" in tag
        }

    except ClientError:

        return {}


# ============================================================
# CHECK LIFECYCLE POLICY
# ============================================================

def check_lifecycle_policy(
    ecr,
    repository_name: str,
) -> Dict[str, Any]:
    """
    Check whether the repository has an ECR
    lifecycle policy.

    Returns:
        exists
        policyText
        lastEvaluatedAt
    """

    try:

        response = ecr.get_lifecycle_policy(
            repositoryName=repository_name
        )

        last_evaluated_at = response.get(
            "lastEvaluatedAt"
        )

        return {

            "exists": True,

            "policyText": response.get(
                "lifecyclePolicyText"
            ),

            "lastEvaluatedAt": (
                last_evaluated_at.isoformat()
                if last_evaluated_at
                else None
            ),
        }

    except ecr.exceptions.LifecyclePolicyNotFoundException:

        return {

            "exists": False,

            "policyText": None,

            "lastEvaluatedAt": None,
        }

    except ClientError as error:

        error_code = (
            error.response
            .get("Error", {})
            .get("Code", "")
        )

        if (
            error_code
            == "LifecyclePolicyNotFoundException"
        ):

            return {

                "exists": False,

                "policyText": None,

                "lastEvaluatedAt": None,
            }

        raise


# ============================================================
# CALCULATE IMAGE AGE
# ============================================================

def calculate_age_days(
    pushed_at: datetime | None,
) -> float | None:
    """
    Calculate how many days an image has existed
    since imagePushedAt.
    """

    if pushed_at is None:
        return None

    if pushed_at.tzinfo is None:

        pushed_at = pushed_at.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(
        timezone.utc
    )

    age_days = (
        now - pushed_at
    ).total_seconds() / 86400

    return round(
        age_days,
        2
    )


# ============================================================
# ANALYZE ECR IMAGES
# ============================================================

def analyze_images(
    images: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyze all images in the repository.

    Calculates:

        Total images
        Images older than 90 days
        Untagged images
        Total image storage
        Storage occupied by old images
    """

    total_size_bytes = 0

    old_images = []

    untagged_images = []

    image_details = []

    for image in images:

        image_digest = image.get(
            "imageDigest"
        )

        image_tags = image.get(
            "imageTags",
            []
        )

        pushed_at = image.get(
            "imagePushedAt"
        )

        image_size_bytes = image.get(
            "imageSizeInBytes",
            0
        )

        age_days = calculate_age_days(
            pushed_at
        )

        total_size_bytes += (
            image_size_bytes
        )

        image_info = {

            "imageDigest": image_digest,

            "imageTags": image_tags,

            "imagePushedAt": (
                pushed_at.isoformat()
                if pushed_at
                else None
            ),

            "ageDays": age_days,

            "imageSizeBytes": (
                image_size_bytes
            ),

            "imageSizeMB": round(
                image_size_bytes
                / (1024 * 1024),
                2,
            ),

            "imageSizeGB": round(
                image_size_bytes
                / (1024 ** 3),
                4,
            ),

            "mediaType": image.get(
                "imageManifestMediaType"
            ),

            "artifactMediaType": image.get(
                "artifactMediaType"
            ),

            "scanStatus": (
                image.get(
                    "imageScanStatus",
                    {}
                ).get(
                    "status"
                )
            ),
        }

        image_details.append(
            image_info
        )

        # ----------------------------------------------------
        # IMAGE OLDER THAN 90 DAYS
        # ----------------------------------------------------

        if (
            age_days is not None
            and age_days
            > IMAGE_AGE_THRESHOLD_DAYS
        ):

            old_images.append(
                image_info
            )

        # ----------------------------------------------------
        # UNTAGGED IMAGE
        # ----------------------------------------------------

        if not image_tags:

            untagged_images.append(
                image_info
            )

    # --------------------------------------------------------
    # Calculate storage
    # --------------------------------------------------------

    old_size_bytes = sum(
        image.get(
            "imageSizeBytes",
            0
        )
        for image in old_images
    )

    return {

        "totalImages": len(
            images
        ),

        "oldImageCount": len(
            old_images
        ),

        "untaggedImageCount": len(
            untagged_images
        ),

        "totalSizeBytes": (
            total_size_bytes
        ),

        "totalSizeGB": round(
            total_size_bytes
            / (1024 ** 3),
            4,
        ),

        "oldImageSizeBytes": (
            old_size_bytes
        ),

        "oldImageSizeGB": round(
            old_size_bytes
            / (1024 ** 3),
            4,
        ),

        "oldImages": old_images,

        "untaggedImages": (
            untagged_images
        ),

        "imageDetails": (
            image_details
        ),
    }


# ============================================================
# CUR + ATHENA COST PLACEHOLDER
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    resource_arn: str,
) -> Dict[str, Any]:
    """
    COST DATA WILL COME FROM CUR + ATHENA.

    This function intentionally does NOT calculate
    cost using ECR image size or a hardcoded price.

    Later this function should query Athena and return:

        currentDailyCost
        currentMonthlyCost
        estimatedMonthlySavings
    """

    return {

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,
    }


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_ecr_finding(
    repository: Dict[str, Any],
    account_id: str,
    region_name: str,
    lifecycle_policy: Dict[str, Any],
    image_analysis: Dict[str, Any],
    tags: Dict[str, str],
) -> Dict[str, Any]:

    repository_name = repository[
        "repositoryName"
    ]

    repository_arn = repository[
        "repositoryArn"
    ]

    repository_uri = repository.get(
        "repositoryUri"
    )

    created_at = repository.get(
        "createdAt"
    )

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    cost = get_resource_cost(
        account_id=account_id,
        region_name=region_name,
        resource_arn=repository_arn,
    )

    # --------------------------------------------------------
    # FinOps policy
    # --------------------------------------------------------

    policy = (
        "ecr-missing-lifecycle-policy"
    )

    has_policy = lifecycle_policy["exists"]
    
    total_images = image_analysis.get("totalImages", 0)
    old_image_count = image_analysis.get("oldImageCount", 0)
    old_image_size_gb = image_analysis.get("oldImageSizeGB", 0)
    untagged_image_count = image_analysis.get("untaggedImageCount", 0)

    if not has_policy:
        finding_type = "Missing Lifecycle Policy"
        effort_level = "Low"
        status = "Review Required"
        recommendation = (
            f"Create an ECR lifecycle policy to automatically clean up eligible "
            f"images older than {IMAGE_AGE_THRESHOLD_DAYS} days."
        )
        message = (
            f"ECR repository '{repository_name}' does not have a lifecycle policy. "
            f"The repository contains {total_images} images. "
            f"{old_image_count} images are older than {IMAGE_AGE_THRESHOLD_DAYS} days, "
            f"with approximately {old_image_size_gb} GB of image storage. "
            f"Untagged images: {untagged_image_count}. "
            f"Consider creating a lifecycle policy to automatically clean up old images."
        )
    else:
        finding_type = "Has Lifecycle Policy"
        effort_level = "None"
        status = "Optimized"
        recommendation = "Repository has a lifecycle policy. Keep."
        message = f"ECR repository '{repository_name}' has a lifecycle policy."

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {repository_name} | "

        f"arn: {repository_arn} | "

        f"Type: {finding_type} | "

        f"policy: {policy} | "

        f"message: {message} | "

        f"effortLevel: {effort_level} | "

        f"imageCount: {total_images} | "

        f"oldImages90Days: "
        f"{old_image_count} | "

        f"oldImageStorageGB: "
        f"{old_image_size_gb} | "

        f"untaggedImages: "
        f"{untagged_image_count}"
    )

    # --------------------------------------------------------
    # Return finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORKFLOW
        # ====================================================

        "workItemType": "Task",
        "title": "AWS ECR Lifecycle Policy Check",
        "category": "AWS ECR Lifecycle Policy Check",
        "owner": "",
        "assignedTo": "",
        "status": status,

        "areaPath": (
            "AWS Cost Optimization"
        ),

        "tags": tags,

        "commentCount": 0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceId": repository_name,

        "resourceArn": repository_arn,

        "service": "ECR",

        # ====================================================
        # REPOSITORY
        # ====================================================

        "repositoryName": repository_name,

        "repositoryUri": repository_uri,

        "repositoryCreatedAt": (
            created_at.isoformat()
            if created_at
            else None
        ),

        # ====================================================
        # IMAGE INFORMATION
        # ====================================================

        "imageCount": total_images,

        "totalImageStorageGB": (
            image_analysis[
                "totalSizeGB"
            ]
        ),

        "imagesOlderThan90Days": (
            old_image_count
        ),

        "oldImageStorageGB": (
            old_image_size_gb
        ),

        "untaggedImageCount": (
            untagged_image_count
        ),

        # ====================================================
        # LIFECYCLE POLICY
        # ====================================================

        "hasLifecyclePolicy": (
            lifecycle_policy[
                "exists"
            ]
        ),

        "lifecyclePolicy": (
            lifecycle_policy[
                "policyText"
            ]
        ),

        "lifecyclePolicyLastEvaluated": (
            lifecycle_policy[
                "lastEvaluatedAt"
            ]
        ),

        # ====================================================
        # FINOPS
        # ====================================================

        "type": finding_type,

        "policy": policy,

        "effortLevel": effort_level,

        "recommendation": recommendation,

        "message": message,

        "description": description,

        # ====================================================
        # COST
        # ====================================================

        "currentDailyCost": (
            cost[
                "currentDailyCost"
            ]
        ),

        "currentMonthlyCost": (
            cost[
                "currentMonthlyCost"
            ]
        ),

        "estimatedMonthlySavings": (
            cost[
                "estimatedMonthlySavings"
            ]
        ),

        # ====================================================
        # APPROVAL
        # ====================================================

        "approvalComments": "",
    }


# ============================================================
# SCAN ALL ECR REPOSITORIES
# ============================================================

def scan_ecr_repositories(
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan all ECR repositories in a region.
    """

    ecr, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Automatically discover repositories
    # --------------------------------------------------------

    repositories = (
        fetch_all_ecr_repositories(
            ecr
        )
    )

    findings = []

    # Optional inventory containing ALL repositories.
    inventory = []

    # --------------------------------------------------------
    # Process every repository
    # --------------------------------------------------------

    for repository in repositories:

        repository_name = repository[
            "repositoryName"
        ]

        repository_arn = repository[
            "repositoryArn"
        ]

        # ----------------------------------------------------
        # Fetch repository tags
        # ----------------------------------------------------

        tags = fetch_repository_tags(
            ecr,
            repository_arn,
        )

        # ----------------------------------------------------
        # Check lifecycle policy
        # ----------------------------------------------------

        lifecycle_policy = (
            check_lifecycle_policy(
                ecr,
                repository_name,
            )
        )

        # ----------------------------------------------------
        # Fetch all images
        # ----------------------------------------------------

        images = (
            fetch_all_repository_images(
                ecr,
                repository_name,
            )
        )

        # ----------------------------------------------------
        # Analyze images
        # ----------------------------------------------------

        image_analysis = analyze_images(
            images
        )

        # ----------------------------------------------------
        # Store complete repository inventory
        # ----------------------------------------------------

        inventory.append({

            "repositoryName": (
                repository_name
            ),

            "repositoryArn": (
                repository_arn
            ),

            "repositoryUri": (
                repository.get(
                    "repositoryUri"
                )
            ),

            "tags": tags,

            "hasLifecyclePolicy": (
                lifecycle_policy[
                    "exists"
                ]
            ),

            "imageCount": (
                image_analysis[
                    "totalImages"
                ]
            ),

            "totalImageStorageGB": (
                image_analysis[
                    "totalSizeGB"
                ]
            ),

            "imagesOlderThan90Days": (
                image_analysis[
                    "oldImageCount"
                ]
            ),

            "oldImageStorageGB": (
                image_analysis[
                    "oldImageSizeGB"
                ]
            ),

            "untaggedImageCount": (
                image_analysis[
                    "untaggedImageCount"
                ]
            ),
        })

        # ----------------------------------------------------
        # FINOPS RULE
        # ----------------------------------------------------

        finding = build_ecr_finding(
            repository=repository,
            account_id=account_id,
            region_name=region_name,
            lifecycle_policy=lifecycle_policy,
            image_analysis=image_analysis,
            tags=tags,
        )

        findings.append(finding)

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalRepositoriesScanned": (
            len(repositories)
        ),

        "totalRepositoriesMissingLifecyclePolicy": (
            len(findings)
        ),

        "findings": findings,

        "repositoryInventory": inventory,
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


def main():
    print("\nStarting FinOps Policy: ECR Lifecycle Policy Check")

    # Get regions
    ecr_base, sts_base = create_clients("us-east-1")
    account_id = get_account_id(sts_base)
    print(f"Account ID: {account_id}")

    try:
        ec2_client = boto3.client("ec2", region_name="us-east-1")
        regions_response = ec2_client.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        print(f"Failed to fetch AWS regions: {e}")
        return

    print(f"Discovered {len(regions)} regions to scan.")

    all_repositories = 0
    all_findings = []

    for region in regions:
        print(f"\n========================================")
        print(f"Scanning region: {region}")
        print(f"========================================")

        try:
            result = scan_ecr_repositories(region)
            repos_in_region = result.get("totalRepositoriesScanned", 0)
            findings_in_region = result.get("findings", [])
            
            all_repositories += repos_in_region
            all_findings.extend(findings_in_region)
            
            print(f"Evaluated {repos_in_region} repositories in {region}")
        except Exception as e:
            print(f"Failed to scan region {region}: {e}")

    # Export
    excel_file = "ecr_lifecycle_policy_report.xlsx"
    export_to_excel(
        findings=all_findings,
        filename=excel_file,
    )

    print("\n==================================================")
    print("SCAN COMPLETED")
    print(f"Total Regions Scanned: {len(regions)}")
    print(f"Total Repositories Evaluated: {all_repositories}")
    print(f"Total Findings Exported: {len(all_findings)}")
    print("==================================================")

if __name__ == "__main__":
    main()
