# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import pandas as pd

from datetime import datetime, timedelta, timezone
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

POLICY_NAME = "Enable Predictive Scaling"
CATEGORY = "Enable Predictive Scaling"
SERVICE_NAME = "Auto Scaling"

LOOKBACK_DAYS = 30

# Minimum variability required before recommending
# Predictive Scaling.
#
# variability_ratio =
# (max_desired_capacity - min_desired_capacity)
# / average_desired_capacity
#
# Example:
# min = 0
# max = 8
# avg = 6
# ratio = 1.33
#
# The sample findings use a ratio of approximately 2.
# A ratio of 1.0 is used as a reasonable configurable
# starting threshold.
VARIABILITY_RATIO_THRESHOLD = 1.0

# Minimum number of capacity datapoints required
# before evaluating an ASG.
MIN_DATAPOINTS_REQUIRED = 2

# Used only for the heuristic estimate shown in description.
# This is NOT used as an actual AWS cost calculation.
HEURISTIC_MONTHLY_COST_PER_CAPACITY_UNIT = 25.0


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients.
    """

    autoscaling = boto3.client(
        "autoscaling",
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

    return autoscaling, cloudwatch, sts


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

def fetch_all_auto_scaling_groups(autoscaling):
    """
    Fetch all Auto Scaling Groups using AWS pagination.
    """

    groups = []

    paginator = autoscaling.get_paginator(
        "describe_auto_scaling_groups"
    )

    for page in paginator.paginate():

        groups.extend(
            page.get(
                "AutoScalingGroups",
                []
            )
        )

    return groups


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_predictive_scaling_policies(
    autoscaling,
    auto_scaling_group_name
):
    """
    Fetch Predictive Scaling policies configured for
    the specified Auto Scaling Group.

    Returns a list of predictive scaling policies.
    """
        
    policies = []

    paginator = autoscaling.get_paginator(
        "describe_policies"
    )

    for page in paginator.paginate(
        AutoScalingGroupName=auto_scaling_group_name,
        PolicyTypes=[
            "PredictiveScaling"
        ]
    ):

        policies.extend(
            page.get(
                "ScalingPolicies",
                []
            )
        )

    return policies


def is_predictive_scaling_enabled(
    autoscaling,
    auto_scaling_group_name
):
    """
    Determine whether Predictive Scaling is configured
    for the Auto Scaling Group.
    """

    policies = get_predictive_scaling_policies(
        autoscaling,
        auto_scaling_group_name
    )

    for policy in policies:

        if policy.get(
            "PolicyType"
        ) == "PredictiveScaling":

            return True

    return False


def fetch_desired_capacity_metrics(
    cloudwatch,
    auto_scaling_group_name,
    start_time,
    end_time
):
    """
    Fetch GroupDesiredCapacity from CloudWatch for the
    Auto Scaling Group over the configured lookback period.

    AWS/AutoScaling metric:
        GroupDesiredCapacity

    Dimension:
        AutoScalingGroupName
    """
        
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/AutoScaling",
        MetricName="GroupDesiredCapacity",
        Dimensions=[
            {
                "Name": "AutoScalingGroupName",
                "Value": auto_scaling_group_name
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=[
            "Average"
        ]
    )

    datapoints = response.get(
        "Datapoints",
        []
    )

    datapoints.sort(
        key=lambda x: x.get(
            "Timestamp",
            datetime.min.replace(
                tzinfo=timezone.utc
            )
        )
    )

    return datapoints


def calculate_capacity_statistics(
    datapoints
):
    """
    Calculate min, max, average and variability ratio
    from desired-capacity datapoints.
    """

    values = [
        float(dp["Average"])
        for dp in datapoints
        if dp.get("Average") is not None
    ]

    if len(values) < MIN_DATAPOINTS_REQUIRED:
        return None

    min_capacity = min(values)
    max_capacity = max(values)
    avg_capacity = sum(values) / len(values)

    if avg_capacity > 0:
        variability_ratio = (
            (max_capacity - min_capacity)
            / avg_capacity
        )
    else:
        variability_ratio = 0.0

    return {
        "datapoints": len(values),
        "minCapacity": min_capacity,
        "maxCapacity": max_capacity,
        "avgCapacity": avg_capacity,
        "variabilityRatio": variability_ratio
    }


def get_group_tags(
    autoscaling,
    auto_scaling_group
):
    """
    Extract Auto Scaling Group tags.
    """

    tags = auto_scaling_group.get(
        "Tags",
        []
    )

    return tags


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

def evaluate_predictive_scaling_policy(
    autoscaling,
    cloudwatch,
    auto_scaling_group,
    start_time,
    end_time
):
    """
    Evaluate whether an Auto Scaling Group is a candidate
    for Predictive Scaling.
    """

    asg_name = auto_scaling_group.get(
        "AutoScalingGroupName",
        ""
    )

    if not asg_name:
        return None

    # --------------------------------------------------------
    # Check current Predictive Scaling configuration.
    # --------------------------------------------------------

    predictive_scaling_enabled = (
        is_predictive_scaling_enabled(
            autoscaling,
            asg_name
        )
    )

    # Already enabled -> no finding.
    if predictive_scaling_enabled:
        return None

    # --------------------------------------------------------
    # Fetch desired capacity history.
    # --------------------------------------------------------

    datapoints = fetch_desired_capacity_metrics(
        cloudwatch=cloudwatch,
        auto_scaling_group_name=asg_name,
        start_time=start_time,
        end_time=end_time
    )

    statistics = calculate_capacity_statistics(
        datapoints
    )

    if not statistics:
        return None

    # --------------------------------------------------------
    # Check capacity variability.
    # --------------------------------------------------------

    variability_ratio = statistics[
        "variabilityRatio"
    ]

    if (
        variability_ratio
        < VARIABILITY_RATIO_THRESHOLD
    ):
        return None

    # --------------------------------------------------------
    # Return candidate.
    # --------------------------------------------------------

    return {
        "autoScalingGroupName": asg_name,

        "autoScalingGroupArn":
            auto_scaling_group.get(
                "AutoScalingGroupARN",
                ""
            ),

        "minSize":
            auto_scaling_group.get(
                "MinSize",
                0
            ),

        "maxSize":
            auto_scaling_group.get(
                "MaxSize",
                0
            ),

        "desiredCapacity":
            auto_scaling_group.get(
                "DesiredCapacity",
                0
            ),

        "capacityStatistics":
            statistics,

        "instanceCount":
            len(
                auto_scaling_group.get(
                    "Instances",
                    []
                )
            ),

        "healthCheckType":
            auto_scaling_group.get(
                "HealthCheckType",
                ""
            ),

        "healthCheckGracePeriod":
            auto_scaling_group.get(
                "HealthCheckGracePeriod",
                0
            ),

        "availabilityZones":
            auto_scaling_group.get(
                "AvailabilityZones",
                []
            ),

        "launchTemplate":
            auto_scaling_group.get(
                "LaunchTemplate"
            ),

        "mixedInstancesPolicy":
            auto_scaling_group.get(
                "MixedInstancesPolicy"
            )
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
    Build a finding using the exact standard 30-column schema.
    """

    asg_name = candidate[
        "autoScalingGroupName"
    ]

    stats = candidate[
        "capacityStatistics"
    ]

    min_capacity = stats[
        "minCapacity"
    ]

    max_capacity = stats[
        "maxCapacity"
    ]

    avg_capacity = stats[
        "avgCapacity"
    ]

    variability_ratio = stats[
        "variabilityRatio"
    ]

    datapoints = stats[
        "datapoints"
    ]

    # --------------------------------------------------------
    # Heuristic estimate.
    #
    # This is intentionally kept inside description only.
    # It is NOT written to estimatedMonthlySavings because
    # it is not an actual AWS cost calculation.
    # --------------------------------------------------------

    heuristic_savings = (
        avg_capacity
        * variability_ratio
        * HEURISTIC_MONTHLY_COST_PER_CAPACITY_UNIT
    )

    heuristic_annual_savings = (
        heuristic_savings * 12
    )

    availability_zones = candidate[
        "availabilityZones"
    ]

    az_text = (
        ", ".join(availability_zones)
        if availability_zones
        else "Not available"
    )

    message = (
        f"Auto Scaling Group '{asg_name}' does not have "
        f"Predictive Scaling enabled. Over the last "
        f"{LOOKBACK_DAYS} days, desired capacity varied "
        f"from {min_capacity:.2f} to {max_capacity:.2f}, "
        f"with an average of {avg_capacity:.2f}."
    )

    recommendation = (
        "Review the workload's recurring demand pattern and "
        "consider enabling Predictive Scaling if demand is "
        "predictable. Validate the forecast, minimum/maximum "
        "capacity requirements and application behavior before "
        "enabling the policy."
    )

    description = (
        f"Auto Scaling Group "
        f"**{asg_name}** does not have Predictive Scaling "
        f"enabled.<br>"
        f" → Analysis period: {LOOKBACK_DAYS} days<br>"
        f" → Desired capacity datapoints: {datapoints}<br>"
        f" → Minimum desired capacity: {min_capacity:.2f}<br>"
        f" → Maximum desired capacity: {max_capacity:.2f}<br>"
        f" → Average desired capacity: {avg_capacity:.2f}<br>"
        f" → Variability ratio: {variability_ratio:.2f}<br>"
        f" → Current configured minimum: "
        f"{candidate['minSize']}<br>"
        f" → Current configured maximum: "
        f"{candidate['maxSize']}<br>"
        f" → Current desired capacity: "
        f"{candidate['desiredCapacity']}<br>"
        f" → Current instances: "
        f"{candidate['instanceCount']}<br>"
        f" → Availability Zones: {az_text}<br>"
        f" → Health check type: "
        f"{candidate['healthCheckType'] or 'Not available'}<br>"
        f" → Predictive Scaling: Not enabled<br>"
        f" → The observed capacity variation suggests that "
        f"Predictive Scaling may be worth evaluating for "
        f"recurring or forecastable demand.<br>"
        f" → Heuristic savings reference: "
        f"avg desired capacity × variability ratio × "
        f"${HEURISTIC_MONTHLY_COST_PER_CAPACITY_UNIT:.0f}/month "
        f"= approximately ${heuristic_savings:.2f}/month "
        f"(${heuristic_annual_savings:.2f}/year). "
        f"This is a heuristic estimate only and must not be "
        f"treated as actual AWS savings.<br>"
        f" → Action: Review the forecast and workload pattern, "
        f"then enable Predictive Scaling if technically and "
        f"operationally appropriate."
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
        "resourceNameOrId": asg_name,
        "resourceId": asg_name,
        "resourceArn": candidate[
            "autoScalingGroupArn"
        ],
        "service": SERVICE_NAME,
        "type": "Auto Scaling Group",
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

def scan_predictive_scaling(
    autoscaling,
    cloudwatch,
    account_id,
    region
):
    """
    Scan all Auto Scaling Groups in the region.
    """

    auto_scaling_groups = (
        fetch_all_auto_scaling_groups(
            autoscaling
        )
    )

    findings = []

    total_asgs_scanned = 0
    predictive_scaling_enabled_count = 0
    predictive_scaling_disabled_count = 0
    capacity_variation_candidates = 0

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    for auto_scaling_group in auto_scaling_groups:

        total_asgs_scanned += 1

        asg_name = auto_scaling_group.get(
            "AutoScalingGroupName",
            ""
        )

        if not asg_name:
            continue

        try:

            # ------------------------------------------------
            # Check Predictive Scaling.
            # ------------------------------------------------

            predictive_enabled = (
                is_predictive_scaling_enabled(
                    autoscaling,
                    asg_name
                )
            )

            if predictive_enabled:

                predictive_scaling_enabled_count += 1

                continue

            predictive_scaling_disabled_count += 1

            # ------------------------------------------------
            # Evaluate capacity variability.
            # ------------------------------------------------

            candidate = (
                evaluate_predictive_scaling_policy(
                    autoscaling=autoscaling,
                    cloudwatch=cloudwatch,
                    auto_scaling_group=
                        auto_scaling_group,
                    start_time=start_time,
                    end_time=end_time
                )
            )

            if not candidate:
                continue

            capacity_variation_candidates += 1

            # ------------------------------------------------
            # Tags
            # ------------------------------------------------

            tags = get_group_tags(
                autoscaling,
                auto_scaling_group
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
                f"Warning: Failed to process ASG "
                f"'{asg_name}': {exc}"
            )

    return {
        "findings": findings,
        "totalASGsScanned": total_asgs_scanned,
        "predictiveScalingEnabled":
            predictive_scaling_enabled_count,
        "predictiveScalingDisabled":
            predictive_scaling_disabled_count,
        "capacityVariationCandidates":
            capacity_variation_candidates,
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
    Export findings using the exact 30-column schema.
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
    print("AWS FINOPS - ENABLE PREDICTIVE SCALING")
    print("=" * 70)

    print(f"Region : {REGION}")
    print(f"Policy : {POLICY_NAME}")
    print(
        f"Lookback : {LOOKBACK_DAYS} days"
    )
    print(
        f"Variability threshold : "
        f"{VARIABILITY_RATIO_THRESHOLD}"
    )
    print()

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    autoscaling, cloudwatch, sts = (
        create_clients(REGION)
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

    result = scan_predictive_scaling(
        autoscaling=autoscaling,
        cloudwatch=cloudwatch,
        account_id=account_id,
        region=REGION
    )

    scan_end = datetime.now(
        timezone.utc
    )

    duration = (
        scan_end - scan_start
    ).total_seconds()

    findings = result[
        "findings"
    ]

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    output_file = (
        "enable_predictive_scaling_findings.xlsx"
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
        f"Total ASGs scanned              : "
        f"{result['totalASGsScanned']}"
    )

    print(
        f"Predictive Scaling enabled      : "
        f"{result['predictiveScalingEnabled']}"
    )

    print(
        f"Predictive Scaling disabled     : "
        f"{result['predictiveScalingDisabled']}"
    )

    print(
        f"Capacity variation candidates   : "
        f"{result['capacityVariationCandidates']}"
    )

    print(
        f"Total findings                  : "
        f"{result['totalCandidates']}"
    )

    print(
        f"Scan duration                   : "
        f"{duration:.2f} seconds"
    )

    print(
        f"Output file                     : "
        f"{output_file}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()


    