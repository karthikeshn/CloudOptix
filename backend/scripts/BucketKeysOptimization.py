
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

POLICY_NAME = (
    "s3-bucket-key-optimization"
)

CATEGORY = (
    "Bucket Keys Optimization"
)

SERVICE_NAME = "S3"

EFFORT_LEVEL = "Medium"


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):
    """
    Create AWS clients.

    S3 bucket discovery is global, while most bucket
    configuration APIs are region-aware.
    """

    s3 = boto3.client(
        "s3",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return s3, sts


# ============================================================
# GET ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL S3 BUCKETS
# ============================================================

def fetch_all_s3_buckets(
    s3,
) -> List[Dict[str, Any]]:
    """
    Fetch all S3 buckets in the AWS account.

    list_buckets returns the complete bucket list for
    the account.
    """

    response = s3.list_buckets()

    return response.get(
        "Buckets",
        []
    )


# ============================================================
# GET BUCKET REGION
# ============================================================

def get_bucket_region(
    s3,
    bucket_name: str,
) -> str:
    """
    Determine the actual AWS region of an S3 bucket.

    S3 may return:
        None
        EU
        us-east-1
        etc.

    EU is normalized to eu-west-1 for compatibility
    with older S3 responses.
    """

    try:

        response = s3.get_bucket_location(
            Bucket=bucket_name
        )

        location = response.get(
            "LocationConstraint"
        )

        if location is None:
            return "us-east-1"

        if location == "EU":
            return "eu-west-1"

        return location

    except ClientError as e:

        print(
            f"Could not determine region for "
            f"bucket {bucket_name}: {e}"
        )

        return "unknown"


# ============================================================
# CREATE REGIONAL S3 CLIENT
# ============================================================

def create_regional_s3_client(
    region_name: str,
):

    return boto3.client(
        "s3",
        region_name=region_name,
        config=AWS_CONFIG,
    )


# ============================================================
# FETCH BUCKET ENCRYPTION
# ============================================================

def fetch_bucket_encryption(
    s3,
    bucket_name: str,
) -> Dict[str, Any]:
    """
    Fetch server-side encryption configuration.

    Detects:

        AES256
        aws:kms
        aws:kms:dsse

    and whether S3 Bucket Keys are enabled.
    """

    try:

        response = s3.get_bucket_encryption(
            Bucket=bucket_name
        )

        rules = (
            response
            .get(
                "ServerSideEncryptionConfiguration",
                {}
            )
            .get(
                "Rules",
                []
            )
        )

        if not rules:

            return {
                "encryptionEnabled": False,
                "encryptionType": None,
                "kmsKeyId": None,
                "bucketKeyEnabled": False,
            }

        rule = rules[0]

        default_encryption = (
            rule.get(
                "ApplyServerSideEncryptionByDefault",
                {}
            )
        )

        encryption_type = (
            default_encryption.get(
                "SSEAlgorithm"
            )
        )

        kms_key_id = (
            default_encryption.get(
                "KMSMasterKeyID"
            )
        )

        bucket_key_enabled = (
            rule.get(
                "BucketKeyEnabled",
                False
            )
        )

        return {

            "encryptionEnabled": True,

            "encryptionType": (
                encryption_type
            ),

            "kmsKeyId": (
                kms_key_id
            ),

            "bucketKeyEnabled": (
                bucket_key_enabled
            ),
        }

    except ClientError as e:

        error_code = (
            e.response
            .get("Error", {})
            .get("Code")
        )

        # NoSuchBucket / AccessDenied / etc.
        if error_code in (
            "ServerSideEncryptionConfigurationNotFoundError",
            "NoSuchBucket",
        ):

            return {

                "encryptionEnabled": False,

                "encryptionType": None,

                "kmsKeyId": None,

                "bucketKeyEnabled": False,
            }

        print(
            f"Could not fetch encryption "
            f"for bucket {bucket_name}: {e}"
        )

        return {

            "encryptionEnabled": None,

            "encryptionType": None,

            "kmsKeyId": None,

            "bucketKeyEnabled": None,
        }


# ============================================================
# FETCH BUCKET VERSIONING
# ============================================================

def fetch_bucket_versioning(
    s3,
    bucket_name: str,
) -> Dict[str, Any]:

    try:

        response = s3.get_bucket_versioning(
            Bucket=bucket_name
        )

        return {

            "versioningStatus": (
                response.get(
                    "Status"
                )
            ),

            "mfaDelete": (
                response.get(
                    "MFADelete"
                )
            ),
        }

    except ClientError:

        return {

            "versioningStatus": None,

            "mfaDelete": None,
        }


# ============================================================
# FETCH BUCKET TAGS
# ============================================================

def fetch_bucket_tags(
    s3,
    bucket_name: str,
) -> Dict[str, str]:

    try:

        response = s3.get_bucket_tagging(
            Bucket=bucket_name
        )

        tag_set = response.get(
            "TagSet",
            []
        )

        return {

            tag["Key"]: tag.get(
                "Value"
            )

            for tag in tag_set

            if "Key" in tag
        }

    except ClientError:

        return {}


# ============================================================
# FETCH BUCKET LIFECYCLE
# ============================================================

def fetch_bucket_lifecycle(
    s3,
    bucket_name: str,
) -> Dict[str, Any]:
    """
    Fetch lifecycle configuration.

    This is useful because the sample Excel row mentions
    lifecycle-related optimization.
    """

    try:

        response = (
            s3.get_bucket_lifecycle_configuration(
                Bucket=bucket_name
            )
        )

        rules = response.get(
            "Rules",
            []
        )

        return {

            "hasLifecyclePolicy": (
                len(rules) > 0
            ),

            "lifecycleRuleCount": (
                len(rules)
            ),

            "lifecycleRules": rules,
        }

    except ClientError:

        return {

            "hasLifecyclePolicy": False,

            "lifecycleRuleCount": 0,

            "lifecycleRules": [],
        }


# ============================================================
# FETCH OBJECT COUNT / STORAGE
# ============================================================

def fetch_bucket_storage_inventory(
    s3,
    bucket_name: str,
) -> Dict[str, Any]:
    """
    Optional lightweight inventory.

    IMPORTANT:

    Listing every object in a large S3 bucket can be
    expensive and slow.

    Therefore this function is disabled by default.

    For production FinOps use, object count and storage
    size should preferably come from:

        S3 Storage Lens
        S3 Inventory
        CloudWatch
        CUR

    rather than scanning millions of objects.
    """

    return {

        "objects": None,

        "sizeGB": None,

        "standardGB": None,

        "glacierInstantRetrievalGB": None,
    }


# ============================================================
# CHECK BUCKET KEY OPTIMIZATION
# ============================================================

def evaluate_bucket_key_policy(
    encryption_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluate the S3 Bucket Key configuration.

    Important:

    Bucket Keys normally REDUCE AWS KMS request costs.

    Therefore:

        Bucket Key enabled
            -> normally healthy

        Bucket Key disabled + SSE-KMS
            -> optimization candidate

    We do not automatically recommend disabling an enabled
    Bucket Key.
    """

    encryption_type = (
        encryption_info.get(
            "encryptionType"
        )
    )

    bucket_key_enabled = (
        encryption_info.get(
            "bucketKeyEnabled"
        )
    )

    # --------------------------------------------------------
    # SSE-KMS + Bucket Key enabled
    # --------------------------------------------------------

    if (
        encryption_type
        in (
            "aws:kms",
            "aws:kms:dsse",
        )
        and bucket_key_enabled is True
    ):

        return {

            "isCandidate": False,

            "type": (
                "Bucket Key Enabled"
            ),

            "policy": POLICY_NAME,

            "effortLevel": "N/A",

            "recommendation": (
                "S3 Bucket Keys are enabled. "
                "This normally reduces AWS KMS "
                "request charges. Keep Bucket Keys "
                "enabled unless a specific security "
                "or application requirement requires "
                "otherwise."
            ),
        }

    # --------------------------------------------------------
    # SSE-KMS + Bucket Key disabled
    # --------------------------------------------------------

    if (
        encryption_type
        in (
            "aws:kms",
            "aws:kms:dsse",
        )
        and bucket_key_enabled is False
    ):

        return {

            "isCandidate": True,

            "type": (
                "Bucket Key Disabled"
            ),

            "policy": POLICY_NAME,

            "effortLevel": EFFORT_LEVEL,

            "recommendation": (
                "S3 Bucket Keys are disabled on an "
                "SSE-KMS encrypted bucket. Review "
                "the workload and enable S3 Bucket "
                "Keys if compatible. Bucket Keys can "
                "reduce AWS KMS request charges."
            ),
        }

    # --------------------------------------------------------
    # No KMS encryption
    # --------------------------------------------------------

    return {

        "isCandidate": False,

        "type": (
            "Bucket Key Not Applicable"
        ),

        "policy": POLICY_NAME,

        "effortLevel": "N/A",

        "recommendation": (
            "S3 Bucket Keys are not applicable "
            "because the bucket is not using "
            "SSE-KMS encryption."
        ),
    }


# ============================================================
# COST PLACEHOLDER
# ============================================================

def get_resource_cost(
    account_id: str,
    region_name: str,
    bucket_name: str,
) -> Dict[str, Any]:
    """
    Cost integration point.

    DO NOT calculate S3 cost using a simple hardcoded
    price.

    Your production implementation should query:

        CUR
          ↓
        Athena
          ↓
        S3 bucket/resource cost

    and return:

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

def build_bucket_finding(
    bucket: Dict[str, Any],
    account_id: str,
    region_name: str,
    encryption_info: Dict[str, Any],
    versioning_info: Dict[str, Any],
    lifecycle_info: Dict[str, Any],
    tags: Dict[str, str],
) -> Optional[Dict[str, Any]]:

    bucket_name = bucket.get(
        "Name"
    )

    creation_date = bucket.get(
        "CreationDate"
    )

    # --------------------------------------------------------
    # Policy evaluation
    # --------------------------------------------------------

    evaluation = (
        evaluate_bucket_key_policy(
            encryption_info
        )
    )

    # --------------------------------------------------------
    # Only create a finding when policy says candidate
    # --------------------------------------------------------

    if not evaluation[
        "isCandidate"
    ]:

        return None

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    cost = get_resource_cost(

        account_id=account_id,

        region_name=region_name,

        bucket_name=bucket_name,
    )

    # --------------------------------------------------------
    # S3 ARN
    # --------------------------------------------------------

    bucket_arn = (
        f"arn:aws:s3:::{bucket_name}"
    )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        evaluation[
            "recommendation"
        ]
    )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceName: {bucket_name} | "

        f"category: {CATEGORY} | "

        f"currentCostDaily: "
        f"{cost['currentDailyCost']} | "

        f"currentCostMonthly: "
        f"{cost['currentMonthlyCost']} | "

        f"postActivityCostDaily: N/A | "

        f"postActivityCostMonthly: N/A | "

        f"encryptionType: "
        f"{encryption_info.get('encryptionType')} | "

        f"kmsKeyId: "
        f"{encryption_info.get('kmsKeyId')} | "

        f"bucketKeyEnabled: "
        f"{encryption_info.get('bucketKeyEnabled')} | "

        f"versioningStatus: "
        f"{versioning_info.get('versioningStatus')} | "

        f"hasLifecyclePolicy: "
        f"{lifecycle_info.get('hasLifecyclePolicy')} | "

        f"lifecycleRuleCount: "
        f"{lifecycle_info.get('lifecycleRuleCount')} | "

        f"type: "
        f"{evaluation['type']} | "

        f"effortLevel: "
        f"{evaluation['effortLevel']} | "

        f"recommendation: "
        f"{recommendation}"
    )

    # --------------------------------------------------------
    # Return finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORK ITEM
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

        "tags": (
            ", ".join(
                f"{k}={v}"
                for k, v in tags.items()
            )
        ),

        "commentCount": 0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": bucket_name,

        "resourceId": bucket_name,

        "resourceArn": bucket_arn,

        "service": SERVICE_NAME,

        # ====================================================
        # S3
        # ====================================================

        "bucketName": bucket_name,

        "bucketArn": bucket_arn,

        "creationDate": (
            creation_date.isoformat()
            if creation_date
            else None
        ),

        # ====================================================
        # ENCRYPTION
        # ====================================================

        "encryptionEnabled": (
            encryption_info.get(
                "encryptionEnabled"
            )
        ),

        "encryptionType": (
            encryption_info.get(
                "encryptionType"
            )
        ),

        "kmsKeyId": (
            encryption_info.get(
                "kmsKeyId"
            )
        ),

        "bucketKeyEnabled": (
            encryption_info.get(
                "bucketKeyEnabled"
            )
        ),

        # ====================================================
        # VERSIONING
        # ====================================================

        "versioningStatus": (
            versioning_info.get(
                "versioningStatus"
            )
        ),

        "mfaDelete": (
            versioning_info.get(
                "mfaDelete"
            )
        ),

        # ====================================================
        # LIFECYCLE
        # ====================================================

        "hasLifecyclePolicy": (
            lifecycle_info.get(
                "hasLifecyclePolicy"
            )
        ),

        "lifecycleRuleCount": (
            lifecycle_info.get(
                "lifecycleRuleCount"
            )
        ),

        # ====================================================
        # FINOPS
        # ====================================================

        "type": (
            evaluation[
                "type"
            ]
        ),

        "policy": (
            evaluation[
                "policy"
            ]
        ),

        "effortLevel": (
            evaluation[
                "effortLevel"
            ]
        ),

        "recommendation": recommendation,

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
        # WORKFLOW
        # ====================================================

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": "",
    }


