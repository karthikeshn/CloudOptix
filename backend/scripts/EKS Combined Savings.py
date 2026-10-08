# ============================================================
# AWS FinOps Policy
# Policy : EKS Combined Savings
# Service: EKS
#
# Purpose:
# Identify EKS managed node groups where:
#
# 1. Node instance type can potentially be right-sized
# 2. Graviton migration may be possible
# 3. Node group capacity can potentially be reduced
# 4. Cluster/node group utilization indicates optimization
#
# Important safeguards:
# - Do NOT reduce HA node groups below 2 when HA is required.
# - Do NOT recommend reducing a node group when desired size
#   is already 0.
# - Do NOT recommend scaling below minSize.
# - Do NOT recommend changing disk size.
# - Graviton migration is reported as a candidate only when
#   the current instance family has a known Graviton equivalent.
#
# Cost fields are intentionally left as "To be updated".
# Resource-level cost should be populated from CUR + Athena.
# ============================================================


# ============================================================
# 1. Imports
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timezone

from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2. AWS Configuration
# ============================================================

REGION = "us-east-1"

OUTPUT_FILE = "eks_combined_savings.xlsx"

AWS_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)


# ============================================================
# 3. FinOps Policy Configuration
# ============================================================

POLICY_TITLE = "EKS Combined Savings"

CATEGORY = "EKS Combined Savings"

SERVICE = "EKS"

# CPU threshold used for capacity-right-sizing indication.
CPU_THRESHOLD = 30.0

# Memory threshold used for capacity-right-sizing indication.
MEMORY_THRESHOLD = 50.0

# Minimum reduction percentage before creating a
# capacity recommendation.
CAPACITY_REDUCTION_PERCENT = 25.0

# Protect HA workloads.
HA_MINIMUM_NODES = 2


# ============================================================
# 4. Create AWS Clients
# ============================================================

def create_clients(region_name):

    eks = boto3.client(
        "eks",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return eks, sts


# ============================================================
# 5. Get Account ID
# ============================================================

def get_account_id(sts):

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6. Fetch All Resources with Pagination
# ============================================================

def fetch_all_eks_clusters(eks):

    clusters = []

    paginator = eks.get_paginator(
        "list_clusters"
    )

    for page in paginator.paginate():

        clusters.extend(
            page.get(
                "clusters",
                []
            )
        )

    return clusters


def fetch_all_nodegroups(
    eks,
    cluster_name
):

    nodegroups = []

    paginator = eks.get_paginator(
        "list_nodegroups"
    )

    for page in paginator.paginate(
        clusterName=cluster_name
    ):

        nodegroups.extend(
            page.get(
                "nodegroups",
                []
            )
        )

    return nodegroups


def describe_nodegroup(
    eks,
    cluster_name,
    nodegroup_name
):

    try:

        response = eks.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )

        return response.get(
            "nodegroup",
            {}
        )

    except ClientError as error:

        print(
            f"Unable to describe node group "
            f"{nodegroup_name}: {error}"
        )

        return {}


# ============================================================
# 7. Fetch Additional AWS Data / Metrics
# ============================================================

def get_instance_family(
    instance_type
):

    if not instance_type:

        return ""

    parts = instance_type.split(".")

    if len(parts) < 2:

        return instance_type

    return parts[0]


def get_instance_size(
    instance_type
):

    if not instance_type:

        return ""

    parts = instance_type.split(".")

    if len(parts) < 2:

        return ""

    return parts[1]


