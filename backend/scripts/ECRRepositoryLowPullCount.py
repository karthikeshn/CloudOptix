
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import pandas as pd
import json


# ============================================================
# CONFIGURATION
# ============================================================

# Number of days used to determine repository pull activity.
PULL_ACTIVITY_DAYS = 90

# Repository is considered low-pull when pull count is
# less than or equal to this value.
LOW_PULL_THRESHOLD = 0

# Number of latest images to keep.
KEEP_LATEST_IMAGES = 30


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

    cloudtrail = boto3.client(
        "cloudtrail",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return ecr, cloudtrail, sts


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
# FETCH ALL IMAGES IN REPOSITORY
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
    Fetch tags attached to the ECR repository.
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
# CALCULATE AGE
# ============================================================

def calculate_age_days(
    date_value: datetime | None,
) -> float | None:
    """
    Calculate age in days from the supplied datetime.
    """

    if date_value is None:
        return None

    if date_value.tzinfo is None:

        date_value = date_value.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(
        timezone.utc
    )

    age_days = (
        now - date_value
    ).total_seconds() / 86400

    return round(
        age_days,
        2
    )


# ============================================================
# GET IMAGE PUSH DATE
# ============================================================

def get_image_push_date(
    image: Dict[str, Any],
) -> datetime | None:

    return image.get(
        "imagePushedAt"
    )


# ============================================================
# SORT IMAGES BY PUSH DATE
# ============================================================

def sort_images_latest_first(
    images: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Sort images from newest to oldest.

    Images without a push date are placed at the end.
    """

    return sorted(
        images,
        key=lambda image: (
            image.get(
                "imagePushedAt"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )


# ============================================================
# GET LATEST IMAGES
# ============================================================

def get_latest_images(
    images: List[Dict[str, Any]],
    keep_count: int = KEEP_LATEST_IMAGES,
) -> List[Dict[str, Any]]:
    """
    Return the latest N images based on imagePushedAt.
    """

    sorted_images = (
        sort_images_latest_first(
            images
        )
    )

    return sorted_images[
        :keep_count
    ]


# ============================================================
# GET OLDER IMAGES
# ============================================================

def get_images_older_than_latest(
    images: List[Dict[str, Any]],
    keep_count: int = KEEP_LATEST_IMAGES,
) -> List[Dict[str, Any]]:
    """
    Return images outside the latest N images.

    Example:

        Total images = 50
        Keep latest = 30

        Returns 20 older images.
    """

    sorted_images = (
        sort_images_latest_first(
            images
        )
    )

    return sorted_images[
        keep_count:
    ]


# ============================================================
# CLOUDTRAIL EVENT NAME
# ============================================================

def is_ecr_pull_event(
    event_name: str,
) -> bool:
    """
    Determine whether a CloudTrail event represents
    an ECR image pull-related operation.

    ECR image pull activity can involve several API
    operations depending on the client and workflow.

    The primary data-plane API calls associated with
    pulling images are included here.
    """

    pull_events = {

        "BatchGetImage",

        "GetDownloadUrlForLayer",

        "BatchCheckLayerAvailability",
    }

    return event_name in pull_events


# ============================================================
# EXTRACT REPOSITORY FROM CLOUDTRAIL EVENT
# ============================================================

def extract_repository_from_event(
    event: Dict[str, Any],
) -> str | None:
    """
    Extract repository name from CloudTrail event.

    Different ECR events may represent the repository
    in different parts of the request parameters.
    """

    request_parameters = event.get(
        "requestParameters",
        {}
    )

    if not request_parameters:
        return None

    repository_name = (
        request_parameters.get(
            "repositoryName"
        )
    )

    return repository_name


# ============================================================
# FETCH ECR PULL ACTIVITY
# ============================================================

def fetch_repository_pull_activity(
    cloudtrail,
    repository_name: str,
    region_name: str,
    days: int = PULL_ACTIVITY_DAYS,
) -> Dict[str, Any]:
    """
    Fetch ECR pull-related CloudTrail events for
    a repository during the last N days.

    IMPORTANT:

    CloudTrail LookupEvents has API limitations.
    This method is suitable for environments where
    the required ECR data-plane events are available
    through CloudTrail lookup.

    For large-scale production environments, consider
    storing CloudTrail events in S3 and querying them
    through Athena instead.
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(days=days)
    )

    pull_event_count = 0

    pull_events = []

    next_token = None

    while True:

        request: Dict[str, Any] = {

            "StartTime": start_time,

            "EndTime": end_time,

            "LookupAttributes": [
                {
                    "AttributeKey": "EventSource",
                    "AttributeValue": (
                        "ecr.amazonaws.com"
                    ),
                }
            ],

            "MaxResults": 50,
        }

        if next_token:

            request[
                "NextToken"
            ] = next_token

        try:

            response = (
                cloudtrail.lookup_events(
                    **request
                )
            )

        except ClientError as error:

            print(
                f"CloudTrail lookup failed "
                f"for repository "
                f"{repository_name}: "
                f"{error}"
            )

            break

        events = response.get(
            "Events",
            []
        )

        for cloudtrail_event in events:

            event_name = (
                cloudtrail_event.get(
                    "EventName",
                    ""
                )
            )

            if not is_ecr_pull_event(
                event_name
            ):
                continue

            # ------------------------------------------------
            # CloudTrail stores CloudTrailEvent as JSON text.
            # ------------------------------------------------

            raw_event = (
                cloudtrail_event.get(
                    "CloudTrailEvent"
                )
            )

            if not raw_event:
                continue

            try:

                parsed_event = json.loads(
                    raw_event
                )

            except json.JSONDecodeError:

                continue

            event_repository = (
                extract_repository_from_event(
                    parsed_event
                )
            )

            # ------------------------------------------------
            # Make sure the event belongs to this repository.
            # ------------------------------------------------

            if (
                event_repository
                != repository_name
            ):

                continue

            pull_event_count += 1

            event_time = (
                cloudtrail_event.get(
                    "EventTime"
                )
            )

            pull_events.append({

                "eventName": event_name,

                "eventTime": (
                    event_time.isoformat()
                    if event_time
                    else None
                ),

                "username": (
                    cloudtrail_event.get(
                        "Username"
                    )
                ),
            })

        next_token = (
            response.get(
                "NextToken"
            )
        )

        if not next_token:
            break

    return {

        "pullCount": pull_event_count,

        "pullActivityDays": days,

        "pullEvents": pull_events,
    }


# ============================================================
# ANALYZE IMAGES
# ============================================================

def analyze_images(
    images: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyze ECR images.

    Calculates:

        Total image count
        Total image storage
        Latest 30 images
        Older images
        Untagged image count
    """

    sorted_images = (
        sort_images_latest_first(
            images
        )
    )

    latest_images = (
        sorted_images[
            :KEEP_LATEST_IMAGES
        ]
    )

    older_images = (
        sorted_images[
            KEEP_LATEST_IMAGES:
        ]
    )

    total_size_bytes = 0

    older_size_bytes = 0

    untagged_image_count = 0

    image_details = []

    latest_image_ids: Set[str] = set()

    # --------------------------------------------------------
    # Identify latest images
    # --------------------------------------------------------

    for image in latest_images:

        digest = image.get(
            "imageDigest"
        )

        if digest:

            latest_image_ids.add(
                digest
            )

    # --------------------------------------------------------
    # Analyze every image
    # --------------------------------------------------------

    for image in sorted_images:

        digest = image.get(
            "imageDigest"
        )

        image_tags = image.get(
            "imageTags",
            []
        )

        pushed_at = image.get(
            "imagePushedAt"
        )

        size_bytes = image.get(
            "imageSizeInBytes",
            0
        )

        age_days = calculate_age_days(
            pushed_at
        )

        total_size_bytes += (
            size_bytes
        )

        if not image_tags:

            untagged_image_count += 1

        is_latest = (
            digest
            in latest_image_ids
        )

        if not is_latest:

            older_size_bytes += (
                size_bytes
            )

        image_details.append({

            "imageDigest": digest,

            "imageTags": image_tags,

            "imagePushedAt": (
                pushed_at.isoformat()
                if pushed_at
                else None
            ),

            "ageDays": age_days,

            "imageSizeBytes": size_bytes,

            "imageSizeGB": round(
                size_bytes
                / (1024 ** 3),
                4,
            ),

            "isLatest30": is_latest,

            "mediaType": image.get(
                "imageManifestMediaType"
            ),

        })

    return {

        "totalImages": len(
            sorted_images
        ),

        "latestImageCount": len(
            latest_images
        ),

        "olderImageCount": len(
            older_images
        ),

        "untaggedImageCount": (
            untagged_image_count
        ),

        "totalSizeBytes": (
            total_size_bytes
        ),

        "totalSizeGB": round(
            total_size_bytes
            / (1024 ** 3),
            4,
        ),

        "olderImageSizeBytes": (
            older_size_bytes
        ),

        "olderImageSizeGB": round(
            older_size_bytes
            / (1024 ** 3),
            4,
        ),

        "latestImages": (
            latest_images
        ),

        "olderImages": (
            older_images
        ),

        "imageDetails": (
            image_details
        ),
    }


# ============================================================
# COST PLACEHOLDER
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    resource_arn: str,
) -> Dict[str, Any]:
    """
    COST DATA WILL COME FROM CUR + ATHENA.

    Do NOT calculate ECR cost using a hardcoded price.

    This function will later be replaced/integrated with
    your centralized CUR + Athena cost service.

    Expected output:

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

def build_ecr_low_pull_finding(
    repository: Dict[str, Any],
    account_id: str,
    region_name: str,
    tags: Dict[str, str],
    image_analysis: Dict[str, Any],
    pull_activity: Dict[str, Any],
) -> Dict[str, Any]:

    repository_name = (
        repository[
            "repositoryName"
        ]
    )

    repository_arn = (
        repository[
            "repositoryArn"
        ]
    )

    repository_uri = (
        repository.get(
            "repositoryUri"
        )
    )

    created_at = (
        repository.get(
            "createdAt"
        )
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
    # Image information
    # --------------------------------------------------------

    total_images = (
        image_analysis[
            "totalImages"
        ]
    )

    latest_image_count = (
        image_analysis[
            "latestImageCount"
        ]
    )

    older_image_count = (
        image_analysis[
            "olderImageCount"
        ]
    )

    older_image_size_gb = (
        image_analysis[
            "olderImageSizeGB"
        ]
    )

    untagged_image_count = (
        image_analysis[
            "untaggedImageCount"
        ]
    )

    pull_count = (
        pull_activity[
            "pullCount"
        ]
    )

    # --------------------------------------------------------
    # Policy
    # --------------------------------------------------------

    policy = (
        "ecr-repository-low-pull-count"
    )

    effort_level = "Low"

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    if total_images < KEEP_LATEST_IMAGES:

        recommendation = (

            f"ECR repository "
            f"'{repository_name}' "
            f"has very low image pull activity "
            f"({pull_count} pull events over "
            f"{PULL_ACTIVITY_DAYS} days). "

            f"The repository contains only "
            f"{total_images} images, which is fewer "
            f"than the configured "
            f"{KEEP_LATEST_IMAGES}-image retention threshold. "

            f"Leave the repository as-is and "
            f"review whether it is still required."
        )

    else:

        recommendation = (

            f"ECR repository "
            f"'{repository_name}' "
            f"has very low image pull activity "
            f"({pull_count} pull events over "
            f"{PULL_ACTIVITY_DAYS} days). "

            f"Keep the latest "
            f"{KEEP_LATEST_IMAGES} images and "
            f"consider archiving or deleting the "
            f"{older_image_count} older images "
            f"({older_image_size_gb} GB)."
        )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = (

        f"ECR repository "
        f"{repository_name} "
        f"has very low image pull count "
        f"(~{pull_count} over "
        f"{PULL_ACTIVITY_DAYS} days). "

        f"The repository contains "
        f"{total_images} images. "

        f"Latest images to retain: "
        f"{latest_image_count}. "

        f"Images outside the latest "
        f"{KEEP_LATEST_IMAGES}: "
        f"{older_image_count}. "

        f"Untagged images: "
        f"{untagged_image_count}. "
    )

    if total_images < KEEP_LATEST_IMAGES:

        message += (

            f"Image count is below "
            f"{KEEP_LATEST_IMAGES}, "
            f"so no image cleanup is recommended."
        )

    else:

        message += (

            f"Keep the latest "
            f"{KEEP_LATEST_IMAGES} images "
            f"and archive/delete eligible older images."
        )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {repository_name} | "

        f"arn: {repository_arn} | "

        f"Type: Low Pull Count | "

        f"policy: {policy} | "

        f"message: {message} | "

        f"effortLevel: {effort_level} | "

        f"pullCount90Days: {pull_count} | "

        f"imageCount: {total_images} | "

        f"latestImagesKept: "
        f"{latest_image_count} | "

        f"olderImageCount: "
        f"{older_image_count} | "

        f"olderImageStorageGB: "
        f"{older_image_size_gb}"
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

        "title": (
            "AWS ECR Repository Low Pull Count"
        ),

        "category": (
            "AWS ECR Repository Low Pull Count"
        ),

        "owner": "",

        "assignedTo": "",

        "status": "Task Completed",

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

        "resourceNameOrId": (
            f"{region_name}:"
            f"{account_id}:"
            f"repository/{repository_name}"
        ),

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
        # PULL ACTIVITY
        # ====================================================

        "pullActivityDays": (
            PULL_ACTIVITY_DAYS
        ),

        "pullCount90Days": pull_count,

        "isLowPullCount": (
            pull_count
            <= LOW_PULL_THRESHOLD
        ),

        # ====================================================
        # IMAGE INFORMATION
        # ====================================================

        "imageCount": total_images,

        "latestImageCount": (
            latest_image_count
        ),

        "olderImageCount": (
            older_image_count
        ),

        "untaggedImageCount": (
            untagged_image_count
        ),

        "totalImageStorageGB": (
            image_analysis[
                "totalSizeGB"
            ]
        ),

        "olderImageStorageGB": (
            older_image_size_gb
        ),

        # ====================================================
        # FINOPS
        # ====================================================

        "type": "Low Pull Count",

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

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": "",
    }


# ============================================================
# SCAN ALL ECR REPOSITORIES
# ============================================================

def scan_ecr_repositories(
    region_name: str,
) -> Dict[str, Any]:
    """
    Scan all ECR repositories in a region.

    Repository names are discovered automatically.
    """

    ecr, cloudtrail, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Discover repositories
    # --------------------------------------------------------

    repositories = (
        fetch_all_ecr_repositories(
            ecr
        )
    )

    findings = []

    inventory = []

    # --------------------------------------------------------
    # Process every repository
    # --------------------------------------------------------

    for repository in repositories:

        repository_name = (
            repository[
                "repositoryName"
            ]
        )

        repository_arn = (
            repository[
                "repositoryArn"
            ]
        )

        print(
            f"\nProcessing repository: "
            f"{repository_name}"
        )

        # ----------------------------------------------------
        # Tags
        # ----------------------------------------------------

        tags = fetch_repository_tags(
            ecr,
            repository_arn,
        )

        # ----------------------------------------------------
        # Images
        # ----------------------------------------------------

        images = (
            fetch_all_repository_images(
                ecr,
                repository_name,
            )
        )

        image_analysis = (
            analyze_images(
                images
            )
        )

        # ----------------------------------------------------
        # Pull activity
        # ----------------------------------------------------

        print(
            f"Fetching {PULL_ACTIVITY_DAYS}-day "
            f"pull activity..."
        )

        pull_activity = (
            fetch_repository_pull_activity(
                cloudtrail=cloudtrail,

                repository_name=(
                    repository_name
                ),

                region_name=region_name,

                days=PULL_ACTIVITY_DAYS,
            )
        )

        pull_count = (
            pull_activity[
                "pullCount"
            ]
        )

        # ----------------------------------------------------
        # Complete repository inventory
        # ----------------------------------------------------

        inventory.append({

            "accountId": account_id,

            "region": region_name,

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

            "imageCount": (
                image_analysis[
                    "totalImages"
                ]
            ),

            "latestImageCount": (
                image_analysis[
                    "latestImageCount"
                ]
            ),

            "olderImageCount": (
                image_analysis[
                    "olderImageCount"
                ]
            ),

            "totalImageStorageGB": (
                image_analysis[
                    "totalSizeGB"
                ]
            ),

            "olderImageStorageGB": (
                image_analysis[
                    "olderImageSizeGB"
                ]
            ),

            "untaggedImageCount": (
                image_analysis[
                    "untaggedImageCount"
                ]
            ),

            "pullCount90Days": pull_count,

            "isLowPullCount": (
                pull_count
                <= LOW_PULL_THRESHOLD
            ),
        })

        # ----------------------------------------------------
        # POLICY
        #
        # Low pull count
        # ----------------------------------------------------

        if (
            pull_count
            <= LOW_PULL_THRESHOLD
        ):

            finding = (
                build_ecr_low_pull_finding(

                    repository=repository,

                    account_id=account_id,

                    region_name=region_name,

                    tags=tags,

                    image_analysis=(
                        image_analysis
                    ),

                    pull_activity=(
                        pull_activity
                    ),
                )
            )

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalRepositoriesScanned": (
            len(repositories)
        ),

        "totalLowPullRepositories": (
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


if __name__ == "__main__":

    # --------------------------------------------------------
    # ONLY REGION IS SUPPLIED
    #
    # Repository names are discovered automatically.
    # --------------------------------------------------------

    region = "eu-west-1"

    print(
        "\n=========================================="
    )

    print(
        "ECR LOW PULL COUNT FINOPS SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Pull activity window: "
        f"{PULL_ACTIVITY_DAYS} days"
    )

    print(
        f"Keep latest images: "
        f"{KEEP_LATEST_IMAGES}"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_ecr_repositories(
        region
    )

    # --------------------------------------------------------
    # Print JSON
    # --------------------------------------------------------

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
        result[
            "accountId"
        ]
    )

    print(
        "Region:",
        result[
            "region"
        ]
    )

    print(
        "Repositories scanned:",
        result[
            "totalRepositoriesScanned"
        ]
    )

    print(
        "Low-pull repositories:",
        result[
            "totalLowPullRepositories"
        ]
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
            "\nNo ECR repositories with "
            "low pull activity were found."
        )

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    excel_file = (
        "ecr_low_pull_count_report.xlsx"
    )

    export_to_excel(
        findings=findings,

        filename=excel_file,
    )

