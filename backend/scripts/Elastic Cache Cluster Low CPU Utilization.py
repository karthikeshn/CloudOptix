import boto3
import openpyxl

from datetime import datetime, timedelta, timezone
from botocore.config import Config
import pandas as pd


# ============================================================
# 1. IMPORTS
# ============================================================

# boto3 and openpyxl imported above


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

METRIC_LOOKBACK_DAYS = 30


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Elastic Cache Cluster Low CPU Utilization"
POLICY_CATEGORY = "Elastic Cache Cluster Low CPU Utilization"
SERVICE = "ElastiCache"

# Average CPU utilization below this threshold is considered low.
CPU_THRESHOLD_PERCENT = 10.0

# CloudWatch metric period.
# 3600 = 1 hour.
CLOUDWATCH_PERIOD_SECONDS = 3600

DESCRIPTION_TEMPLATE = (
    "ElastiCache cluster '{cluster_id}' ({cache_node_type}) "
    "has low CPU utilization over the last {lookback_days} days. "
    "Average CPU: {avg_cpu:.2f}%, Maximum CPU: {max_cpu:.2f}%. "
    "Consider reviewing the node type, node count, or cluster utilization "
    "before downsizing or deleting the resource."
)


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients for the specified region.
    """

    session = boto3.Session(region_name=region_name)

    elasticache = session.client(
        "elasticache",
        config=AWS_CONFIG
    )

    cloudwatch = session.client(
        "cloudwatch",
        config=AWS_CONFIG
    )

    sts = session.client(
        "sts",
        config=AWS_CONFIG
    )

    return elasticache, cloudwatch, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. FETCH ALL ELASTICACHE RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_cache_clusters(elasticache):
    """
    Fetch all ElastiCache cache clusters in the region.

    Pagination is handled using the Marker returned by AWS.
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
# 7. FETCH CLOUDWATCH CPU METRICS
# ============================================================