# ============================================================
# SCAN ONE BUCKET
# ============================================================

def scan_bucket(
    bucket: Dict[str, Any],
    account_id: str,
    discovery_s3,
) -> Optional[Dict[str, Any]]:

    bucket_name = bucket.get(
        "Name"
    )

    print(
        f"\nScanning bucket: "
        f"{bucket_name}"
    )

    # --------------------------------------------------------
    # Get bucket region
    # --------------------------------------------------------

    region_name = get_bucket_region(

        discovery_s3,

        bucket_name,
    )

    if region_name == "unknown":

        return None

    print(
        f"Region: {region_name}"
    )

    # --------------------------------------------------------
    # Create regional client
    # --------------------------------------------------------

    regional_s3 = (
        create_regional_s3_client(
            region_name
        )
    )

    # --------------------------------------------------------
    # Fetch encryption
    # --------------------------------------------------------

    encryption_info = (
        fetch_bucket_encryption(

            regional_s3,

            bucket_name,
        )
    )

    print(
        "Encryption:",
        encryption_info.get(
            "encryptionType"
        )
    )

    print(
        "Bucket Key:",
        encryption_info.get(
            "bucketKeyEnabled"
        )
    )

    # --------------------------------------------------------
    # Fetch versioning
    # --------------------------------------------------------

    versioning_info = (
        fetch_bucket_versioning(

            regional_s3,

            bucket_name,
        )
    )

    # --------------------------------------------------------
    # Fetch lifecycle
    # --------------------------------------------------------

    lifecycle_info = (
        fetch_bucket_lifecycle(

            regional_s3,

            bucket_name,
        )
    )

    # --------------------------------------------------------
    # Fetch tags
    # --------------------------------------------------------

    tags = fetch_bucket_tags(

        regional_s3,

        bucket_name,
    )

    # --------------------------------------------------------
    # Build finding
    # --------------------------------------------------------

    finding = build_bucket_finding(

        bucket=bucket,

        account_id=account_id,

        region_name=region_name,

        encryption_info=encryption_info,

        versioning_info=versioning_info,

        lifecycle_info=lifecycle_info,

        tags=tags,
    )

    return finding


