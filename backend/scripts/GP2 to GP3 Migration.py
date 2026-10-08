# ============================================================
# AWS FinOps Policy: GP2 to GP3 Migration
# ============================================================

# ============================================================
# 1) IMPORTS
# ============================================================

import boto3
import logging
import pandas as pd
from datetime import datetime, timezone
from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# 2) AWS CONFIGURATION 
# ============================================================

AWS_REGION = "us-east-1"
OUTPUT_FILE = "gp2_to_gp3_migration.xlsx"

BOTO_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    }
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# 3) FINOPS POLICY CONFIGURATION
# ============================================================

POLICY_TITLE = "GP2 to GP3 Migration"
POLICY_CATEGORY = "GP2 to GP3 Migration"
POLICY_SERVICE = "EBS"
POLICY_TAG = "Cloud Roar"

SOURCE_VOLUME_TYPE = "gp2"
TARGET_VOLUME_TYPE = "gp3"


# ============================================================
# 4) CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name):
    """
    Create AWS clients for the specified region.
    """

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    sts = boto3.client(
        "sts",
        region_name=region_name,
        config=BOTO_CONFIG
    )

    return ec2, sts


# ============================================================
# 5) GET ACCOUNT ID
# ============================================================

def get_account_id(sts):
    """
    Get AWS account ID.
    """

    return sts.get_caller_identity()["Account"]


# ============================================================
# 6) FETCH ALL RESOURCES WITH PAGINATION
# ============================================================

def fetch_all_volumes(
    ec2
):
    """
    Fetch all EBS volumes in the region.
    """
    all_volumes = []
    paginator = ec2.get_paginator("describe_volumes")

    try:
        for page in paginator.paginate():
            for volume in page.get("Volumes", []):
                all_volumes.append(volume)

    except ClientError as e:
        logger.error(
            "Failed to fetch volumes: %s",
            e
        )

    logger.info(
        "Total volumes found in region: %d",
        len(all_volumes)
    )

    return all_volumes


# ============================================================
# 7) FETCH ADDITIONAL AWS DATA / METRICS
# ============================================================

def get_instance_details(ec2, instance_id):
    """
    Fetch details for the EC2 instance associated with a volume.

    Returns None if the instance no longer exists.
    """

    try:
        response = ec2.describe_instances(
            InstanceIds=[instance_id]
        )

        reservations = response.get(
            "Reservations",
            []
        )

        for reservation in reservations:
            for instance in reservation.get(
                "Instances",
                []
            ):
                return instance

    except ClientError as e:

        error_code = e.response.get(
            "Error",
            {}
        ).get(
            "Code"
        )

        if error_code in [
            "InvalidInstanceID.NotFound",
            "InvalidInstanceID.Malformed"
        ]:
            logger.warning(
                "EC2 instance %s no longer exists.",
                instance_id
            )
            return None

        logger.error(
            "Unable to fetch instance %s: %s",
            instance_id,
            e
        )

    return None


def get_instance_name(instance):
    """
    Extract the EC2 Name tag.
    """

    for tag in instance.get("Tags", []):
        if tag.get("Key") == "Name":
            return tag.get("Value", "")

    return ""


def get_volume_attachment(volume):
    """
    Get the active EC2 attachment information.

    Returns None if the volume is currently unattached.
    """

    attachments = volume.get(
        "Attachments",
        []
    )

    if not attachments:
        return None

    for attachment in attachments:

        instance_id = attachment.get(
            "InstanceId"
        )

        if instance_id:
            return attachment

    return None


def build_volume_details(
    volume,
    instance
):
    """
    Build service-specific details used inside Description.
    """

    volume_id = volume.get(
        "VolumeId",
        ""
    )

    availability_zone = volume.get(
        "AvailabilityZone",
        ""
    )

    size_gib = volume.get(
        "Size",
        0
    )

    state = volume.get(
        "State",
        ""
    )

    create_time = volume.get(
        "CreateTime"
    )

    if create_time:
        create_time = create_time.isoformat()

    encrypted = volume.get(
        "Encrypted",
        False
    )

    instance_id = instance.get(
        "InstanceId",
        ""
    )

    instance_name = get_instance_name(
        instance
    )
    
    instance_type = instance.get(
        "InstanceType",
        ""
    )

    instance_state = (
        instance.get("State", {})
        .get("Name", "")
    )

    device_name = ""

    for attachment in volume.get(
        "Attachments",
        []
    ):
        if attachment.get(
            "InstanceId"
        ) == instance_id:

            device_name = attachment.get(
                "Device",
                ""
            )

            break

    return {
        "volumeId": volume_id,
        "availabilityZone": availability_zone,
        "volumeType": volume.get(
            "VolumeType",
            ""
        ),
        "provisionedGB": size_gib,
        "volumeState": state,
        "createTime": create_time,
        "encrypted": encrypted,
        "instanceId": instance_id,
        "instanceName": instance_name,
        "instanceType": instance_type,
        "instanceState": instance_state,
        "deviceName": device_name
    }