def get_cpu_metrics(
    cloudwatch,
    cache_cluster_id,
    cache_node_id,
    start_time,
    end_time
):
    """
    Fetch CPUUtilization metrics for an ElastiCache cache node.

    CloudWatch dimensions:
        CacheClusterId
        CacheNodeId
    """

    try:

        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/ElastiCache",
            MetricName="CPUUtilization",
            Dimensions=[
                {
                    "Name": "CacheClusterId",
                    "Value": cache_cluster_id
                },
                {
                    "Name": "CacheNodeId",
                    "Value": cache_node_id
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=CLOUDWATCH_PERIOD_SECONDS,
            Statistics=[
                "Average",
                "Maximum"
            ]
        )

        datapoints = response.get("Datapoints", [])

        if not datapoints:
            return None

        average_values = [
            point["Average"]
            for point in datapoints
            if "Average" in point
        ]

        maximum_values = [
            point["Maximum"]
            for point in datapoints
            if "Maximum" in point
        ]

        if not average_values:
            return None

        avg_cpu = sum(average_values) / len(average_values)

        max_cpu = max(maximum_values) if maximum_values else 0.0

        return {
            "average_cpu": avg_cpu,
            "maximum_cpu": max_cpu,
            "datapoint_count": len(datapoints)
        }

    except Exception as error:

        print(
            f"Failed to fetch CPU metrics for "
            f"{cache_cluster_id}/{cache_node_id}: {error}"
        )

        return None


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_policy(
    clusters,
    cloudwatch,
    account_id,
    region_name
):
    """
    Evaluate ElastiCache clusters for low CPU utilization.
    """

    findings = []

    end_time = datetime.now(timezone.utc)

    start_time = (
        end_time -
        timedelta(days=METRIC_LOOKBACK_DAYS)
    )

    for cluster in clusters:

        cluster_id = cluster.get("CacheClusterId", "")

        cache_node_type = cluster.get(
            "CacheNodeType",
            ""
        )

        engine = cluster.get(
            "Engine",
            ""
        )

        engine_version = cluster.get(
            "EngineVersion",
            ""
        )

        num_cache_nodes = cluster.get(
            "NumCacheNodes",
            0
        )

        cache_cluster_status = cluster.get(
            "CacheClusterStatus",
            ""
        )

        preferred_availability_zone = cluster.get(
            "PreferredAvailabilityZone",
            ""
        )

        cache_nodes = cluster.get(
            "CacheNodes",
            []
        )

        if not cache_nodes:

            print(
                f"No cache nodes found for cluster "
                f"{cluster_id}"
            )

            continue

        node_metrics = []

        # ----------------------------------------------------
        # Fetch CPU metrics for every cache node
        # ----------------------------------------------------

        for cache_node in cache_nodes:

            cache_node_id = cache_node.get(
                "CacheNodeId"
            )

            if not cache_node_id:
                continue

            metrics = get_cpu_metrics(
                cloudwatch=cloudwatch,
                cache_cluster_id=cluster_id,
                cache_node_id=cache_node_id,
                start_time=start_time,
                end_time=end_time
            )

            if metrics:
                node_metrics.append(
                    {
                        "node_id": cache_node_id,
                        "average_cpu": metrics["average_cpu"],
                        "maximum_cpu": metrics["maximum_cpu"],
                        "datapoint_count": metrics["datapoint_count"]
                    }
                )

        # No CloudWatch data means we cannot make a
        # low-utilization recommendation.
        if not node_metrics:
            continue

        # ----------------------------------------------------
        # Calculate cluster-level CPU
        # ----------------------------------------------------

        cluster_average_cpu = (
            sum(
                node["average_cpu"]
                for node in node_metrics
            )
            / len(node_metrics)
        )

        cluster_max_cpu = max(
            node["maximum_cpu"]
            for node in node_metrics
        )

        # ----------------------------------------------------
        # Evaluate policy
        # ----------------------------------------------------

        if cluster_average_cpu >= CPU_THRESHOLD_PERCENT:
            continue

        # ----------------------------------------------------
        # Build detailed description
        # ----------------------------------------------------

        node_details = []

        for node in node_metrics:

            node_details.append(
                f"{node['node_id']}: "
                f"AvgCPU={node['average_cpu']:.2f}%, "
                f"MaxCPU={node['maximum_cpu']:.2f}%"
            )

        description = DESCRIPTION_TEMPLATE.format(
            cluster_id=cluster_id,
            cache_node_type=cache_node_type,
            lookback_days=METRIC_LOOKBACK_DAYS,
            avg_cpu=cluster_average_cpu,
            max_cpu=cluster_max_cpu
        )

        description += (
            f" Engine: {engine}"
            f" | EngineVersion: {engine_version}"
            f" | Status: {cache_cluster_status}"
            f" | CacheNodes: {num_cache_nodes}"
            f" | AZ: {preferred_availability_zone}"
            f" | CPUThreshold: <{CPU_THRESHOLD_PERCENT}%"
            f" | NodeMetrics: {'; '.join(node_details)}"
        )

        # ----------------------------------------------------
        # Resource ARN
        # ----------------------------------------------------

        resource_arn = cluster.get(
            "ARN",
            f"arn:aws:elasticache:{region_name}:"
            f"{account_id}:cluster:{cluster_id}"
        )

        # ----------------------------------------------------
        # Finding
        # ----------------------------------------------------

        finding = {
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": "Pending for Review",
            "areaPath": "AWS Cost Optimization",
            "tags": "",
            "commentCount": 0,
            "accountId": account_id,
            "region": region_name,
            "resourceNameOrId": cluster_id,
            "resourceId": cluster_id,
            "resourceArn": resource_arn,
            "service": SERVICE,
            "type": "ElastiCache Cluster",
            "policy": POLICY_TITLE,
            "effortLevel": "Low",
            "message": "Low CPU utilization detected.",
            "recommendation": "Review node type and consider downsizing.",
            "description": description,
            "currentDailyCost": "To be updated",
            "currentMonthlyCost": "To be updated",
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": "",
            "month": ""
        }

        findings.append(finding)

    return findings


# ============================================================
# 9. WRITE RESULTS TO EXCEL
# ============================================================

def write_to_excel(findings, output_file):
    columns = [
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

    dataframe = pd.DataFrame(
        findings,
        columns=columns
    )

    dataframe.to_excel(
        output_file,
        index=False
    )

    print(
        f"Excel file created successfully: {output_file}"
    )


# ============================================================
# 10. MAIN
# ============================================================

def main():

    print("=" * 70)
    print("AWS FINOPS POLICY")
    print("Elastic Cache Cluster Low CPU Utilization")
    print("=" * 70)

    print(f"Region: {REGION}")
    print(
        f"CPU Threshold: < {CPU_THRESHOLD_PERCENT}%"
    )
    print(
        f"Metric Lookback: {METRIC_LOOKBACK_DAYS} days"
    )

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    elasticache, cloudwatch, sts = create_clients(
        REGION
    )

    # --------------------------------------------------------
    # Get Account ID
    # --------------------------------------------------------

    account_id = get_account_id(sts)

    print(f"Account ID: {account_id}")

    # --------------------------------------------------------
    # Fetch all ElastiCache clusters
    # --------------------------------------------------------

    print("Fetching ElastiCache clusters...")

    clusters = fetch_all_cache_clusters(
        elasticache
    )

    print(
        f"Total ElastiCache clusters scanned: "
        f"{len(clusters)}"
    )

    # --------------------------------------------------------
    # Evaluate policy
    # --------------------------------------------------------

    print(
        "Evaluating CPU utilization over "
        f"the last {METRIC_LOOKBACK_DAYS} days..."
    )

    findings = evaluate_policy(
        clusters=clusters,
        cloudwatch=cloudwatch,
        account_id=account_id,
        region_name=REGION
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("=" * 70)
    print("SCAN SUMMARY")
    print("=" * 70)

    print(
        f"Total clusters scanned : {len(clusters)}"
    )

    print(
        f"Low CPU findings       : {len(findings)}"
    )

    # --------------------------------------------------------
    # Write Excel
    # --------------------------------------------------------

    output_file = (
        "elasticache_low_cpu_utilization.xlsx"
    )

    write_to_excel(
        findings=findings,
        output_file=output_file
    )

    print("=" * 70)
    print("SCAN COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()