def get_graviton_equivalent(
    instance_type
):

    """
    Conservative mapping of common x86 EC2 instance types
    to their Graviton equivalents.

    This is NOT a recommendation to migrate automatically.
    It only identifies a technically corresponding family
    where a known equivalent exists.

    Example:

        m5.large -> m7g.large
        m5.xlarge -> m7g.xlarge
        c5.large -> c7g.large
        r5.large -> r7g.large

    The final recommendation should still consider:
    - OS
    - application compatibility
    - container image architecture
    - native libraries
    - drivers
    - runtime compatibility
    """

    if not instance_type:

        return ""

    mappings = {

        # ----------------------------------------------------
        # General purpose
        # ----------------------------------------------------

        "m5.large": "m7g.large",
        "m5.xlarge": "m7g.xlarge",
        "m5.2xlarge": "m7g.2xlarge",
        "m5.4xlarge": "m7g.4xlarge",
        "m5.8xlarge": "m7g.8xlarge",
        "m5.12xlarge": "m7g.12xlarge",
        "m5.16xlarge": "m7g.16xlarge",
        "m5.24xlarge": "m7g.24xlarge",

        "m6i.large": "m7g.large",
        "m6i.xlarge": "m7g.xlarge",
        "m6i.2xlarge": "m7g.2xlarge",
        "m6i.4xlarge": "m7g.4xlarge",
        "m6i.8xlarge": "m7g.8xlarge",
        "m6i.12xlarge": "m7g.12xlarge",
        "m6i.16xlarge": "m7g.16xlarge",
        "m6i.24xlarge": "m7g.24xlarge",

        # ----------------------------------------------------
        # Compute optimized
        # ----------------------------------------------------

        "c5.large": "c7g.large",
        "c5.xlarge": "c7g.xlarge",
        "c5.2xlarge": "c7g.2xlarge",
        "c5.4xlarge": "c7g.4xlarge",
        "c5.9xlarge": "c7g.8xlarge",
        "c5.12xlarge": "c7g.12xlarge",
        "c5.18xlarge": "c7g.16xlarge",
        "c5.24xlarge": "c7g.24xlarge",

        "c6i.large": "c7g.large",
        "c6i.xlarge": "c7g.xlarge",
        "c6i.2xlarge": "c7g.2xlarge",
        "c6i.4xlarge": "c7g.4xlarge",
        "c6i.8xlarge": "c7g.8xlarge",
        "c6i.12xlarge": "c7g.12xlarge",
        "c6i.16xlarge": "c7g.16xlarge",
        "c6i.24xlarge": "c7g.24xlarge",

        # ----------------------------------------------------
        # Memory optimized
        # ----------------------------------------------------

        "r5.large": "r7g.large",
        "r5.xlarge": "r7g.xlarge",
        "r5.2xlarge": "r7g.2xlarge",
        "r5.4xlarge": "r7g.4xlarge",
        "r5.8xlarge": "r7g.8xlarge",
        "r5.12xlarge": "r7g.12xlarge",
        "r5.16xlarge": "r7g.16xlarge",
        "r5.24xlarge": "r7g.24xlarge",

        "r6i.large": "r7g.large",
        "r6i.xlarge": "r7g.xlarge",
        "r6i.2xlarge": "r7g.2xlarge",
        "r6i.4xlarge": "r7g.4xlarge",
        "r6i.8xlarge": "r7g.8xlarge",
        "r6i.12xlarge": "r7g.12xlarge",
        "r6i.16xlarge": "r7g.16xlarge",
        "r6i.24xlarge": "r7g.24xlarge"
    }

    return mappings.get(
        instance_type,
        ""
    )


def get_scaling_config(
    nodegroup
):

    scaling_config = nodegroup.get(
        "scalingConfig",
        {}
    )

    desired = scaling_config.get(
        "desiredSize"
    )

    minimum = scaling_config.get(
        "minSize"
    )

    maximum = scaling_config.get(
        "maxSize"
    )

    return (
        desired,
        minimum,
        maximum
    )


def get_nodegroup_instance_types(
    nodegroup
):

    instance_types = nodegroup.get(
        "instanceTypes",
        []
    )

    if not instance_types:

        return []

    return instance_types


def get_nodegroup_status(
    nodegroup
):

    return nodegroup.get(
        "status",
        ""
    )


def get_capacity_type(
    nodegroup
):

    return nodegroup.get(
        "capacityType",
        ""
    )


def get_ami_type(
    nodegroup
):

    return nodegroup.get(
        "amiType",
        ""
    )


def get_disk_size(
    nodegroup
):

    return nodegroup.get(
        "diskSize",
        ""
    )


# ============================================================
# 8. Evaluate FinOps Policy
# ============================================================

