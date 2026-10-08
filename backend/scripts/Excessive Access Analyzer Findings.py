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

POLICY_NAME = "Excessive Access Analyzer Findings"
CATEGORY = "Excessive Access Analyzer Findings"
SERVICE_NAME = "IAM Access Analyzer"

# Minimum number of findings before an analyzer is considered
# excessive.
#
# This is configurable because "excessive" is a FinOps
# governance threshold rather than an AWS-defined threshold.
MIN_FINDINGS_THRESHOLD = 100

# Percentage of findings considered potentially excess before
# generating a finding.
#
# Example:
# Total findings = 466
# Potential excess = 366
# Excess percentage = 78.54%
#
# The sample findings have a large excess count, so this
# threshold is configurable.
EXCESS_PERCENTAGE_THRESHOLD = 50.0

# Heuristic annual value per excess finding.
#
# IMPORTANT:
# This is NOT an AWS billing calculation.
# It is only used as a reference in the description.
HEURISTIC_ANNUAL_SAVINGS_PER_FINDING = 1.20


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients.
    """

    accessanalyzer = boto3.client(
        "accessanalyzer",
        region_name=region_name,
        config=AWS_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=AWS_CONFIG
    )

    return accessanalyzer, sts


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

def fetch_all_analyzers(accessanalyzer):
    """
    Fetch all IAM Access Analyzer analyzers in the region.
    """

    analyzers = []

    paginator = accessanalyzer.get_paginator(
        "list_analyzers"
    )

    for page in paginator.paginate():

        analyzers.extend(
            page.get(
                "analyzers",
                []
            )
        )

    return analyzers


def fetch_all_findings(
    accessanalyzer,
    analyzer_arn
):
    """
    Fetch all findings for an Access Analyzer.

    Uses the AWS paginator so analyzers with large numbers
    of findings are handled correctly.
    """
        
    findings = []

    paginator = accessanalyzer.get_paginator(
        "list_findings"
    )

    try:

        for page in paginator.paginate(
            analyzerArn=analyzer_arn
        ):

            findings.extend(
                page.get(
                    "findings",
                    []
                )
            )

    except Exception as exc:

        print(
            f"Warning: Unable to retrieve findings for "
            f"analyzer '{analyzer_arn}': {exc}"
        )

    return findings


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_analyzer_tags(
    accessanalyzer,
    analyzer_arn
):
    """
    Fetch tags associated with an Access Analyzer analyzer.
    """

    if not analyzer_arn:
        return []

    try:

        response = accessanalyzer.list_tags_for_resource(
            resourceArn=analyzer_arn
        )

        return response.get(
            "tags",
            []
        )

    except Exception as exc:

        print(
            f"Warning: Unable to fetch tags for "
            f"{analyzer_arn}: {exc}"
        )

        return []


def build_tag_string(tags):
    """
    Convert AWS tags into a string.
    """

    if not tags:
        return ""

    return "; ".join(
        f"{tag.get('key', '')}={tag.get('value', '')}"
        for tag in tags
    )


def calculate_finding_summary(findings):
    """
    Calculate finding statistics.

    Access Analyzer findings can have statuses such as:
        ACTIVE
        ARCHIVED
        RESOLVED

    For excessive-finding analysis, the primary count is
    based on ACTIVE findings because archived findings are
    already handled and should not be treated as outstanding
    findings.
    """

    total_findings = len(findings)

    active_findings = 0
    archived_findings = 0
    resolved_findings = 0

    for finding in findings:

        status = (
            finding.get("status") or ""
        ).upper()

        if status == "ACTIVE":
            active_findings += 1

        elif status == "ARCHIVED":
            archived_findings += 1

        elif status == "RESOLVED":
            resolved_findings += 1

    return {
        "totalFindings": total_findings,
        "activeFindings": active_findings,
        "archivedFindings": archived_findings,
        "resolvedFindings": resolved_findings
    }


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_excessive_findings(
    accessanalyzer,
    analyzer
):
    """
    Evaluate whether an Access Analyzer has an excessive
    number of active findings.
    """

    analyzer_arn = analyzer.get(
        "arn",
        ""
    )

    analyzer_name = analyzer.get(
        "name",
        ""
    )

    analyzer_type = analyzer.get(
        "type",
        ""
    )

    status = analyzer.get(
        "status",
        ""
    )

    created_at = analyzer.get(
        "createdAt"
    )

    last_resource_analyzed_at = analyzer.get(
        "lastResourceAnalyzedAt"
    )

    if not analyzer_arn:
        return None

    # --------------------------------------------------------
    # Fetch findings.
    # --------------------------------------------------------

    findings = fetch_all_findings(
        accessanalyzer=accessanalyzer,
        analyzer_arn=analyzer_arn
    )

    summary = calculate_finding_summary(
        findings
    )

    total_findings = summary[
        "totalFindings"
    ]

    active_findings = summary[
        "activeFindings"
    ]

    archived_findings = summary[
        "archivedFindings"
    ]

    resolved_findings = summary[
        "resolvedFindings"
    ]

    # --------------------------------------------------------
    # Only active findings should drive the recommendation.
    # --------------------------------------------------------

    if active_findings < MIN_FINDINGS_THRESHOLD:
        return None

    # --------------------------------------------------------
    # Calculate potentially excessive findings.
    #
    # We cannot know from the API alone which findings are
    # genuinely obsolete. Therefore the scanner identifies
    # the excess population for review rather than blindly
    # archiving findings.
    # --------------------------------------------------------

    excess_findings = (
        active_findings
        - MIN_FINDINGS_THRESHOLD
    )

    if excess_findings <= 0:
        return None

    excess_percentage = (
        excess_findings
        / active_findings
        * 100
    )

    if (
        excess_percentage
        < EXCESS_PERCENTAGE_THRESHOLD
    ):
        return None

    # --------------------------------------------------------
    # Heuristic savings.
    #
    # This is only a reference value.
    # --------------------------------------------------------

    estimated_annual_savings = (
        excess_findings
        * HEURISTIC_ANNUAL_SAVINGS_PER_FINDING
    )

    estimated_monthly_savings = (
        estimated_annual_savings
        / 12
    )

    return {
        "analyzerArn": analyzer_arn,
        "analyzerName": analyzer_name,
        "analyzerType": analyzer_type,
        "status": status,
        "createdAt": created_at,
        "lastResourceAnalyzedAt":
            last_resource_analyzed_at,
        "totalFindings": total_findings,
        "activeFindings": active_findings,
        "archivedFindings": archived_findings,
        "resolvedFindings": resolved_findings,
        "excessFindings": excess_findings,
        "excessPercentage": excess_percentage,
        "estimatedAnnualSavings":
            estimated_annual_savings,
        "estimatedMonthlySavings":
            estimated_monthly_savings
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

    analyzer_name = candidate[
        "analyzerName"
    ]

    analyzer_arn = candidate[
        "analyzerArn"
    ]

    analyzer_type = candidate[
        "analyzerType"
    ]

    status = candidate[
        "status"
    ]

    total_findings = candidate[
        "totalFindings"
    ]

    active_findings = candidate[
        "activeFindings"
    ]

    archived_findings = candidate[
        "archivedFindings"
    ]

    resolved_findings = candidate[
        "resolvedFindings"
    ]

    excess_findings = candidate[
        "excessFindings"
    ]

    excess_percentage = candidate[
        "excessPercentage"
    ]

    estimated_monthly_savings = candidate[
        "estimatedMonthlySavings"
    ]

    estimated_annual_savings = candidate[
        "estimatedAnnualSavings"
    ]

    created_at = candidate[
        "createdAt"
    ]

    last_resource_analyzed_at = candidate[
        "lastResourceAnalyzedAt"
    ]

    message = (
        f"Access Analyzer '{analyzer_name}' has "
        f"{active_findings} active findings, of which "
        f"{excess_findings} are above the configured "
        f"review threshold of {MIN_FINDINGS_THRESHOLD}."
    )

    recommendation = (
        "Review active Access Analyzer findings and identify "
        "old, irrelevant, duplicate or already-remediated "
        "findings. Archive findings only after validating "
        "that they no longer represent a required security "
        "condition. Avoid automatically archiving findings "
        "solely because the count is high."
    )

    description = (
        f"Access Analyzer "
        f"**{analyzer_name}** in {region} has a high number "
        f"of active findings and should be reviewed.<br>"
        f" → Analyzer type: "
        f"{analyzer_type or 'Not available'}<br>"
        f" → Analyzer status: "
        f"{status or 'Not available'}<br>"
        f" → Total findings: {total_findings}<br>"
        f" → Active findings: {active_findings}<br>"
        f" → Archived findings: {archived_findings}<br>"
        f" → Resolved findings: {resolved_findings}<br>"
        f" → Review threshold: "
        f"{MIN_FINDINGS_THRESHOLD} active findings<br>"
        f" → Findings above threshold: "
        f"{excess_findings}<br>"
        f" → Excess percentage relative to active findings: "
        f"{excess_percentage:.2f}%<br>"
        f" → Created at: "
        f"{created_at if created_at else 'Not available'}<br>"
        f" → Last resource analyzed at: "
        f"{last_resource_analyzed_at if last_resource_analyzed_at else 'Not available'}<br>"
        f" → Heuristic annual value: "
        f"~${estimated_annual_savings:.2f}<br>"
        f" → Heuristic monthly value: "
        f"~${estimated_monthly_savings:.2f}<br>"
        f" → The heuristic value is not an AWS billing "
        f"calculation and should not be treated as realized "
        f"cost savings.<br>"
        f" → Action: Review the active findings and archive "
        f"only those that are confirmed to be obsolete or "
        f"irrelevant."
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
        "resourceNameOrId": analyzer_name,
        "resourceId": analyzer_arn,
        "resourceArn": analyzer_arn,
        "service": SERVICE_NAME,
        "type": "Access Analyzer",
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

def scan_excessive_access_analyzer_findings(
    accessanalyzer,
    account_id,
    region
):
    """
    Scan all Access Analyzer analyzers in the region.
    """

    analyzers = fetch_all_analyzers(
        accessanalyzer
    )

    findings = []

    total_analyzers_scanned = 0
    total_analyzers_with_findings = 0
    total_active_findings = 0

    for analyzer in analyzers:

        total_analyzers_scanned += 1

        analyzer_name = analyzer.get(
            "name",
            ""
        )

        try:

            candidate = evaluate_excessive_findings(
                accessanalyzer=accessanalyzer,
                analyzer=analyzer
            )

            # ------------------------------------------------
            # Count active findings for summary.
            # ------------------------------------------------

            if candidate:

                total_analyzers_with_findings += 1

                total_active_findings += candidate[
                    "activeFindings"
                ]

                # --------------------------------------------
                # Fetch tags.
                # --------------------------------------------

                tags = get_analyzer_tags(
                    accessanalyzer,
                    candidate["analyzerArn"]
                )

                tag_string = build_tag_string(
                    tags
                )

                # --------------------------------------------
                # Build finding.
                # --------------------------------------------

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
                f"Access Analyzer '{analyzer_name}': "
                f"{exc}"
            )

    return {
        "findings": findings,
        "totalAnalyzersScanned":
            total_analyzers_scanned,
        "totalAnalyzersWithExcessiveFindings":
            total_analyzers_with_findings,
        "totalActiveFindings":
            total_active_findings,
        "totalCandidates":
            len(findings)
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
    print(
        "AWS FINOPS - EXCESSIVE ACCESS ANALYZER FINDINGS"
    )
    print("=" * 70)

    print(f"Region : {REGION}")
    print(f"Policy : {POLICY_NAME}")
    print(
        f"Finding threshold : "
        f"{MIN_FINDINGS_THRESHOLD}"
    )
    print(
        f"Excess percentage threshold : "
        f"{EXCESS_PERCENTAGE_THRESHOLD}%"
    )
    print()

    # --------------------------------------------------------
    # Create AWS clients
    # --------------------------------------------------------

    accessanalyzer, sts = create_clients(
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

    result = (
        scan_excessive_access_analyzer_findings(
            accessanalyzer=accessanalyzer,
            account_id=account_id,
            region=REGION
        )
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
        "excessive_access_analyzer_findings.xlsx"
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
        f"Total analyzers scanned              : "
        f"{result['totalAnalyzersScanned']}"
    )

    print(
        f"Analyzers with excessive findings    : "
        f"{result['totalAnalyzersWithExcessiveFindings']}"
    )

    print(
        f"Active findings in candidates        : "
        f"{result['totalActiveFindings']}"
    )

    print(
        f"Total FinOps candidates               : "
        f"{result['totalCandidates']}"
    )

    print(
        f"Scan duration                         : "
        f"{duration:.2f} seconds"
    )

    print(
        f"Output file                           : "
        f"{output_file}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()