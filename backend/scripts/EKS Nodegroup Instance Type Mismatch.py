import boto3
import json
import time
from datetime import datetime, timezone, timedelta
from botocore.config import Config
from botocore.exceptions import ClientError
import pandas as pd


# ============================================================
# 1. IMPORTS
# ============================================================

# boto3, json, time, datetime, Config, ClientError, Workbook
# are imported above.


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

CLOUDWATCH_LOOKBACK_DAYS = 30

# Minimum utilization threshold used to identify
# potentially unsuitable compute-optimized instances.
CPU_THRESHOLD_PERCENT = 30.0
MEMORY_THRESHOLD_PERCENT = 50.0


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "EKS Nodegroup Instance Type Mismatch"
POLICY_CATEGORY = "EKS Nodegroup Instance Type Mismatch"
SERVICE = "EKS"

SUPPORTED_FAMILIES = {
    "c": "compute-optimized",
    "m": "general-purpose",
    "r": "memory-optimized",
    "t": "burstable"
}

# Instance families where this policy can make sense.
COMPUTE_OPTIMIZED_FAMILIES = (
    "c5", "c5a", "c5d", "c5n",
    "c6i", "c6a", "c6id",
    "c7i", "c7a", "c7g",
    "c7gd", "c8g"
)


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    eks = boto3.client(
        "eks",
        region_name=region_name,
        config=AWS_CONFIG
    )

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return eks, ec2, cloudwatch, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_clusters(eks):
    clusters = []

    paginator = eks.get_paginator("list_clusters")

    for page in paginator.paginate():
        clusters.extend(page.get("clusters", []))

    return clusters


def fetch_all_nodegroups(eks, cluster_name):
    nodegroups = []

    paginator = eks.get_paginator("list_nodegroups")

    for page in paginator.paginate(
        clusterName=cluster_name
    ):
        nodegroups.extend(page.get("nodegroups", []))

    return nodegroups


def get_cluster_details(eks, cluster_name):
    return eks.describe_cluster(
        name=cluster_name
    )["cluster"]


def get_nodegroup_details(eks, cluster_name, nodegroup_name):
    return eks.describe_nodegroup(
        clusterName=cluster_name,
        nodegroupName=nodegroup_name
    )["nodegroup"]


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def extract_instance_family(instance_type):
    """
    Examples:

    c7i.4xlarge -> c7i
    m5.large    -> m5
    r6i.xlarge  -> r6i
    t3.medium   -> t3
    """

    if not instance_type:
        return ""

    return instance_type.split(".")[0]


def is_compute_optimized(instance_type):
    family = extract_instance_family(instance_type)

    return family.startswith(
        COMPUTE_OPTIMIZED_FAMILIES
    )


def get_instance_details(ec2, instance_ids):
    """
    Fetch EC2 instances associated with an EKS
    managed node group.

    Pagination is used.
    """

    if not instance_ids:
        return []

    instances = []

    paginator = ec2.get_paginator("describe_instances")

    for page in paginator.paginate(
        InstanceIds=instance_ids
    ):
        for reservation in page.get("Reservations", []):
            instances.extend(
                reservation.get("Instances", [])
            )

    return instances


def get_nodegroup_instance_ids(nodegroup):
    """
    EKS managed node groups expose resources such as
    Auto Scaling Groups. EC2 instances are therefore
    discovered through the ASG.
    """

    instance_ids = []

    resources = nodegroup.get("resources", {})

    for asg in resources.get(
        "autoScalingGroups", []
    ):
        asg_name = asg.get("name")

        if asg_name:
            instance_ids.append(asg_name)

    return instance_ids


def get_asg_instances(autoscaling, asg_names):
    """
    Resolve Auto Scaling Group names into EC2 instance IDs.
    """

    instance_ids = []

    if not asg_names:
        return instance_ids

    for asg_name in asg_names:

        try:
            response = autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )

            for group in response.get(
                "AutoScalingGroups", []
            ):
                for instance in group.get(
                    "Instances", []
                ):
                    instance_id = instance.get(
                        "InstanceId"
                    )

                    if instance_id:
                        instance_ids.append(
                            instance_id
                        )

        except ClientError:
            continue

    return instance_ids