# ============================================================
# 8) EVALUATE FINOPS POLICY
# ============================================================

def evaluate_volume(
    volume,
    ec2,
    account_id,
    region_name
):
    """
    Evaluate a volume.
    If GP2: Recommend GP3 Migration.
    If already GP3 (or other): Recommend Keep.
    """

    volume_id = volume.get(
        "VolumeId",
        ""
    )

    volume_type = volume.get(
        "VolumeType",
        ""
    )

    # --------------------------------------------------------
    # Check whether volume is attached
    # --------------------------------------------------------

    attachment = get_volume_attachment(
        volume
    )

    if not attachment:
        logger.info("Skipping unattached volume: %s", volume_id)
        return None

    instance_id = attachment.get("InstanceId")

    if not instance_id:
        logger.info("Skipping volume %s because no instance ID is present.", volume_id)
        return None

    # --------------------------------------------------------
    # Verify EC2 instance still exists
    # --------------------------------------------------------

    instance = get_instance_details(
        ec2,
        instance_id
    )

    if not instance:
        logger.info("Skipping volume %s because instance %s no longer exists.", volume_id, instance_id)
        return None

    # --------------------------------------------------------
    # Dynamic FinOps Logic
    # --------------------------------------------------------

    if volume_type != SOURCE_VOLUME_TYPE:
        return None

    status = "Review Required"
    effort = "Low"
    recommendation = f"Migrate {SOURCE_VOLUME_TYPE} volume to {TARGET_VOLUME_TYPE} after validating performance requirements."
    message = f"EBS volume '{volume_id}' is using GP2 and should be migrated to GP3."

    # --------------------------------------------------------
    # Build service-specific details
    # --------------------------------------------------------

    details = build_volume_details(
        volume,
        instance
    )

    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"resourceId: {volume_id} | "
        f"category: {POLICY_CATEGORY} | "
        f"dailyCost: To be updated | "
        f"monthlyCost: To be updated | "
        f"availabilityZone: {details['availabilityZone']} | "
        f"instanceId: {details['instanceId']} | "
        f"instanceName: {details['instanceName']} | "
        f"instanceType: {details['instanceType']} | "
        f"instanceState: {details['instanceState']} | "
        f"deviceName: {details['deviceName']} | "
        f"volumeType: {details['volumeType']} | "
        f"provisionedGB: {details['provisionedGB']} | "
        f"volumeState: {details['volumeState']} | "
        f"encrypted: {details['encrypted']} | "
        f"createTime: {details['createTime']}"
    )

    volume_arn = f"arn:aws:ec2:{region_name}:{account_id}:volume/{volume_id}"

    return {
        "Resource Name or ID": volume_id,
        "Volume ARN": volume_arn,
        "Description": description,
        "Status": status,
        "Recommendation": recommendation,
        "Message": message,
        "EffortLevel": effort,
        "Account ID": account_id,
        "Region": region_name
    }


def evaluate_all_volumes(
    volumes,
    ec2,
    account_id,
    region_name
):
    """
    Evaluate all volumes.
    """

    findings = []

    for volume in volumes:

        try:

            finding = evaluate_volume(
                volume=volume,
                ec2=ec2,
                account_id=account_id,
                region_name=region_name
            )

            if finding:
                findings.append(finding)

        except Exception as e:

            logger.exception(
                "Error evaluating volume %s: %s",
                volume.get("VolumeId", ""),
                e
            )

    return findings


# ============================================================
# 9) COST / SAVINGS
# ============================================================