def evaluate_nodegroup(
    nodegroup,
    cluster_name
):

    nodegroup_name = nodegroup.get(
        "nodegroupName",
        ""
    )

    status = get_nodegroup_status(
        nodegroup
    )

    instance_types = (
        get_nodegroup_instance_types(
            nodegroup
        )
    )

    desired, minimum, maximum = (
        get_scaling_config(
            nodegroup
        )
    )

    capacity_type = get_capacity_type(
        nodegroup
    )

    ami_type = get_ami_type(
        nodegroup
    )

    disk_size = get_disk_size(
        nodegroup
    )

    if not instance_types:

        return {
            "candidate": False,
            "reason": (
                "No EC2 instance type information "
                "available for the node group."
            )
        }

    current_instance = (
        instance_types[0]
    )

    target_instance = (
        get_graviton_equivalent(
            current_instance
        )
    )

    # --------------------------------------------------------
    # Cluster/node group must be ACTIVE.
    # --------------------------------------------------------

    if status != "ACTIVE":

        return {
            "candidate": False,
            "reason": (
                f"Node group status is "
                f"'{status}', therefore no "
                f"optimization recommendation is "
                f"generated."
            )
        }

    # --------------------------------------------------------
    # Already zero.
    #
    # This specifically prevents the false positive from:
    #
    # Desired: 0
    # TargetDesired: 0
    #
    # seen in the sample findings.
    # --------------------------------------------------------

    if desired == 0:

        return {
            "candidate": False,
            "reason": (
                "Node group desired capacity is "
                "already 0. No capacity reduction "
                "recommendation is required."
            ),
            "current_instance": current_instance,
            "target_instance": target_instance,
            "desired": desired,
            "minimum": minimum,
            "maximum": maximum,
            "capacity_type": capacity_type,
            "ami_type": ami_type,
            "disk_size": disk_size
        }

    # --------------------------------------------------------
    # Capacity recommendation.
    #
    # We only create a possible capacity reduction when
    # desired capacity is materially above min capacity.
    # --------------------------------------------------------

    capacity_reduction_candidate = False

    target_desired = desired

    capacity_reason = ""

    if (
        desired is not None
        and minimum is not None
        and desired > minimum
    ):

        reduction_percentage = (
            (
                desired - minimum
            )
            /
            desired
        ) * 100

        if (
            reduction_percentage
            >= CAPACITY_REDUCTION_PERCENT
        ):

            capacity_reduction_candidate = True

            target_desired = minimum

            capacity_reason = (
                f"Desired capacity {desired} "
                f"is above minimum capacity "
                f"{minimum} by "
                f"{reduction_percentage:.1f}%."
            )

    # --------------------------------------------------------
    # HA protection.
    #
    # If current desired is >= 2 and minimum is 1,
    # do NOT automatically recommend 1.
    #
    # The actual HA requirement is application-specific,
    # so the safe default is to preserve 2 nodes.
    # --------------------------------------------------------

    ha_protected = False

    if (
        desired is not None
        and desired >= HA_MINIMUM_NODES
        and target_desired < HA_MINIMUM_NODES
    ):

        target_desired = HA_MINIMUM_NODES

        capacity_reduction_candidate = False

        ha_protected = True

        capacity_reason = (
            "Capacity reduction was blocked because "
            "reducing the node group below 2 nodes "
            "could compromise high availability."
        )

    # --------------------------------------------------------
    # Graviton candidate.
    # --------------------------------------------------------

    graviton_candidate = (
        target_instance != ""
        and
        target_instance != current_instance
    )

    # --------------------------------------------------------
    # Combined candidate.
    # --------------------------------------------------------

    candidate = (
        capacity_reduction_candidate
        or
        graviton_candidate
    )

    reasons = []

    if graviton_candidate:

        reasons.append(
            f"Potential Graviton migration from "
            f"{current_instance} to "
            f"{target_instance}."
        )

    if capacity_reduction_candidate:

        reasons.append(
            f"Potential desired capacity "
            f"reduction from {desired} to "
            f"{target_desired}."
        )

    if ha_protected:

        reasons.append(
            "HA protection prevented capacity "
            "reduction below 2 nodes."
        )

    if not reasons:

        reasons.append(
            "No safe optimization action identified "
            "from the available EKS node group data."
        )

    return {
        "candidate": candidate,
        "reason": " ".join(reasons),
        "current_instance": current_instance,
        "target_instance": target_instance,
        "desired": desired,
        "target_desired": target_desired,
        "minimum": minimum,
        "maximum": maximum,
        "capacity_type": capacity_type,
        "ami_type": ami_type,
        "disk_size": disk_size,
        "graviton_candidate": graviton_candidate,
        "capacity_reduction_candidate": (
            capacity_reduction_candidate
        ),
        "ha_protected": ha_protected,
        "capacity_reason": capacity_reason
    }