def get_cloudwatch_average(
    cloudwatch,
    namespace,
    metric_name,
    dimensions,
    statistic="Average"
):
    """
    Fetch 30-day average CloudWatch metric.

    Returns None when the metric is unavailable.
    """

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(
        days=CLOUDWATCH_LOOKBACK_DAYS
    )

    try:
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=[statistic]
        )

        datapoints = response.get(
            "Datapoints", []
        )

        if not datapoints:
            return None

        values = [
            point[statistic]
            for point in datapoints
            if statistic in point
        ]

        if not values:
            return None

        return sum(values) / len(values)

    except ClientError:
        return None


def get_ec2_cpu_average(
    cloudwatch,
    instance_id
):
    return get_cloudwatch_average(
        cloudwatch=cloudwatch,
        namespace="AWS/EC2",
        metric_name="CPUUtilization",
        dimensions=[
            {
                "Name": "InstanceId",
                "Value": instance_id
            }
        ]
    )


def get_nodegroup_cpu_average(
    cloudwatch,
    instance_ids
):
    """
    Calculate average CPU across instances.
    """

    values = []

    for instance_id in instance_ids:

        cpu = get_ec2_cpu_average(
            cloudwatch,
            instance_id
        )

        if cpu is not None:
            values.append(cpu)

    if not values:
        return None

    return sum(values) / len(values)


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_nodegroup(
    eks,
    ec2,
    cloudwatch,
    autoscaling,
    cluster_name,
    nodegroup_name,
    account_id,
    region
):

    nodegroup = get_nodegroup_details(
        eks,
        cluster_name,
        nodegroup_name
    )

    scaling_config = nodegroup.get(
        "scalingConfig",
        {}
    )

    current_desired = scaling_config.get(
        "desiredSize"
    )

    current_min = scaling_config.get(
        "minSize"
    )

    current_max = scaling_config.get(
        "maxSize"
    )

    instance_types = nodegroup.get(
        "instanceTypes",
        []
    )

    if not instance_types:
        return None

    # EKS managed node group can have multiple
    # instance types.
    current_instance_type = instance_types[0]

    if not is_compute_optimized(
        current_instance_type
    ):
        return None

    # --------------------------------------------------------
    # Resolve Auto Scaling Groups
    # --------------------------------------------------------

    asg_names = []

    resources = nodegroup.get(
        "resources",
        {}
    )

    for asg in resources.get(
        "autoScalingGroups",
        []
    ):
        name = asg.get("name")

        if name:
            asg_names.append(name)

    instance_ids = get_asg_instances(
        autoscaling,
        asg_names
    )

    # --------------------------------------------------------
    # Fetch CPU
    # --------------------------------------------------------

    avg_cpu = get_nodegroup_cpu_average(
        cloudwatch,
        instance_ids
    )

    # --------------------------------------------------------
    # Determine recommendation
    # --------------------------------------------------------

    candidate = False
    target_instance_type = None
    recommendation = ""

    if avg_cpu is not None:

        if avg_cpu < CPU_THRESHOLD_PERCENT:

            candidate = True

            family = extract_instance_family(
                current_instance_type
            )

            if family.startswith("c7"):
                target_instance_type = (
                    current_instance_type
                    .replace("c7i", "m7i")
                )

            elif family.startswith("c6"):
                target_instance_type = (
                    current_instance_type
                    .replace("c6i", "m6i")
                )

            elif family.startswith("c5"):
                target_instance_type = (
                    current_instance_type
                    .replace("c5", "m5")
                )

            else:
                target_instance_type = (
                    "Review m/r/t family"
                )

            recommendation = (
                f"Nodegroup uses compute-optimized "
                f"instance type {current_instance_type} "
                f"with average CPU utilization of "
                f"{avg_cpu:.2f}%. Review workload "
                f"characteristics and consider migrating "
                f"to a suitable general-purpose or "
                f"memory-optimized instance family."
            )

    # --------------------------------------------------------
    # Do not create finding when there is no evidence
    # --------------------------------------------------------

    if not candidate:
        return None

    cluster_arn = nodegroup.get(
        "cluster",
        ""
    )

    created_at = nodegroup.get(
        "createdAt"
    )

    created_date = ""

    if created_at:
        created_date = created_at.strftime(
            "%Y-%m-%d"
        )

    description = (
        f"AccountId: {account_id} | "
        f"Region: {region} | "
        f"Cluster: {cluster_name} | "
        f"NodeGroup: {nodegroup_name} | "
        f"Instance: {current_instance_type} | "
        f"TargetInstance: {target_instance_type} | "
        f"Capacity: {nodegroup.get('capacityType', '')} | "
        f"Desired: {current_desired} | "
        f"Min: {current_min} | "
        f"Max: {current_max} | "
        f"Instances: {len(instance_ids)} | "
        f"AvgCPU: "
        f"{avg_cpu:.2f}% | "
        f"Created: {created_date} | "
        f"ARN: {cluster_arn} | "
        f"Recommendation: {recommendation}"
    )
    

    return {
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
        "region": region,
        "resourceNameOrId": nodegroup_name,
        "resourceId": nodegroup_name,
        "resourceArn": cluster_arn,
        "service": SERVICE,
        "type": "EKS Node Group",
        "policy": POLICY_TITLE,
        "effortLevel": "Low",
        "message": "Compute-optimized instance underutilized.",
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
# 9. GENERATE EXCEL OUTPUT
# ============================================================

def generate_excel(findings, output_file):
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


# ============================================================
# 10. MAIN
# ============================================================

def main():

    start_time = time.time()

    print(
        f"Starting FinOps policy: "
        f"{POLICY_TITLE}"
    )

    print(
        f"Region: {REGION}"
    )

    # --------------------------------------------------------
    # Create clients
    # --------------------------------------------------------

    (
        eks,
        ec2,
        cloudwatch,
        sts
    ) = create_clients(REGION)

    autoscaling = boto3.client(
        "autoscaling",
        region_name=REGION,
        config=AWS_CONFIG
    )

    # --------------------------------------------------------
    # Account
    # --------------------------------------------------------

    account_id = get_account_id(sts)

    print(
        f"Account ID: {account_id}"
    )

    # --------------------------------------------------------
    # Fetch clusters
    # --------------------------------------------------------

    clusters = fetch_all_clusters(eks)

    print(
        f"Total EKS clusters found: "
        f"{len(clusters)}"
    )

    findings = []

    total_nodegroups = 0

    # --------------------------------------------------------
    # Scan clusters
    # --------------------------------------------------------

    for cluster_name in clusters:

        print(
            f"Scanning cluster: "
            f"{cluster_name}"
        )

        try:

            nodegroups = fetch_all_nodegroups(
                eks,
                cluster_name
            )

            total_nodegroups += len(
                nodegroups
            )

            for nodegroup_name in nodegroups:

                print(
                    f"  Checking nodegroup: "
                    f"{nodegroup_name}"
                )

                try:

                    finding = evaluate_nodegroup(
                        eks=eks,
                        ec2=ec2,
                        cloudwatch=cloudwatch,
                        autoscaling=autoscaling,
                        cluster_name=cluster_name,
                        nodegroup_name=nodegroup_name,
                        account_id=account_id,
                        region=REGION
                    )

                    if finding:

                        findings.append(
                            finding
                        )

                        print(
                            f"    FINDING: "
                            f"{nodegroup_name}"
                        )

                except Exception as error:

                    print(
                        f"    Error evaluating "
                        f"{nodegroup_name}: "
                        f"{error}"
                    )

        except Exception as error:

            print(
                f"Error scanning cluster "
                f"{cluster_name}: "
                f"{error}"
            )

    # --------------------------------------------------------
    # Generate Excel
    # --------------------------------------------------------

    output_file = (
        "eks_nodegroup_instance_type_mismatch.xlsx"
    )

    generate_excel(
        findings,
        output_file
    )

    duration = (
        time.time() - start_time
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINOPS SCAN COMPLETED")
    print("=" * 70)

    print(
        f"Account ID              : "
        f"{account_id}"
    )

    print(
        f"Region                  : "
        f"{REGION}"
    )

    print(
        f"Clusters scanned        : "
        f"{len(clusters)}"
    )

    print(
        f"Nodegroups scanned      : "
        f"{total_nodegroups}"
    )

    print(
        f"Candidates found        : "
        f"{len(findings)}"
    )

    print(
        f"Output                  : "
        f"{output_file}"
    )

    print(
        f"Scan duration           : "
        f"{duration:.2f} seconds"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()