def get_current_cost(
    resource_id,
    account_id,
    region_name
):
    """
    Get current daily/monthly cost.

    IMPORTANT:
    Resource-level cost should be populated from the centralized
    CUR + Athena implementation.

    This function intentionally does not fabricate pricing.

    Replace the return values with the organization's existing
    CUR + Athena cost lookup implementation.
    """

    current_daily_cost = ""
    current_monthly_cost = ""

    return (
        current_daily_cost,
        current_monthly_cost
    )


def calculate_potential_savings(
    current_monthly_cost
):
    """
    Potential GP2 -> GP3 savings should be calculated using
    actual CUR cost and the applicable GP2/GP3 pricing model.

    Do not estimate savings from volume size alone here.

    Return blank until the centralized pricing/CUR calculation
    is integrated.
    """

    return ""


# ============================================================
# 10) GENERATE EXCEL / OUTPUT
# ============================================================

def export_to_excel(
    findings,
    output_file
):
    """
    Write findings using the standard FinOps schema.
    """
    columns = [
        "id",
        "title",
        "category",
        "owner",
        "assignedTo",
        "status",
        "accountId",
        "region",
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
    
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = []

    for finding in findings:
        resource_id = finding["Resource Name or ID"]
        account_id = finding.get("Account ID", "")
        region = finding.get("Region", "")

        daily_cost, monthly_cost = get_current_cost(resource_id, account_id, region)
        achieved_savings = calculate_potential_savings(monthly_cost)

        rows.append({
            "id": "",
            "title": POLICY_TITLE,
            "category": POLICY_CATEGORY,
            "owner": "",
            "assignedTo": "",
            "status": finding.get("Status", "Review Required"),
            "accountId": account_id,
            "region": region,
            "resourceId": resource_id,
            "resourceArn": finding.get("Volume ARN", ""),
            "service": POLICY_SERVICE,
            "type": "EBS Volume",
            "policy": POLICY_TITLE,
            "effortLevel": finding.get("EffortLevel", ""),
            "message": finding.get("Message", ""),
            "recommendation": finding.get("Recommendation", ""),
            "description": finding["Description"],
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": monthly_cost,
            "estimatedMonthlySavings": "",
            "approvalComments": "",
            "reasonForRejection": "",
            "achievedSavingsMonthly": achieved_savings,
            "month": current_month
        })

    df = pd.DataFrame(rows, columns=columns)
    df.to_excel(output_file, index=False)
    
    logger.info("Output written to: %s", output_file)


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "Starting FinOps policy: %s",
        POLICY_TITLE
    )

    # --------------------------------------------------------
    # Get Account ID and Regions
    # --------------------------------------------------------

    base_ec2, sts = create_clients(AWS_REGION)
    account_id = get_account_id(sts)
    logger.info("AWS Account ID: %s", account_id)

    try:
        regions_response = base_ec2.describe_regions()
        regions = [r["RegionName"] for r in regions_response.get("Regions", [])]
    except Exception as e:
        logger.error("Failed to fetch AWS regions: %s", e)
        return

    logger.info("Discovered %d regions to scan.", len(regions))

    all_volumes = []
    all_findings = []

    # --------------------------------------------------------
    # Evaluate policy across all regions
    # --------------------------------------------------------

    for region in regions:
        logger.info("\n========================================")
        logger.info("Scanning region: %s", region)
        logger.info("========================================")

        try:
            regional_ec2, _ = create_clients(region)

            volumes = fetch_all_volumes(regional_ec2)
            all_volumes.extend(volumes)

            findings = evaluate_all_volumes(
                volumes=volumes,
                ec2=regional_ec2,
                account_id=account_id,
                region_name=region
            )

            all_findings.extend(findings)
            logger.info("Evaluated %d volumes in %s", len(volumes), region)

        except Exception as e:
            logger.error("Failed to evaluate region %s: %s", region, e)

    # --------------------------------------------------------
    # Generate output
    # --------------------------------------------------------

    export_to_excel(
        findings=all_findings,
        output_file=OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    logger.info("\n==================================================")
    logger.info("SCAN COMPLETED")
    logger.info("Total Regions Scanned  : %d", len(regions))
    logger.info("Total volumes evaluated: %d", len(all_volumes))
    logger.info("Total findings exported: %d", len(all_findings))
    logger.info("==================================================")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()