# ============================================================
# 9. Build Finding
# ============================================================

def build_finding(
    evaluation,
    nodegroup,
    cluster_name,
    account_id,
    region
):

    nodegroup_name = nodegroup.get(
        "nodegroupName",
        ""
    )

    current_instance = evaluation.get(
        "current_instance",
        ""
    )

    target_instance = evaluation.get(
        "target_instance",
        ""
    )

    desired = evaluation.get(
        "desired",
        ""
    )

    target_desired = evaluation.get(
        "target_desired",
        ""
    )

    minimum = evaluation.get(
        "minimum",
        ""
    )

    maximum = evaluation.get(
        "maximum",
        ""
    )

    capacity_type = evaluation.get(
        "capacity_type",
        ""
    )

    ami_type = evaluation.get(
        "ami_type",
        ""
    )

    disk_size = evaluation.get(
        "disk_size",
        ""
    )

    graviton_candidate = evaluation.get(
        "graviton_candidate",
        False
    )

    capacity_candidate = evaluation.get(
        "capacity_reduction_candidate",
        False
    )

    ha_protected = evaluation.get(
        "ha_protected",
        False
    )

    status = (
        "Pending for Review"
        if evaluation["candidate"]
        else "Not a Candidate"
    )

    # --------------------------------------------------------
    # Node group ARN
    # --------------------------------------------------------

    nodegroup_arn = nodegroup.get(
        "nodegroupArn",
        ""
    )

    # --------------------------------------------------------
    # Description
    #
    # Service-specific fields are bundled here.
    # --------------------------------------------------------

    description = (
        f"AccountId: {account_id} | "
        f"Region: {region} | "
        f"Cluster: {cluster_name} | "
        f"NodeGroup: {nodegroup_name} | "
        f"Status: {nodegroup.get('status', '')} | "
        f"Instance: {current_instance} | "
        f"TargetInstance: {target_instance or 'None'} | "
        f"Capacity: {capacity_type} | "
        f"Desired: {desired} | "
        f"TargetDesired: {target_desired} | "
        f"Min: {minimum} | "
        f"Max: {maximum} | "
        f"AMI: {ami_type} | "
        f"Disk: {disk_size} | "
        f"GravitonCandidate: "
        f"{graviton_candidate} | "
        f"CapacityReductionCandidate: "
        f"{capacity_candidate} | "
        f"HASafeGuard: "
        f"{ha_protected} | "
        f"Recommendation: "
        f"{evaluation['reason']}"
    )

    recommendation_parts = []

    if graviton_candidate:

        recommendation_parts.append(
            f"Review migration from "
            f"{current_instance} to "
            f"{target_instance}."
        )

    if capacity_candidate:

        recommendation_parts.append(
            f"Review reducing desired capacity "
            f"from {desired} to "
            f"{target_desired}."
        )

    if ha_protected:

        recommendation_parts.append(
            "Maintain at least 2 nodes unless "
            "the workload owner confirms that "
            "single-node operation is acceptable."
        )

    if not recommendation_parts:

        recommendation_parts.append(
            "No optimization action recommended."
        )

    recommendation = " ".join(
        recommendation_parts
    )

    return {

        # ----------------------------------------------------
        # Fixed FinOps output schema
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": "",

        "title": POLICY_TITLE,

        "category": CATEGORY,

        "owner": "",

        "assignedTo": "",

        "status": status,

        "areaPath": "AWS Cost Optimization",

        "tags": "",

        "commentCount": 0,

        "accountId": account_id,

        "region": region,

        "resourceNameOrId": nodegroup_name,

        "resourceId": nodegroup_name,

        "resourceArn": nodegroup_arn,

        "service": SERVICE,

        "type": "EKS Node Group",

        "policy": POLICY_TITLE,

        "effortLevel": "Medium",

        "message": evaluation[
            "reason"
        ],

        "recommendation": recommendation,

        "description": description,

        # ----------------------------------------------------
        # Cost comes from CUR + Athena.
        # ----------------------------------------------------

        "currentDailyCost": (
            "To be updated"
        ),

        "currentMonthlyCost": (
            "To be updated"
        ),

        "estimatedMonthlySavings": "",

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": "",

        "month": ""
    }


