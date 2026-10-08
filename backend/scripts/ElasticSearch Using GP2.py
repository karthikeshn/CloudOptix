# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone
from botocore.config import Config


# ============================================================
# 2. AWS CONFIGURATION
# ============================================================

REGION = "us-east-1"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_NAME = "ElasticSearch Using GP2"
CATEGORY = "ElasticSearch Using GP2"
SERVICE_NAME = "OpenSearch"

SOURCE_VOLUME_TYPE = "gp2"
TARGET_VOLUME_TYPE = "gp3"


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients.
    """

    opensearch = boto3.client(
        "opensearch",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return opensearch, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_domains(opensearch):
    """
    Fetch all OpenSearch domains in the region.

    list_domain_names returns the domain names and the
    pagination mechanism is handled using NextToken when
    available.
    """

    domains = []

    next_token = None

    while True:

        params = {}

        if next_token:
            params["NextToken"] = next_token

        response = opensearch.list_domain_names(
            **params
        )

        domain_names = response.get(
            "DomainNames",
            []
        )

        domains.extend(domain_names)

        next_token = response.get(
            "NextToken"
        )

        if not next_token:
            break

    return domains


def fetch_domain_details(
    opensearch,
    domain_name
):
    """
    Fetch detailed configuration for one OpenSearch domain.
    """

    response = opensearch.describe_domain(
        DomainName=domain_name
    )

    return response.get(
        "DomainStatus",
        {}
    )


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_domain_tags(
    opensearch,
    domain_arn
):
    """
    Fetch tags associated with the OpenSearch domain.
    """

    if not domain_arn:
        return []

    try:

        response = opensearch.list_tags(
            ARN=domain_arn
        )

        return response.get(
            "TagList",
            []
        )

    except Exception as exc:

        print(
            f"Warning: Unable to fetch tags for "
            f"{domain_arn}: {exc}"
        )

        return []


def build_tag_string(tags):
    """
    Convert AWS tags to a string.
    """

    if not tags:
        return ""

    return "; ".join(
        f"{tag.get('Key', '')}={tag.get('Value', '')}"
        for tag in tags
    )


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_gp2_policy(domain):
    """
    Check whether the OpenSearch domain is using GP2 EBS
    storage.
    """

    domain_name = domain.get(
        "DomainName",
        ""
    )

    arn = domain.get(
        "ARN",
        ""
    )

    engine_version = domain.get(
        "EngineVersion",
        ""
    )

    processing = domain.get(
        "Processing",
        False
    )

    upgrade_processing = domain.get(
        "UpgradeProcessing",
        False
    )

    created = domain.get(
        "Created",
        False
    )

    deleted = domain.get(
        "Deleted",
        False
    )

    domain_id = domain.get(
        "DomainId",
        ""
    )

    endpoint = domain.get(
        "Endpoint",
        ""
    )

    endpoints = domain.get(
        "Endpoints",
        {}
    )

    # --------------------------------------------------------
    # EBS configuration
    # --------------------------------------------------------

    ebs_options = domain.get(
        "EBSOptions",
        {}
    )

    volume_type = (
        ebs_options.get(
            "VolumeType"
        ) or ""
    ).lower()

    volume_size = ebs_options.get(
        "VolumeSize"
    )

    iops = ebs_options.get(
        "Iops"
    )

    throughput = ebs_options.get(
        "Throughput"
    )

    ebs_enabled = ebs_options.get(
        "EBSEnabled",
        False
    )

    # --------------------------------------------------------
    # Only GP2 domains are candidates.
    # --------------------------------------------------------

    if volume_type != SOURCE_VOLUME_TYPE:
        return None

    # --------------------------------------------------------
    # Ignore deleted domains.
    # --------------------------------------------------------

    if deleted:
        return None

    return {
        "domainName": domain_name,
        "domainId": domain_id,
        "domainArn": arn,
        "engineVersion": engine_version,
        "volumeType": volume_type,
        "volumeSize": volume_size,
        "iops": iops,
        "throughput": throughput,
        "ebsEnabled": ebs_enabled,
        "endpoint": endpoint,
        "endpoints": endpoints,
        "processing": processing,
        "upgradeProcessing": upgrade_processing,
        "created": created
    }


# ============================================================
# 9. BUILD STANDARD FINDING
# ============================================================

def build_finding(
    candidate,
    account_id,
    region,
    tags=""
):
    """
    Build finding using the exact standard 30-column schema.
    """

    domain_name = candidate["domainName"]
    domain_arn = candidate["domainArn"]
    engine_version = candidate["engineVersion"]

    volume_type = candidate["volumeType"]
    volume_size = candidate["volumeSize"]
    iops = candidate["iops"]
    throughput = candidate["throughput"]

    message = (
        f"OpenSearch domain '{domain_name}' is using "
        f"{volume_type.upper()} EBS storage and is a candidate "
        f"for migration to GP3."
    )

    recommendation = (
        "Review the OpenSearch domain's EBS configuration and "
        "migrate the storage volume from GP2 to GP3 where "
        "supported. Validate required IOPS, throughput, "
        "performance and workload requirements before making "
        "the change."
    )

    description = (
        f"OpenSearch domain **{domain_name}** is using "
        f"**{volume_type.upper()}** EBS storage and should be "
        f"reviewed for migration to **{TARGET_VOLUME_TYPE.upper()}**.<br>"
        f" → Domain: {domain_name}<br>"
        f" → Engine version: {engine_version or 'Not available'}<br>"
        f" → Current EBS volume type: {volume_type.upper()}<br>"
        f" → Target EBS volume type: {TARGET_VOLUME_TYPE.upper()}<br>"
        f" → EBS enabled: {candidate['ebsEnabled']}<br>"
        f" → Volume size: "
        f"{volume_size if volume_size is not None else 'Not available'} GiB<br>"
        f" → Configured IOPS: "
        f"{iops if iops is not None else 'Default/Not available'}<br>"
        f" → Configured throughput: "
        f"{throughput if throughput is not None else 'Default/Not available'} MB/s<br>"
        f" → Action: Review the workload and migrate GP2 storage "
        f"to GP3 where supported to optimize storage cost and "
        f"configuration flexibility."
    )

    return {
        "workItemType": "Task",
        "state": "To Do",
        "id": "",
        "title": POLICY_NAME,
        "category": CATEGORY,
        "owner": "",
        "assignedTo": "",
        "status": "Pending for Review",
        "areaPath": "AWS Cost Optimization",
        "tags": tags,
        "commentCount": 0,
        "accountId": account_id,
        "region": region,
        "resourceNameOrId": domain_name,
        "resourceId": candidate["domainId"],
        "resourceArn": domain_arn,
        "service": SERVICE_NAME,
        "type": "OpenSearch Domain",
        "policy": POLICY_NAME,
        "effortLevel": "",
        "message": message,
        "recommendation": recommendation,
        "description": description,
        "currentDailyCost": "To be updated",
        "currentMonthlyCost": "To be updated",
        "estimatedMonthlySavings": "",
        "approvalComments": "",
        "reasonForRejection": "",
        "achievedSavingsMonthly": "",
        "month": ""
    }


# ============================================================
# 10. SCAN FUNCTION
# ============================================================

def scan_opensearch_gp2(
    opensearch,
    account_id,
    region
):
    """
    Scan all OpenSearch domains and identify domains
    using GP2 EBS storage.
    """

    domain_names = fetch_all_domains(
        opensearch
    )

    findings = []

    total_domains_scanned = 0
    total_gp2_domains = 0

    for domain_summary in domain_names:

        domain_name = domain_summary.get(
            "DomainName",
            ""
        )

        if not domain_name:
            continue

        total_domains_scanned += 1

        try:

            # ------------------------------------------------
            # Fetch complete domain configuration.
            # ------------------------------------------------

            domain = fetch_domain_details(
                opensearch,
                domain_name
            )

            # ------------------------------------------------
            # Evaluate GP2 policy.
            # ------------------------------------------------

            candidate = evaluate_gp2_policy(
                domain
            )

            if not candidate:
                continue

            total_gp2_domains += 1

            # ------------------------------------------------
            # Fetch tags.
            # ------------------------------------------------

            tags = get_domain_tags(
                opensearch,
                candidate["domainArn"]
            )

            tag_string = build_tag_string(
                tags
            )

            # ------------------------------------------------
            # Build finding.
            # ------------------------------------------------

            finding = build_finding(
                candidate=candidate,
                account_id=account_id,
                region=region,
                tags=tag_string
            )

            findings.append(
                finding
            )

        except Exception as exc:

            print(
                f"Warning: Failed to process "
                f"OpenSearch domain '{domain_name}': {exc}"
            )

    return {
        "findings": findings,
        "totalDomainsScanned": total_domains_scanned,
        "totalGP2Domains": total_gp2_domains,
        "totalCandidates": len(findings)
    }


# ============================================================
# 11. EXCEL EXPORT
# ============================================================

EXCEL_COLUMNS = [
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


def export_to_excel(
    findings,
    output_file
):
    """
    Export findings to Excel using the exact 30-column schema.
    """

    df = pd.DataFrame(
        findings,
        columns=EXCEL_COLUMNS
    )

    df.to_excel(
        output_file,
        index=False
    )

    print(
        f"Excel report generated: {output_file}"
    )


# ============================================================
# 12. MAIN
# ============================================================

def main():

    print("=" * 70)
    print("AWS FINOPS - OPENSEARCH GP2 TO GP3 SCAN")
    print("=" * 70)

    print(f"Region : {REGION}")
    print(f"Policy : {POLICY_NAME}")
    print()

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    opensearch, sts = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Get account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"Account ID : {account_id}"
    )

    # --------------------------------------------------------
    # Execute scan
    # --------------------------------------------------------

    scan_start = datetime.now(
        timezone.utc
    )

    result = scan_opensearch_gp2(
        opensearch=opensearch,
        account_id=account_id,
        region=REGION
    )

    scan_end = datetime.now(
        timezone.utc
    )

    duration = (
        scan_end - scan_start
    ).total_seconds()

    findings = result["findings"]

    # --------------------------------------------------------
    # Export findings
    # --------------------------------------------------------

    output_file = (
        "opensearch_gp2_findings.xlsx"
    )

    export_to_excel(
        findings,
        output_file
    )

    # --------------------------------------------------------
    # Scan summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SCAN SUMMARY")
    print("=" * 70)

    print(
        f"Total OpenSearch domains scanned : "
        f"{result['totalDomainsScanned']}"
    )

    print(
        f"Domains using GP2                 : "
        f"{result['totalGP2Domains']}"
    )

    print(
        f"GP2 migration candidates           : "
        f"{result['totalCandidates']}"
    )

    print(
        f"Scan duration                      : "
        f"{duration:.2f} seconds"
    )

    print(
        f"Output file                        : "
        f"{output_file}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()