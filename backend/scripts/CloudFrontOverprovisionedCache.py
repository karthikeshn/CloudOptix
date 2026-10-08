
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

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
    "cloudfront-over-provisioned-cache"
)

CATEGORY = (
    "CloudFront Over provisioned Cache"
)

SERVICE_NAME = "CloudFront"

EFFORT_LEVEL = "Medium"

# Cache hit ratio below this value will be
# considered a potential optimization candidate.
#
# 0.0 means almost no requests are being served
# from CloudFront cache.

CACHE_HIT_RATIO_THRESHOLD = 10.0

# Number of days to analyze

LOOKBACK_DAYS = 30


# ============================================================
# CREATE AWS CLIENTS
# ============================================================

def create_clients(
    region_name: str,
):

    # CloudFront is a global service.
    #
    # CloudFront API calls should normally use us-east-1.

    cloudfront = boto3.client(
        "cloudfront",
        region_name="us-east-1",
        config=AWS_CONFIG,
    )

    cloudwatch = boto3.client(
        "cloudwatch",
        region_name="us-east-1",
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    return (
        cloudfront,
        cloudwatch,
        sts,
    )


# ============================================================
# GET ACCOUNT ID
# ============================================================

def get_account_id(
    sts,
) -> str:

    return sts.get_caller_identity()[
        "Account"
    ]


# ============================================================
# FETCH ALL CLOUDFRONT DISTRIBUTIONS
# ============================================================

def fetch_all_distributions(
    cloudfront,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL CloudFront
    distributions.

    Pagination is handled using the
    boto3 paginator.
    """

    distributions = []

    paginator = cloudfront.get_paginator(
        "list_distributions"
    )

    for page in paginator.paginate():

        distribution_list = page.get(
            "DistributionList",
            {}
        )

        items = distribution_list.get(
            "Items",
            []
        )

        distributions.extend(
            items
        )

    return distributions


# ============================================================
# FETCH CLOUDFRONT DISTRIBUTION CONFIGURATION
# ============================================================

def fetch_distribution_config(
    cloudfront,
    distribution_id: str,
) -> Dict[str, Any]:

    try:

        response = (
            cloudfront.get_distribution_config(
                Id=distribution_id
            )
        )

        return response.get(
            "DistributionConfig",
            {}
        )

    except ClientError as e:

        print(
            f"Could not fetch configuration "
            f"for distribution "
            f"{distribution_id}: {e}"
        )

        return {}


# ============================================================
# FETCH CACHE HIT RATE
# ============================================================

def fetch_cache_hit_rate(
    cloudwatch,
    distribution_id: str,
) -> Dict[str, Any]:
    """
    Fetch CloudFront CacheHitRate metric
    for the previous LOOKBACK_DAYS.

    CloudFront metrics are stored in the
    AWS/CloudFront namespace.

    Metric:
        CacheHitRate

    Statistic:
        Average

    Dimension:
        DistributionId
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    try:

        response = (
            cloudwatch.get_metric_statistics(

                Namespace="AWS/CloudFront",

                MetricName="CacheHitRate",

                Dimensions=[

                    {
                        "Name":
                            "DistributionId",

                        "Value":
                            distribution_id,
                    },

                    {
                        "Name":
                            "Region",

                        "Value":
                            "Global",
                    },
                ],

                StartTime=start_time,

                EndTime=end_time,

                Period=86400,

                Statistics=[
                    "Average"
                ],
            )
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        if not datapoints:

            return {

                "cacheHitRate": None,

                "datapoints": 0,

                "startTime":
                    start_time.isoformat(),

                "endTime":
                    end_time.isoformat(),
            }

        values = [

            point["Average"]

            for point in datapoints

            if "Average" in point
        ]

        if not values:

            return {

                "cacheHitRate": None,

                "datapoints":
                    len(datapoints),

                "startTime":
                    start_time.isoformat(),

                "endTime":
                    end_time.isoformat(),
            }

        average_cache_hit_rate = (
            sum(values)
            / len(values)
        )

        return {

            "cacheHitRate":
                round(
                    average_cache_hit_rate,
                    4,
                ),

            "datapoints":
                len(values),

            "startTime":
                start_time.isoformat(),

            "endTime":
                end_time.isoformat(),
        }

    except ClientError as e:

        print(
            f"Could not fetch CacheHitRate "
            f"for distribution "
            f"{distribution_id}: {e}"
        )

        return {

            "cacheHitRate": None,

            "datapoints": 0,

            "error": str(e),
        }


# ============================================================
# FETCH REQUEST COUNT
# ============================================================

def fetch_request_count(
    cloudwatch,
    distribution_id: str,
) -> Dict[str, Any]:
    """
    Fetch total CloudFront requests over
    the configured lookback period.

    Metric:
        Requests
    """

    end_time = datetime.now(
        timezone.utc
    )

    start_time = (
        end_time
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    try:

        response = (
            cloudwatch.get_metric_statistics(

                Namespace="AWS/CloudFront",

                MetricName="Requests",

                Dimensions=[

                    {
                        "Name":
                            "DistributionId",

                        "Value":
                            distribution_id,
                    },

                    {
                        "Name":
                            "Region",

                        "Value":
                            "Global",
                    },
                ],

                StartTime=start_time,

                EndTime=end_time,

                Period=86400,

                Statistics=[
                    "Sum"
                ],
            )
        )

        datapoints = response.get(
            "Datapoints",
            []
        )

        request_count = sum(

            point.get(
                "Sum",
                0
            )

            for point in datapoints
        )

        return {

            "requests":
                int(request_count),

            "datapoints":
                len(datapoints),
        }

    except ClientError as e:

        print(
            f"Could not fetch Requests "
            f"for distribution "
            f"{distribution_id}: {e}"
        )

        return {

            "requests": None,

            "datapoints": 0,

            "error": str(e),
        }


# ============================================================
# GET CACHE BEHAVIOR INFORMATION
# ============================================================

def get_cache_behavior_summary(
    distribution_config: Dict[str, Any],
) -> Dict[str, Any]:

    default_behavior = (
        distribution_config.get(
            "DefaultCacheBehavior",
            {}
        )
    )

    cache_behaviors = (
        distribution_config.get(
            "CacheBehaviors",
            {}
        )
    )

    behavior_items = (
        cache_behaviors.get(
            "Items",
            []
        )
    )

    total_cache_behaviors = (
        1
        + len(behavior_items)
        if default_behavior
        else len(behavior_items)
    )

    return {

        "totalCacheBehaviors":
            total_cache_behaviors,

        "defaultCachePolicyId":
            default_behavior.get(
                "CachePolicyId"
            ),

        "defaultOriginRequestPolicyId":
            default_behavior.get(
                "OriginRequestPolicyId"
            ),

        "defaultViewerProtocolPolicy":
            default_behavior.get(
                "ViewerProtocolPolicy"
            ),

        "compress":
            default_behavior.get(
                "Compress"
            ),
    }


# ============================================================
# GET ORIGIN INFORMATION
# ============================================================

def get_origin_summary(
    distribution_config: Dict[str, Any],
) -> Dict[str, Any]:

    origins = (
        distribution_config.get(
            "Origins",
            {}
        )
    )

    origin_items = (
        origins.get(
            "Items",
            []
        )
    )

    origin_domains = []

    for origin in origin_items:

        domain_name = origin.get(
            "DomainName"
        )

        if domain_name:

            origin_domains.append(
                domain_name
            )

    return {

        "originCount":
            len(origin_items),

        "origins":
            origin_domains,
    }


# ============================================================
# DETERMINE CACHE OPTIMIZATION
# ============================================================

def is_low_cache_hit_ratio(
    cache_hit_rate: float | None,
) -> bool:

    if cache_hit_rate is None:

        return True

    return (
        cache_hit_rate
        < CACHE_HIT_RATIO_THRESHOLD
    )


# ============================================================
# BUILD RECOMMENDATION
# ============================================================

def build_recommendation(
    distribution_id: str,
    domain_name: str,
    cache_hit_rate: float | None,
) -> str:

    if cache_hit_rate is None:

        return (

            f"CloudFront distribution "
            f"{distribution_id} does not have "
            f"sufficient CacheHitRate metrics "
            f"available for the last "
            f"{LOOKBACK_DAYS} days. "
            f"Review the distribution's cache "
            f"configuration and origin "
            f"Cache-Control headers."
        )

    if (
        cache_hit_rate
        < CACHE_HIT_RATIO_THRESHOLD
    ):

        return (

            f"CloudFront distribution "
            f"{distribution_id} "
            f"({domain_name}) has a low average "
            f"cache hit ratio of "
            f"{cache_hit_rate:.2f}% over the "
            f"last {LOOKBACK_DAYS} days. "
            f"Review and optimize the cache "
            f"policy, TTL settings, cache keys, "
            f"and origin Cache-Control headers "
            f"to increase cache reuse and "
            f"reduce unnecessary origin fetches."
        )

    return (

        f"CloudFront distribution "
        f"{distribution_id} "
        f"({domain_name}) has an average "
        f"cache hit ratio of "
        f"{cache_hit_rate:.2f}% over the "
        f"last {LOOKBACK_DAYS} days. "
        f"No immediate cache optimization "
        f"finding is required."
    )


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_cloudfront_finding(
    distribution: Dict[str, Any],
    distribution_config: Dict[str, Any],
    cache_metrics: Dict[str, Any],
    request_metrics: Dict[str, Any],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    distribution_id = distribution.get(
        "Id"
    )

    domain_name = distribution.get(
        "DomainName"
    )

    status = distribution.get(
        "Status"
    )

    enabled = distribution.get(
        "Enabled"
    )

    last_modified_time = distribution.get(
        "LastModifiedTime"
    )

    arn = distribution.get(
        "ARN"
    )

    # --------------------------------------------------------
    # Cache information
    # --------------------------------------------------------

    cache_hit_rate = cache_metrics.get(
        "cacheHitRate"
    )

    request_count = request_metrics.get(
        "requests"
    )

    # --------------------------------------------------------
    # Configuration information
    # --------------------------------------------------------

    cache_summary = (
        get_cache_behavior_summary(
            distribution_config
        )
    )

    origin_summary = (
        get_origin_summary(
            distribution_config
        )
    )

    # --------------------------------------------------------
    # Candidate
    # --------------------------------------------------------

    is_candidate = (
        is_low_cache_hit_ratio(
            cache_hit_rate
        )
    )

    if is_candidate:

        workflow_state = "To Do"

    else:

        workflow_state = "Ignored"

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        build_recommendation(

            distribution_id=
                distribution_id,

            domain_name=
                domain_name,

            cache_hit_rate=
                cache_hit_rate,
        )
    )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    if cache_hit_rate is not None:

        message = (

            f"CloudFront distribution "
            f"{distribution_id} "
            f"({domain_name}) has low cache "
            f"hit ratio "
            f"({cache_hit_rate:.2f}% over "
            f"{LOOKBACK_DAYS} days). "
            f"Optimize caching policy, "
            f"increase appropriate TTL values, "
            f"and add suitable Cache-Control "
            f"headers at the origin to reduce "
            f"origin fetches."
        )

    else:

        message = (

            f"CloudFront distribution "
            f"{distribution_id} "
            f"({domain_name}) could not be "
            f"evaluated because CacheHitRate "
            f"metrics were unavailable for "
            f"the configured analysis period."
        )

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    description = (

        f"accountId: {account_id} | "

        f"region: {region_name} | "

        f"resourceId: {distribution_id} | "

        f"domainName: {domain_name} | "

        f"arn: {arn} | "

        f"category: {CATEGORY} | "

        f"cacheHitRate: "
        f"{cache_hit_rate} | "

        f"lookbackDays: "
        f"{LOOKBACK_DAYS} | "

        f"requests: "
        f"{request_count} | "

        f"enabled: {enabled} | "

        f"status: {status} | "

        f"originCount: "
        f"{origin_summary['originCount']} | "

        f"cacheBehaviors: "
        f"{cache_summary['totalCacheBehaviors']} | "

        f"type: "
        f"Low Cache Hit Ratio | "

        f"policy: {POLICY_NAME} | "

        f"effortLevel: {EFFORT_LEVEL} | "

        f"message: {message}"
    )

    # --------------------------------------------------------
    # Return finding
    # --------------------------------------------------------

    return {

        # ====================================================
        # WORKFLOW
        # ====================================================

        "workItemType":
            "Task",

        "state":
            workflow_state,

        "id":
            "",

        "title":
            CATEGORY,

        "category":
            CATEGORY,

        "owner":
            "",

        "assignedTo":
            "",

        "status":
            "Pending for Review"
            if is_candidate
            else "Ignored",

        "areaPath":
            "AWS Cost Optimization",

        "tags":
            "CLX",

        "commentCount":
            0,

        # ====================================================
        # AWS IDENTITY
        # ====================================================

        "accountId":
            account_id,

        "region":
            region_name,

        "resourceNameOrId":
            distribution_id,

        "resourceId":
            distribution_id,

        "resourceArn":
            arn,

        "service":
            SERVICE_NAME,

        # ====================================================
        # CLOUDFRONT
        # ====================================================

        "distributionId":
            distribution_id,

        "domainName":
            domain_name,

        "status":
            status,

        "enabled":
            enabled,

        "lastModifiedTime":
            (
                last_modified_time.isoformat()
                if last_modified_time
                else None
            ),

        # ====================================================
        # CACHE METRICS
        # ====================================================

        "cacheHitRate":
            cache_hit_rate,

        "cacheHitRateLookbackDays":
            LOOKBACK_DAYS,

        "requestCount":
            request_count,

        "cacheMetricDatapoints":
            cache_metrics.get(
                "datapoints"
            ),

        # ====================================================
        # CACHE CONFIGURATION
        # ====================================================

        "totalCacheBehaviors":
            cache_summary[
                "totalCacheBehaviors"
            ],

        "defaultCachePolicyId":
            cache_summary[
                "defaultCachePolicyId"
            ],

        "defaultOriginRequestPolicyId":
            cache_summary[
                "defaultOriginRequestPolicyId"
            ],

        "defaultViewerProtocolPolicy":
            cache_summary[
                "defaultViewerProtocolPolicy"
            ],

        "compress":
            cache_summary[
                "compress"
            ],

        # ====================================================
        # ORIGIN
        # ====================================================

        "originCount":
            origin_summary[
                "originCount"
            ],

        "origins":
            origin_summary[
                "origins"
            ],

        # ====================================================
        # FINOPS
        # ====================================================

        "isCandidate":
            is_candidate,

        "type":
            "Low Cache Hit Ratio",

        "policy":
            POLICY_NAME,

        "effortLevel":
            EFFORT_LEVEL,

        "message":
            message,

        "recommendation":
            recommendation,

        "description":
            description,

        # ====================================================
        # COST
        #
        # Populate using CUR + Athena.
        # ====================================================

        "currentDailyCost":
            None,

        "currentMonthlyCost":
            None,

        "estimatedMonthlySavings":
            None,

        # ====================================================
        # WORKFLOW
        # ====================================================

        "approvalComments":
            "",

        "reasonForRejection":
            "",

        "achievedSavingsMonthly":
            "",

        "month":
            "",
    }


# ============================================================
# SCAN ALL CLOUDFRONT DISTRIBUTIONS
# ============================================================

def scan_cloudfront(
    region_name: str,
) -> Dict[str, Any]:

    (
        cloudfront,
        cloudwatch,
        sts,
    ) = create_clients(
        region_name
    )

    # --------------------------------------------------------
    # Account ID
    # --------------------------------------------------------

    account_id = get_account_id(
        sts
    )

    print(
        f"\nAccount ID: {account_id}"
    )

    print(
        f"Region: {region_name}"
    )

    # --------------------------------------------------------
    # Fetch ALL distributions
    # --------------------------------------------------------

    distributions = (
        fetch_all_distributions(
            cloudfront
        )
    )

    print(
        f"Total CloudFront "
        f"distributions: "
        f"{len(distributions)}"
    )

    findings = []

    total_metrics_checked = 0

    # --------------------------------------------------------
    # Process every distribution
    # --------------------------------------------------------

    for distribution in distributions:

        distribution_id = distribution.get(
            "Id"
        )

        domain_name = distribution.get(
            "DomainName"
        )

        print(
            f"\nScanning distribution: "
            f"{distribution_id}"
        )

        print(
            f"Domain: "
            f"{domain_name}"
        )

        # ----------------------------------------------------
        # Fetch configuration
        # ----------------------------------------------------

        distribution_config = (
            fetch_distribution_config(

                cloudfront,

                distribution_id,
            )
        )

        # ----------------------------------------------------
        # Fetch CacheHitRate
        # ----------------------------------------------------

        cache_metrics = (
            fetch_cache_hit_rate(

                cloudwatch,

                distribution_id,
            )
        )

        # ----------------------------------------------------
        # Fetch Requests
        # ----------------------------------------------------

        request_metrics = (
            fetch_request_count(

                cloudwatch,

                distribution_id,
            )
        )

        total_metrics_checked += 1

        cache_hit_rate = (
            cache_metrics.get(
                "cacheHitRate"
            )
        )

        print(
            f"Cache hit rate: "
            f"{cache_hit_rate}"
        )

        # ----------------------------------------------------
        # Only create finding when the
        # distribution meets the policy.
        # ----------------------------------------------------

        if not is_low_cache_hit_ratio(
            cache_hit_rate
        ):

            print(
                "No low cache hit ratio "
                "finding."
            )

            continue

        # ----------------------------------------------------
        # Build finding
        # ----------------------------------------------------

        finding = build_cloudfront_finding(

            distribution=
                distribution,

            distribution_config=
                distribution_config,

            cache_metrics=
                cache_metrics,

            request_metrics=
                request_metrics,

            account_id=
                account_id,

            region_name=
                region_name,
        )

        findings.append(
            finding
        )

        print(
            "Finding created."
        )

    # --------------------------------------------------------
    # Return scan result
    # --------------------------------------------------------

    return {

        "accountId":
            account_id,

        "region":
            region_name,

        "totalDistributionsScanned":
            len(distributions),

        "totalMetricsChecked":
            total_metrics_checked,

        "totalFindings":
            len(findings),

        "findings":
            findings,
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
    # CloudFront is a global service.
    #
    # The CloudFront API and CloudWatch metrics
    # are accessed through us-east-1.
    #
    # The region field in the final report can be
    # represented as Global.
    # --------------------------------------------------------

    region = "us-east-1"

    print(
        "\n=========================================="
    )

    print(
        "AWS CLOUDFRONT CACHE OPTIMIZATION SCANNER"
    )

    print(
        "=========================================="
    )

    print(
        f"Region: {region}"
    )

    print(
        f"Lookback: {LOOKBACK_DAYS} days"
    )

    print(
        f"Cache hit ratio threshold: "
        f"{CACHE_HIT_RATIO_THRESHOLD}%"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # Scan
    # --------------------------------------------------------

    result = scan_cloudfront(
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
        "Total Distributions:",
        result.get(
            "totalDistributionsScanned"
        )
    )

    print(
        "Metrics Checked:",
        result.get(
            "totalMetricsChecked"
        )
    )

    print(
        "Findings:",
        result.get(
            "totalFindings"
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
            "\nNo CloudFront cache "
            "optimization findings found."
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    excel_file = (
        "cloudfront_cache_optimization_report.xlsx"
    )

    export_to_excel(

        findings=findings,

        filename=excel_file,
    )

    print(
        "\nCompleted."
    )

