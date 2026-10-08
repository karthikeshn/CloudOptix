
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

POLICY_NAME = "Elastic Cache Valkey migration"
CATEGORY = "Elastic Cache Valkey migration"
SERVICE_NAME = "ElastiCache"

# Redis OSS clusters are candidates for migration to Valkey.
SUPPORTED_SOURCE_ENGINES = {
    "redis"
}

TARGET_ENGINE = "valkey"

# The examples supplied for this policy use approximately 20%
# savings as the expected savings estimate.
# This is informational only. No savings amount is fabricated
# in the Excel cost/savings columns.
EXPECTED_SAVINGS_PERCENT = 20


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients for the selected region.
    """

    elasticache = boto3.client(
        "elasticache",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return elasticache, sts


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

def fetch_all_cache_clusters(elasticache):
    """
    Fetch all ElastiCache cache clusters using pagination.
    """

    clusters = []

    marker = None

    while True:

        params = {
            "ShowCacheNodeInfo": True
        }

        if marker:
            params["Marker"] = marker

        response = elasticache.describe_cache_clusters(**params)

        clusters.extend(
            response.get("CacheClusters", [])
        )

        marker = response.get("Marker")

        if not marker:
            break

    return clusters


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_cluster_tags(elasticache, cluster_arn):
    """
    Fetch tags associated with an ElastiCache cluster.
    """

    if not cluster_arn:
        return []

    try:
        response = elasticache.list_tags_for_resource(
            ResourceName=cluster_arn
        )

        return response.get("TagList", [])

    except Exception:
        return []


def build_tag_string(tags):
    """
    Convert AWS tags into a simple string.
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

