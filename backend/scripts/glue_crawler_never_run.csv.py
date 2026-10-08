# ============================================================
# AWS FINOPS POLICY
# Glue Crawler Never Run
#
# Policy:
# Identify AWS Glue Crawlers that have never completed
# a successful crawl.
#
# Recommended action:
# Review and delete unused/abandoned Glue Crawlers.
#
# Cost:
# Glue Crawlers do not have a simple fixed resource-level
# monthly charge. Current cost should be obtained through
# CUR + Athena where applicable.
# ============================================================


# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import logging
import time
import pandas as pd

from datetime import datetime, timezone
from decimal import Decimal
from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2. AWS CONFIGURATION
# ============================================================

AWS_REGION = "us-east-1"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

OUTPUT_FILE = "glue_crawler_never_run.xlsx"


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Glue Crawler Never Run"

POLICY_CATEGORY = "Glue Crawler Never Run"

POLICY_SERVICE = "Glue"

POLICY_DESCRIPTION_TEMPLATE = (
    "Glue crawler '{crawler_name}' has never completed "
    "a successful crawl. This indicates an unused or "
    "potentially abandoned metadata discovery job. "
    "Review and delete the crawler if it is no longer required."
)


# ============================================================
# 4. CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients required by the policy.
    """

    glue = boto3.client(
        "glue",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return glue, sts


# ============================================================
# 5. GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    response = sts.get_caller_identity()

    return response["Account"]


# ============================================================
# 6. FETCH ALL GLUE CRAWLERS WITH PAGINATION
# ============================================================

def fetch_all_glue_crawlers(glue):
    """
    Fetch all Glue Crawlers using the AWS paginator.
    """

    crawlers = []

    try:

        paginator = glue.get_paginator(
            "get_crawlers"
        )

        for page in paginator.paginate():

            page_crawlers = page.get(
                "Crawlers",
                []
            )

            crawlers.extend(
                page_crawlers
            )

    except ClientError as e:

        logging.error(
            "Failed to fetch Glue Crawlers: %s",
            e
        )

    return crawlers


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_crawler_details(
    glue,
    crawler_name
):
    """
    Fetch detailed information for a Glue Crawler.

    get_crawlers() already returns substantial crawler
    information, but get_crawler() is used to obtain the
    most current LastCrawl information for the policy.
    """

    try:

        response = glue.get_crawler(
            Name=crawler_name
        )

        return response.get(
            "Crawler",
            {}
        )

    except ClientError as e:

        logging.error(
            "Failed to fetch details for crawler %s: %s",
            crawler_name,
            e
        )

        return None


def get_crawler_last_crawl_status(
    crawler
):
    """
    Determine whether the crawler has a successful crawl.

    Important AWS behavior:

        LastCrawl absent
            -> crawler has never completed a crawl

        LastCrawl.Status == SUCCEEDED
            -> crawler has completed a successful crawl

        LastCrawl.Status == FAILED
            -> latest crawl failed, but this does NOT prove
               that the crawler has never succeeded historically

        Other status
            -> do not classify as Never Run
    """

    last_crawl = crawler.get(
        "LastCrawl"
    )

    if not last_crawl:

        return {
            "has_last_crawl": False,
            "last_crawl_status": None,
            "has_successful_crawl": False,
            "last_crawl_time": None
        }

    last_crawl_status = last_crawl.get(
        "Status"
    )

    last_crawl_time = last_crawl.get(
        "StartTime"
    )

    has_successful_crawl = (
        last_crawl_status == "SUCCEEDED"
    )

    return {
        "has_last_crawl": True,
        "last_crawl_status": last_crawl_status,
        "has_successful_crawl":
            has_successful_crawl,
        "last_crawl_time":
            last_crawl_time
    }


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_glue_crawler(
    crawler,
    glue
):
    """
    Evaluate one Glue Crawler against the
    Glue Crawler Never Run policy.
    """

    crawler_name = crawler.get(
        "Name",
        ""
    )

    crawler_arn = crawler.get(
        "ARN",
        ""
    )

    state = crawler.get(
        "State",
        ""
    )

    role = crawler.get(
        "Role",
        ""
    )

    database_name = crawler.get(
        "DatabaseName",
        ""
    )

    description = crawler.get(
        "Description",
        ""
    )

    creation_time = crawler.get(
        "CreationTime"
    )

    last_updated = crawler.get(
        "LastUpdated"
    )

    # --------------------------------------------------------
    # GET LATEST CRAWLER DETAILS
    # --------------------------------------------------------

    detailed_crawler = get_crawler_details(
        glue=glue,
        crawler_name=crawler_name
    )

    if detailed_crawler is None:

        return {
            "is_finding": False,
            "crawler_name": crawler_name,
            "metric_error": True
        }

    # --------------------------------------------------------
    # CHECK LAST CRAWL
    # --------------------------------------------------------

    crawl_info = get_crawler_last_crawl_status(
        detailed_crawler
    )

    has_last_crawl = crawl_info[
        "has_last_crawl"
    ]

    last_crawl_status = crawl_info[
        "last_crawl_status"
    ]

    has_successful_crawl = crawl_info[
        "has_successful_crawl"
    ]

    last_crawl_time = crawl_info[
        "last_crawl_time"
    ]

    # --------------------------------------------------------
    # POLICY CONDITION
    # --------------------------------------------------------
    #
    # No LastCrawl means the crawler has never completed
    # a crawl.
    #
    # We deliberately DO NOT treat FAILED as "never
    # successfully run", because LastCrawl only represents
    # the latest crawl and cannot prove historical success.
    # --------------------------------------------------------

    is_never_run = (
        not has_last_crawl
    )

    if not is_never_run:

        logging.info(
            "Crawler %s has LastCrawl status: %s. "
            "No Never Run finding.",
            crawler_name,
            last_crawl_status
        )

        return {
            "is_finding": False,
            "metric_error": False,
            "crawler_name": crawler_name,
            "last_crawl_status":
                last_crawl_status,
            "has_successful_crawl":
                has_successful_crawl
        }

    # --------------------------------------------------------
    # FINDING DESCRIPTION
    # --------------------------------------------------------

    finding_description = (
        POLICY_DESCRIPTION_TEMPLATE.format(
            crawler_name=crawler_name
        )
    )

    # --------------------------------------------------------
    # RETURN FINDING
    # --------------------------------------------------------

    return {
        "is_finding": True,
        "metric_error": False,

        "crawler_name": crawler_name,
        "crawler_arn": crawler_arn,

        "state": state,

        "role": role,

        "database_name":
            database_name,

        "crawler_description":
            description,

        "creation_time":
            creation_time,

        "last_updated":
            last_updated,

        "has_last_crawl":
            has_last_crawl,

        "last_crawl_status":
            last_crawl_status,

        "last_crawl_time":
            last_crawl_time,

        "has_successful_crawl":
            has_successful_crawl,

        "description":
            finding_description
    }


# ============================================================
# 9. COST / SAVINGS
# ============================================================

def get_cur_athena_cost(
    athena,
    database,
    output_location,
    table_name,
    crawler_arn,
    start_date,
    end_date
):
    """
    Retrieve resource-level cost using CUR + Athena.

    IMPORTANT:
    Glue crawler cost attribution is not assumed.

    If the CUR contains the crawler ARN/resource ID,
    this function can retrieve the actual cost.

    If the CUR does not expose a resource-level identifier
    for the crawler, return None instead of inventing a cost.
    """

    query = f"""
    SELECT
        SUM(line_item_unblended_cost) AS total_cost
    FROM {table_name}
    WHERE
        line_item_usage_start_date >= DATE '{start_date}'
        AND line_item_usage_start_date < DATE '{end_date}'
        AND line_item_resource_id = '{crawler_arn}'
    """

    try:

        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={
                "Database": database
            },
            ResultConfiguration={
                "OutputLocation":
                    output_location
            }
        )

        query_execution_id = response[
            "QueryExecutionId"
        ]

        # ----------------------------------------------------
        # WAIT FOR ATHENA
        # ----------------------------------------------------

        while True:

            query_status = (
                athena.get_query_execution(
                    QueryExecutionId=
                        query_execution_id
                )
            )

            state = (
                query_status[
                    "QueryExecution"
                ][
                    "Status"
                ][
                    "State"
                ]
            )

            if state in [
                "SUCCEEDED",
                "FAILED",
                "CANCELLED"
            ]:
                break

            time.sleep(2)

        if state != "SUCCEEDED":

            logging.warning(
                "Athena query failed for crawler %s",
                crawler_arn
            )

            return None

        # ----------------------------------------------------
        # READ RESULT
        # ----------------------------------------------------

        result = athena.get_query_results(
            QueryExecutionId=
                query_execution_id
        )

        rows = (
            result.get(
                "ResultSet",
                {}
            ).get(
                "Rows",
                []
            )
        )

        if len(rows) < 2:

            return None

        value = (
            rows[1]
            .get("Data", [{}])[0]
            .get("VarCharValue")
        )

        if value is None:

            return None

        return Decimal(value)

    except ClientError as e:

        logging.error(
            "CUR/Athena cost retrieval failed "
            "for crawler %s: %s",
            crawler_arn,
            e
        )

        return None


def calculate_daily_cost(
    monthly_cost
):
    """
    Convert monthly CUR cost to approximate daily cost.
    """

    if monthly_cost is None:

        return None

    return (
        monthly_cost /
        Decimal("30")
    )


# ============================================================
# 10. GENERATE EXCEL / CSV OUTPUT
# ============================================================

def export_to_excel(
    findings,
    account_id,
    region
):
    """
    Export findings using the exact fixed 30-column schema.
    """

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

    rows = []

    for finding in findings:
        monthly_cost = finding.get("cur_monthly_cost")
        daily_cost = calculate_daily_cost(monthly_cost)

        rows.append({
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": "Pending for Review",
            "areaPath": "AWS Cost Optimization",
            "tags": "BI",
            "commentCount": 0,
            "accountId": account_id,
            "region": region,
            "resourceNameOrId": finding.get("crawler_name"),
            "resourceId": finding.get("crawler_name"),
            "resourceArn": finding.get("crawler_arn"),
            "service": POLICY_SERVICE,
            "type": "Glue Crawler",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Glue crawler '{finding.get('crawler_name')}' has never completed a successful crawl.",
            "recommendation": "Review and delete the crawler if it is no longer required.",
            "description": finding.get("description", "") + f" Crawler state: {finding.get('state', '')}. Database: {finding.get('database_name', '')}. Role: {finding.get('role', '')}. Creation time: {finding.get('creation_time', '')}. Last crawl: None.",
            "currentDailyCost": round(float(daily_cost), 4) if daily_cost is not None else "To be updated",
            "currentMonthlyCost": round(float(monthly_cost), 2) if monthly_cost is not None else "To be updated",
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": "",
            "month": ""
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(OUTPUT_FILE, index=False)
    
    logging.info("Excel report generated: %s", OUTPUT_FILE)


# ============================================================
# MAIN
# ============================================================

def main():

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - "
            "%(levelname)s - "
            "%(message)s"
        )
    )

    scan_start = time.time()

    logging.info(
        "=================================================="
    )

    logging.info(
        "Starting policy: %s",
        POLICY_TITLE
    )

    # ========================================================
    # CREATE CLIENTS
    # ========================================================

    glue, sts = create_clients(
        AWS_REGION
    )

    # ========================================================
    # GET ACCOUNT ID
    # ========================================================

    account_id = get_account_id(
        sts
    )

    logging.info(
        "Account ID: %s",
        account_id
    )

    # ========================================================
    # FETCH ALL CRAWLERS
    # ========================================================

    crawlers = fetch_all_glue_crawlers(
        glue
    )

    logging.info(
        "Total Glue Crawlers scanned: %d",
        len(crawlers)
    )

    # ========================================================
    # EVALUATE CRAWLERS
    # ========================================================

    findings = []

    for crawler in crawlers:

        crawler_name = crawler.get(
            "Name",
            ""
        )

        logging.info(
            "Evaluating Glue Crawler: %s",
            crawler_name
        )

        result = evaluate_glue_crawler(
            crawler=crawler,
            glue=glue
        )

        # ----------------------------------------------------
        # API / DATA ERROR
        # ----------------------------------------------------

        if result.get(
            "metric_error",
            False
        ):

            logging.warning(
                "Unable to evaluate crawler %s. "
                "Skipping.",
                crawler_name
            )

            continue

        # ----------------------------------------------------
        # NO FINDING
        # ----------------------------------------------------

        if not result.get(
            "is_finding",
            False
        ):

            logging.info(
                "Crawler %s does not meet "
                "Never Run condition.",
                crawler_name
            )

            continue

        # ----------------------------------------------------
        # FINDING
        # ----------------------------------------------------

        logging.info(
            "FINDING: Glue Crawler %s "
            "has never completed a successful crawl.",
            crawler_name
        )

        findings.append(
            result
        )

    # ========================================================
    # GENERATE OUTPUT
    # ========================================================

    export_to_excel(
        findings=findings,
        account_id=account_id,
        region=AWS_REGION
    )

    # ========================================================
    # SCAN SUMMARY
    # ========================================================

    scan_duration = (
        time.time() -
        scan_start
    )

    logging.info(
        "=================================================="
    )

    logging.info(
        "Policy: %s",
        POLICY_TITLE
    )

    logging.info(
        "Account ID: %s",
        account_id
    )

    logging.info(
        "Region: %s",
        AWS_REGION
    )

    logging.info(
        "Total Crawlers Scanned: %d",
        len(crawlers)
    )

    logging.info(
        "Never Run Findings: %d",
        len(findings)
    )

    logging.info(
        "Scan Duration: %.2f seconds",
        scan_duration
    )

    logging.info(
        "Output File: %s",
        OUTPUT_FILE
    )

    logging.info(
        "=================================================="
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()