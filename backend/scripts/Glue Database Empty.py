# ============================================================
# AWS FINOPS POLICY
# Glue Database Empty
#
# Policy:
# Identify AWS Glue Data Catalog databases that contain
# zero tables.
#
# Recommended action:
# Review the database and delete it if it is no longer used.
#
# Cost:
# Glue databases themselves do not have a direct database-level
# charge. Therefore Current Daily Cost and Current Monthly Cost
# remain 0 unless attributable CUR data exists.
# ============================================================


# ============================================================
# 1. IMPORTS
# ============================================================

import boto3
import logging
import time
import pandas as pd

from datetime import datetime, timezone
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

OUTPUT_FILE = "glue_database_empty.xlsx"


# ============================================================
# 3. FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "Glue Database Empty"

POLICY_CATEGORY = "Glue Database Empty"

POLICY_SERVICE = "Glue"

POLICY_DESCRIPTION_TEMPLATE = (
    "Glue database '{database_name}' "
    "({database_arn}) has no tables attached. "
    "Review and delete if unused to reduce "
    "console clutter and management overhead."
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
# 6. FETCH ALL GLUE DATABASES WITH PAGINATION
# ============================================================

def fetch_all_glue_databases(glue):
    """
    Fetch all Glue Data Catalog databases using
    the AWS paginator.
    """

    databases = []

    try:

        paginator = glue.get_paginator(
            "get_databases"
        )

        for page in paginator.paginate():

            page_databases = page.get(
                "DatabaseList",
                []
            )

            databases.extend(
                page_databases
            )

    except ClientError as e:

        logging.error(
            "Failed to fetch Glue databases: %s",
            e
        )

    return databases


# ============================================================
# 7. FETCH ADDITIONAL AWS DATA
# ============================================================

def get_database_tables(
    glue,
    database_name
):
    """
    Fetch tables belonging to a Glue database.

    Pagination is important because a database can contain
    more tables than one API response can return.
    """

    tables = []

    try:

        paginator = glue.get_paginator(
            "get_tables"
        )

        for page in paginator.paginate(
            DatabaseName=database_name
        ):

            page_tables = page.get(
                "TableList",
                []
            )

            tables.extend(
                page_tables
            )

    except ClientError as e:

        logging.error(
            "Failed to fetch tables for "
            "database %s: %s",
            database_name,
            e
        )

        return None

    return tables


# ============================================================
# 8. EVALUATE FINOPS POLICY
# ============================================================

def evaluate_glue_database(
    glue,
    database
):
    """
    Evaluate one Glue database against the
    Glue Database Empty policy.
    """

    database_name = database.get(
        "Name",
        ""
    )

    database_arn = database.get(
        "CatalogId",
        ""
    )

    description = database.get(
        "Description",
        ""
    )

    location_uri = database.get(
        "LocationUri",
        ""
    )

    create_time = database.get(
        "CreateTime"
    )

    update_time = database.get(
        "UpdateTime"
    )

    # --------------------------------------------------------
    # BUILD DATABASE ARN
    # --------------------------------------------------------

    catalog_id = database.get(
        "CatalogId"
    )

    if catalog_id:

        database_arn = (
            f"arn:aws:glue:{AWS_REGION}:"
            f"{catalog_id}:database/"
            f"{database_name}"
        )

    else:

        database_arn = ""

    # --------------------------------------------------------
    # FETCH TABLES
    # --------------------------------------------------------

    tables = get_database_tables(
        glue=glue,
        database_name=database_name
    )

    # --------------------------------------------------------
    # API ERROR
    # --------------------------------------------------------

    if tables is None:

        return {
            "is_finding": False,
            "metric_error": True,
            "database_name":
                database_name
        }

    table_count = len(
        tables
    )

    # --------------------------------------------------------
    # POLICY CONDITION
    # --------------------------------------------------------

    is_empty = (
        table_count == 0
    )

    if not is_empty:

        logging.info(
            "Database %s contains %d table(s). "
            "No finding.",
            database_name,
            table_count
        )

        return {
            "is_finding": False,
            "metric_error": False,

            "database_name":
                database_name,

            "database_arn":
                database_arn,

            "table_count":
                table_count
        }

    # --------------------------------------------------------
    # FINDING DESCRIPTION
    # --------------------------------------------------------

    finding_description = (
        POLICY_DESCRIPTION_TEMPLATE.format(
            database_name=database_name,
            database_arn=database_arn
        )
    )

    # --------------------------------------------------------
    # RETURN FINDING
    # --------------------------------------------------------

    return {
        "is_finding": True,
        "metric_error": False,

        "database_name":
            database_name,

        "database_arn":
            database_arn,

        "table_count":
            table_count,

        "description":
            finding_description,

        "database_description":
            description,

        "location_uri":
            location_uri,

        "create_time":
            create_time,

        "update_time":
            update_time
    }


# ============================================================
# 9. COST / SAVINGS
# ============================================================

def get_cur_athena_cost(
    athena,
    database,
    output_location,
    table_name,
    database_arn,
    start_date,
    end_date
):
    """
    Retrieve resource-level cost using CUR + Athena.

    Glue Data Catalog database itself does not normally
    represent a directly attributable billed resource.

    This function is retained to remain compatible with
    the standard FinOps architecture.

    If CUR does not contain a matching resource-level cost,
    return None rather than inventing a cost.
    """

    query = f"""
    SELECT
        SUM(line_item_unblended_cost) AS total_cost
    FROM {table_name}
    WHERE
        line_item_usage_start_date >= DATE '{start_date}'
        AND line_item_usage_start_date < DATE '{end_date}'
        AND line_item_resource_id = '{database_arn}'
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
                "Athena query failed for "
                "database %s",
                database_arn
            )

            return None

        # ----------------------------------------------------
        # READ ATHENA RESULT
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
            .get(
                "Data",
                [{}]
            )[0]
            .get(
                "VarCharValue"
            )
        )

        if value is None:

            return None

        return float(value)

    except ClientError as e:

        logging.error(
            "CUR/Athena cost retrieval failed "
            "for database %s: %s",
            database_arn,
            e
        )

        return None


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
        current_daily_cost = 0
        current_monthly_cost = 0

        description = finding.get("description", "")
        description += f" Table count: {finding.get('table_count', 0)}. Location URI: {finding.get('location_uri', '')}. Creation time: {finding.get('create_time', '')}. Last update time: {finding.get('update_time', '')}."

        rows.append({
            "workItemType": "Task",
            "state": "To Do",
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": "Review Required",
            "areaPath": "AWS Cost Optimization",
            "tags": "BI",
            "commentCount": 0,
            "accountId": account_id,
            "region": region,
            "resourceNameOrId": finding.get("database_name"),
            "resourceId": finding.get("database_name"),
            "resourceArn": finding.get("database_arn"),
            "service": POLICY_SERVICE,
            "type": "Glue Database",
            "policy": POLICY_TITLE,
            "effortLevel": "",
            "message": f"Glue database '{finding.get('database_name')}' has no tables attached.",
            "recommendation": "Review and delete if unused to reduce console clutter and management overhead.",
            "description": description,
            "currentDailyCost": current_daily_cost,
            "currentMonthlyCost": current_monthly_cost,
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
    # CREATE AWS CLIENTS
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
    # FETCH ALL DATABASES
    # ========================================================

    databases = fetch_all_glue_databases(
        glue
    )

    logging.info(
        "Total Glue Databases scanned: %d",
        len(databases)
    )

    # ========================================================
    # EVALUATE DATABASES
    # ========================================================

    findings = []

    for database in databases:

        database_name = database.get(
            "Name",
            ""
        )

        logging.info(
            "Evaluating Glue Database: %s",
            database_name
        )

        result = evaluate_glue_database(
            glue=glue,
            database=database
        )

        # ----------------------------------------------------
        # API ERROR
        # ----------------------------------------------------

        if result.get(
            "metric_error",
            False
        ):

            logging.warning(
                "Unable to evaluate database %s. "
                "Skipping.",
                database_name
            )

            continue

        # ----------------------------------------------------
        # NO FINDING
        # ----------------------------------------------------

        if not result.get(
            "is_finding",
            False
        ):

            continue

        # ----------------------------------------------------
        # FINDING
        # ----------------------------------------------------

        logging.info(
            "FINDING: Glue Database %s "
            "contains zero tables.",
            database_name
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
        "Total Databases Scanned: %d",
        len(databases)
    )

    logging.info(
        "Empty Database Findings: %d",
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