# ============================================================
# SCAN ALL S3 BUCKETS
# ============================================================

def scan_s3_buckets(
    region_name: str = "us-east-1",
) -> Dict[str, Any]:
    """
    Discover and scan all S3 buckets in the account.

    The supplied region is used only for the initial
    discovery client.

    Each bucket's actual region is discovered automatically.
    """

    discovery_s3, sts = create_clients(
        region_name
    )

    # --------------------------------------------------------
    # Account
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"\nAWS Account: "
        f"{account_id}"
    )

    # --------------------------------------------------------
    # Discover all buckets
    # --------------------------------------------------------

    buckets = fetch_all_s3_buckets(
        discovery_s3
    )

    print(
        f"Total S3 buckets discovered: "
        f"{len(buckets)}"
    )

    findings = []

    # --------------------------------------------------------
    # Scan every bucket
    # --------------------------------------------------------

    for bucket in buckets:

        try:

            finding = scan_bucket(

                bucket=bucket,

                account_id=account_id,

                discovery_s3=discovery_s3,
            )

            if finding:

                findings.append(
                    finding
                )

        except Exception as e:

            print(
                f"Error scanning bucket "
                f"{bucket.get('Name')}: "
                f"{e}"
            )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "totalBucketsScanned": (
            len(buckets)
        ),

        "totalBucketKeyFindings": (
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
    # Only the initial region is provided.
    #
    # S3 buckets and their actual regions are discovered
    # automatically.
    # --------------------------------------------------------

    region = "eu-west-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS S3 BUCKET KEY OPTIMIZATION SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Initial Region: {region}"
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

    result = scan_s3_buckets(
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
        "Total Buckets:",
        result.get(
            "totalBucketsScanned"
        )
    )

    print(
        "Bucket Key Findings:",
        result.get(
            "totalBucketKeyFindings"
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
            "\nNo S3 Bucket Key optimization "
            "findings found."
        )

    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    excel_file = (
        "s3_bucket_key_optimization_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