# ============================================================
# 10. Scan Region
# ============================================================

def scan_region(
    region_name
):

    eks, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    print()
    print(
        f"Account ID : {account_id}"
    )

    print(
        f"Region     : {region_name}"
    )

    print(
        "Fetching EKS clusters..."
    )

    clusters = fetch_all_eks_clusters(
        eks
    )

    print(
        f"EKS clusters found: "
        f"{len(clusters)}"
    )

    findings = []

    total_nodegroups = 0

    candidate_count = 0

    for cluster_name in clusters:

        print()
        print(
            f"Processing cluster: "
            f"{cluster_name}"
        )

        nodegroups = (
            fetch_all_nodegroups(
                eks,
                cluster_name
            )
        )

        print(
            f"Node groups found: "
            f"{len(nodegroups)}"
        )

        total_nodegroups += len(
            nodegroups
        )

        for nodegroup_name in nodegroups:

            print(
                f"  Processing node group: "
                f"{nodegroup_name}"
            )

            nodegroup = (
                describe_nodegroup(
                    eks,
                    cluster_name,
                    nodegroup_name
                )
            )

            if not nodegroup:

                continue

            evaluation = (
                evaluate_nodegroup(
                    nodegroup,
                    cluster_name
                )
            )

            if evaluation[
                "candidate"
            ]:

                candidate_count += 1

                finding = build_finding(
                    evaluation,
                    nodegroup,
                    cluster_name,
                    account_id,
                    region_name
                )

                findings.append(
                    finding
                )

    return {
        "account_id": account_id,
        "region": region_name,
        "clusters_scanned": len(
            clusters
        ),
        "nodegroups_scanned": (
            total_nodegroups
        ),
        "candidate_count": (
            candidate_count
        ),
        "findings": findings
    }


# ============================================================
# 11. Excel Export
# ============================================================

def export_to_excel(
    findings,
    output_file
):

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
        findings
    )

    # Ensure all required columns exist.
    for column in columns:

        if column not in dataframe.columns:

            dataframe[column] = ""

    dataframe = dataframe[
        columns
    ]

    dataframe.to_excel(
        output_file,
        index=False
    )

    print()
    print(
        f"Excel file created: "
        f"{output_file}"
    )

    print(
        f"Findings exported: "
        f"{len(dataframe)}"
    )


# ============================================================
# 12. Main
# ============================================================

def main():

    scan_start_time = datetime.now(
        timezone.utc
    )

    print("=" * 80)

    print(
        "AWS FINOPS POLICY SCAN"
    )

    print("=" * 80)

    print(
        f"Policy  : {POLICY_TITLE}"
    )

    print(
        f"Service : {SERVICE}"
    )

    print(
        f"Region  : {REGION}"
    )

    print("=" * 80)

    result = scan_region(
        REGION
    )

    findings = result[
        "findings"
    ]

    export_to_excel(
        findings,
        OUTPUT_FILE
    )

    scan_end_time = datetime.now(
        timezone.utc
    )

    duration = (
        scan_end_time -
        scan_start_time
    ).total_seconds()

    print()
    print("=" * 80)

    print(
        "SCAN SUMMARY"
    )

    print("=" * 80)

    print(
        f"Account ID           : "
        f"{result['account_id']}"
    )

    print(
        f"Region               : "
        f"{result['region']}"
    )

    print(
        f"Clusters Scanned     : "
        f"{result['clusters_scanned']}"
    )

    print(
        f"Node Groups Scanned  : "
        f"{result['nodegroups_scanned']}"
    )

    print(
        f"Candidates           : "
        f"{result['candidate_count']}"
    )

    print(
        f"Scan Duration        : "
        f"{duration:.2f} seconds"
    )

    print(
        f"Output               : "
        f"{OUTPUT_FILE}"
    )

    print("=" * 80)


if __name__ == "__main__":

    main()