def evaluate_valkey_migration(cluster):
    """
    Determine whether an ElastiCache cluster is a candidate
    for Redis OSS -> Valkey migration.
    """

    engine = (
        cluster.get("Engine") or ""
    ).lower()

    status = (
        cluster.get("CacheClusterStatus") or ""
    ).lower()

    # --------------------------------------------------------
    # Only Redis OSS clusters are considered.
    # --------------------------------------------------------

    if engine not in SUPPORTED_SOURCE_ENGINES:
        return None

    # --------------------------------------------------------
    # Do not create recommendations for resources that are
    # not currently available/active.
    # --------------------------------------------------------

    if status and status not in {
        "available",
        "creating",
        "modifying"
    }:
        return None

    cluster_id = cluster.get(
        "CacheClusterId",
        ""
    )

    node_type = cluster.get(
        "CacheNodeType",
        ""
    )

    engine_version = cluster.get(
        "EngineVersion",
        ""
    )

    num_nodes = cluster.get(
        "NumCacheNodes",
        0
    )

    cache_nodes = cluster.get(
        "CacheNodes",
        []
    )

    availability_zones = []

    for node in cache_nodes:

        endpoint = node.get(
            "Endpoint",
            {}
        )

        if endpoint:
            availability_zone = node.get(
                "PreferredAvailabilityZone"
            )

            if availability_zone:
                availability_zones.append(
                    availability_zone
                )

    return {
        "clusterId": cluster_id,
        "clusterArn": cluster.get("ARN", ""),
        "engine": cluster.get("Engine", ""),
        "engineVersion": engine_version,
        "nodeType": node_type,
        "numNodes": num_nodes,
        "status": cluster.get(
            "CacheClusterStatus",
            ""
        ),
        "availabilityZones": sorted(
            set(availability_zones)
        ),
        "cacheNodes": cache_nodes
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
    Build a finding using the standard 30-column schema.
    """

    cluster_id = candidate["clusterId"]
    engine_version = candidate["engineVersion"]
    node_type = candidate["nodeType"]
    num_nodes = candidate["numNodes"]

    availability_zones = candidate[
        "availabilityZones"
    ]

    az_text = (
        ", ".join(availability_zones)
        if availability_zones
        else "Not available"
    )

    message = (
        f"ElastiCache Redis cluster '{cluster_id}' "
        f"running Redis {engine_version} on {node_type} "
        f"with {num_nodes} node(s) is a candidate for "
        f"migration to Valkey."
    )

    recommendation = (
        "Validate application compatibility with Valkey, "
        "review Redis OSS feature usage and engine-version "
        "compatibility, test the migration in a non-production "
        "environment, and migrate to Valkey where supported. "
        "The migration can reduce ElastiCache compute cost."
    )

    description = (
        f"ElastiCache Redis cluster **{cluster_id}** "
        f"(v{engine_version}, {node_type}, {num_nodes} nodes) "
        f"is a strong candidate for migration to **Valkey**.<br>"
        f" → Source engine: Redis OSS<br>"
        f" → Target engine: Valkey<br>"
        f" → Expected cost reduction reference: "
        f"~{EXPECTED_SAVINGS_PERCENT}% "
        f"(actual savings should be calculated from current "
        f"ElastiCache pricing before approval)<br>"
        f" → Valkey supports the Redis OSS protocol and is "
        f"intended as a compatible alternative for supported "
        f"Redis OSS workloads.<br>"
        f" → Engine version: {engine_version}<br>"
        f" → Node type: {node_type}<br>"
        f" → Node count: {num_nodes}<br>"
        f" → Cluster status: {candidate['status']}<br>"
        f" → Availability Zone(s): {az_text}<br>"
        f" → Action: Test application compatibility and "
        f"migration procedure, then migrate to Valkey where "
        f"supported and approved."
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
        "resourceNameOrId": cluster_id,
        "resourceId": cluster_id,
        "resourceArn": candidate["clusterArn"],
        "service": SERVICE_NAME,
        "type": "ElastiCache Cluster",
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

def scan_elasticache_valkey_migration(
    elasticache,
    account_id,
    region
):
    """
    Scan the region and identify Redis OSS ElastiCache
    clusters that are candidates for Valkey migration.
    """

    clusters = fetch_all_cache_clusters(
        elasticache
    )

    findings = []

    total_clusters_scanned = 0
    redis_clusters_scanned = 0

    for cluster in clusters:

        total_clusters_scanned += 1

        engine = (
            cluster.get("Engine") or ""
        ).lower()

        if engine not in SUPPORTED_SOURCE_ENGINES:
            continue

        redis_clusters_scanned += 1

        candidate = evaluate_valkey_migration(
            cluster
        )

        if not candidate:
            continue

        tags = get_cluster_tags(
            elasticache,
            candidate["clusterArn"]
        )

        tag_string = build_tag_string(
            tags
        )

        finding = build_finding(
            candidate=candidate,
            account_id=account_id,
            region=region,
            tags=tag_string
        )

        findings.append(
            finding
        )

    return {
        "findings": findings,
        "totalClustersScanned": total_clusters_scanned,
        "redisClustersScanned": redis_clusters_scanned,
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


def export_to_excel(findings, output_file):
    """
    Export findings using the exact standard 30-column schema.
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
    print("AWS FINOPS - ELASTICACHE VALKEY MIGRATION SCAN")
    print("=" * 70)

    print(f"Region : {REGION}")
    print(f"Policy : {POLICY_NAME}")
    print()

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    elasticache, sts = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Get AWS account ID
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

    result = scan_elasticache_valkey_migration(
        elasticache=elasticache,
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
    # Export
    # --------------------------------------------------------

    output_file = (
        "elasticache_valkey_migration_findings.xlsx"
    )

    export_to_excel(
        findings,
        output_file
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SCAN SUMMARY")
    print("=" * 70)

    print(
        f"Total ElastiCache clusters scanned : "
        f"{result['totalClustersScanned']}"
    )

    print(
        f"Redis OSS clusters scanned         : "
        f"{result['redisClustersScanned']}"
    )

    print(
        f"Valkey migration candidates        : "
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

