from __future__ import annotations

from typing import Any, Dict, List, Optional

import boto3
import pandas as pd

from botocore.config import Config
from botocore.exceptions import ClientError


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
# CREATE AWS CLIENTS
# ============================================================

def create_clients(region_name: str):

    ec2 = boto3.client(
        "ec2",
        region_name=region_name,
        config=AWS_CONFIG,
    )

    sts = boto3.client(
        "sts",
        config=AWS_CONFIG,
    )

    return ec2, sts


# ============================================================
# ACCOUNT ID
# ============================================================

def get_account_id(sts) -> str:

    return sts.get_caller_identity()["Account"]


# ============================================================
# FETCH ALL NETWORK INTERFACES
# ============================================================

def fetch_all_network_interfaces(
    ec2,
) -> List[Dict[str, Any]]:
    """
    Automatically fetch ALL network interfaces in the region.

    Pagination is handled using boto3 paginator.

    AWS recommends paginated requests for
    describe_network_interfaces.
    """

    network_interfaces = []

    paginator = ec2.get_paginator(
        "describe_network_interfaces"
    )

    for page in paginator.paginate():

        page_interfaces = page.get(
            "NetworkInterfaces",
            []
        )

        network_interfaces.extend(
            page_interfaces
        )

    return network_interfaces


# ============================================================
# EXTRACT TAGS
# ============================================================

def extract_tags(
    tags: List[Dict[str, Any]]
) -> Dict[str, str]:

    return {
        tag.get("Key"): tag.get("Value", "")
        for tag in tags
        if tag.get("Key")
    }


# ============================================================
# EXTRACT INSTANCE ID
# ============================================================

def get_instance_id(
    network_interface: Dict[str, Any]
) -> Optional[str]:

    attachment = network_interface.get(
        "Attachment",
        {}
    )

    return attachment.get(
        "InstanceId"
    )


# ============================================================
# EXTRACT PUBLIC IPV4 ADDRESSES
# ============================================================

def extract_public_ipv4_addresses(
    network_interface: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract public IPv4 addresses associated with
    the network interface.

    This handles Elastic IP and public IPv4
    associations exposed through the ENI's
    PrivateIpAddresses structure.
    """

    public_addresses = []

    private_ip_addresses = (
        network_interface.get(
            "PrivateIpAddresses",
            []
        )
    )

    for private_ip in private_ip_addresses:

        association = private_ip.get(
            "Association"
        )

        if not association:
            continue

        public_ip = association.get(
            "PublicIp"
        )

        if not public_ip:
            continue

        public_addresses.append(
            {
                "publicIp": public_ip,

                "privateIp": private_ip.get(
                    "PrivateIpAddress"
                ),

                "primary": private_ip.get(
                    "Primary",
                    False
                ),

                "allocationId": association.get(
                    "AllocationId"
                ),

                "associationId": association.get(
                    "AssociationId"
                ),

                "ipOwnerId": association.get(
                    "IpOwnerId"
                ),

                "publicDnsName": association.get(
                    "PublicDnsName"
                ),
            }
        )

    return public_addresses


# ============================================================
# EXTRACT IPV6 ADDRESSES
# ============================================================

def extract_ipv6_addresses(
    network_interface: Dict[str, Any]
) -> List[str]:

    ipv6_addresses = []

    for item in network_interface.get(
        "Ipv6Addresses",
        []
    ):

        ipv6 = item.get(
            "Ipv6Address"
        )

        if ipv6:
            ipv6_addresses.append(
                ipv6
            )

    return ipv6_addresses


# ============================================================
# FETCH SUBNET DETAILS
# ============================================================

def fetch_subnet_details(
    ec2,
    subnet_id: Optional[str],
) -> Optional[Dict[str, Any]]:

    if not subnet_id:
        return None

    try:

        response = ec2.describe_subnets(
            SubnetIds=[
                subnet_id
            ]
        )

        subnets = response.get(
            "Subnets",
            []
        )

        if subnets:
            return subnets[0]

    except ClientError:
        return None

    return None


# ============================================================
# FETCH VPC DETAILS
# ============================================================

def fetch_vpc_details(
    ec2,
    vpc_id: Optional[str],
) -> Optional[Dict[str, Any]]:

    if not vpc_id:
        return None

    try:

        response = ec2.describe_vpcs(
            VpcIds=[
                vpc_id
            ]
        )

        vpcs = response.get(
            "Vpcs",
            []
        )

        if vpcs:
            return vpcs[0]

    except ClientError:
        return None

    return None


# ============================================================
# CHECK SUBNET IPV6 SUPPORT
# ============================================================

def get_subnet_ipv6_cidrs(
    subnet: Optional[Dict[str, Any]]
) -> List[str]:

    if not subnet:
        return []

    cidrs = []

    for association in subnet.get(
        "Ipv6CidrBlockAssociationSet",
        []
    ):

        ipv6_cidr = association.get(
            "Ipv6CidrBlock"
        )

        if ipv6_cidr:
            cidrs.append(
                ipv6_cidr
            )

    return cidrs


# ============================================================
# CHECK VPC IPV6 SUPPORT
# ============================================================

def get_vpc_ipv6_cidrs(
    vpc: Optional[Dict[str, Any]]
) -> List[str]:

    if not vpc:
        return []

    cidrs = []

    for association in vpc.get(
        "Ipv6CidrBlockAssociationSet",
        []
    ):

        ipv6_cidr = association.get(
            "Ipv6CidrBlock"
        )

        if ipv6_cidr:
            cidrs.append(
                ipv6_cidr
            )

    return cidrs


# ============================================================
# CHECK WHETHER ENI IS AWS MANAGED
# ============================================================

def is_managed_network_interface(
    network_interface: Dict[str, Any]
) -> bool:

    requester_managed = network_interface.get(
        "RequesterManaged",
        False
    )

    interface_type = network_interface.get(
        "InterfaceType"
    )

    # These are generally service-managed
    # network interfaces and should not be
    # treated as normal EC2 IPv4 migration
    # candidates.

    managed_interface_types = {
        "lambda",
        "load_balancer",
        "network_load_balancer",
        "nat_gateway",
        "vpc_endpoint",
        "gateway_load_balancer",
        "gateway_load_balancer_endpoint",
        "api_gateway_managed",
        "aws_codestar_connections_managed",
        "ec2_instance_connect_endpoint",
        "quicksight",
    }

    if requester_managed:
        return True

    if interface_type in managed_interface_types:
        return True

    return False


# ============================================================
# CHECK WHETHER IPV4 IS A CANDIDATE
# ============================================================

def is_ipv4_candidate(
    network_interface: Dict[str, Any],
    public_ipv4: Dict[str, Any],
) -> bool:
    """
    Candidate criteria:

    1. A public IPv4 exists.
    2. The ENI has no IPv6 address.
    3. The interface is not AWS-managed.

    We do NOT automatically claim that IPv6 migration
    is technically possible. The finding is a review
    candidate.
    """

    if not public_ipv4.get(
        "publicIp"
    ):
        return False

    ipv6_addresses = extract_ipv6_addresses(
        network_interface
    )

    if ipv6_addresses:
        return False

    if is_managed_network_interface(
        network_interface
    ):
        return False

    return True


# ============================================================
# BUILD FINOPS FINDING
# ============================================================

def build_ipv4_to_ipv6_finding(
    network_interface: Dict[str, Any],
    public_ipv4: Dict[str, Any],
    subnet: Optional[Dict[str, Any]],
    vpc: Optional[Dict[str, Any]],
    account_id: str,
    region_name: str,
) -> Dict[str, Any]:

    public_ip = public_ipv4.get(
        "publicIp"
    )

    private_ip = public_ipv4.get(
        "privateIp"
    )

    allocation_id = public_ipv4.get(
        "allocationId"
    )

    association_id = public_ipv4.get(
        "associationId"
    )

    network_interface_id = (
        network_interface.get(
            "NetworkInterfaceId"
        )
    )

    vpc_id = network_interface.get(
        "VpcId"
    )

    subnet_id = network_interface.get(
        "SubnetId"
    )

    availability_zone = network_interface.get(
        "AvailabilityZone"
    )

    interface_type = network_interface.get(
        "InterfaceType"
    )

    instance_id = get_instance_id(
        network_interface
    )

    ipv6_addresses = extract_ipv6_addresses(
        network_interface
    )

    subnet_ipv6_cidrs = get_subnet_ipv6_cidrs(
        subnet
    )

    vpc_ipv6_cidrs = get_vpc_ipv6_cidrs(
        vpc
    )

    subnet_ipv6_supported = (
        len(subnet_ipv6_cidrs) > 0
    )

    vpc_ipv6_supported = (
        len(vpc_ipv6_cidrs) > 0
    )

    tags = extract_tags(
        network_interface.get(
            "TagSet",
            []
        )
    )

    # --------------------------------------------------------
    # Determine resource name
    # --------------------------------------------------------

    if instance_id:

        resource_name_or_id = (
            instance_id
        )

    else:

        resource_name_or_id = (
            network_interface_id
        )

    # --------------------------------------------------------
    # Policy
    # --------------------------------------------------------

    policy = (
        "convert-public-ipv4-to-ipv6"
    )

    effort_level = "Medium"

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    if subnet_ipv6_supported:

        message = (
            f"Public IPv4 address {public_ip} is "
            f"associated with network interface "
            f"{network_interface_id} and no IPv6 "
            f"address is currently configured. "
            f"The subnet already has IPv6 CIDR "
            f"configuration. Review the workload "
            f"for IPv6 migration."
        )

    else:

        message = (
            f"Public IPv4 address {public_ip} is "
            f"associated with network interface "
            f"{network_interface_id} and no IPv6 "
            f"address is currently configured. "
            f"The subnet does not currently have "
            f"an IPv6 CIDR configured. Review "
            f"IPv6 migration requirements before "
            f"making changes."
        )

    # --------------------------------------------------------
    # Recommendation
    # --------------------------------------------------------

    recommendation = (
        f"Review resource {resource_name_or_id} "
        f"and determine whether the workload can "
        f"operate using IPv6 or dual-stack "
        f"connectivity. Verify application, "
        f"security-group, route-table, DNS, and "
        f"downstream-service IPv6 compatibility "
        f"before removing the public IPv4 address."
    )

    # --------------------------------------------------------
    # Resource ARN
    # --------------------------------------------------------

    resource_arn = (
        f"arn:aws:ec2:"
        f"{region_name}:"
        f"{account_id}:"
        f"network-interface/"
        f"{network_interface_id}"
    )

    # --------------------------------------------------------
    # Description
    #
    # All service-specific information is placed
    # into description so every FinOps script
    # maintains the same Excel schema.
    # --------------------------------------------------------

    description = (
        f"accountId: {account_id} | "
        f"region: {region_name} | "
        f"publicIpv4: {public_ip} | "
        f"privateIpv4: {private_ip} | "
        f"networkInterfaceId: {network_interface_id} | "
        f"instanceId: {instance_id or 'N/A'} | "
        f"vpcId: {vpc_id} | "
        f"subnetId: {subnet_id} | "
        f"availabilityZone: {availability_zone} | "
        f"interfaceType: {interface_type} | "
        f"allocationId: {allocation_id or 'N/A'} | "
        f"associationId: {association_id or 'N/A'} | "
        f"ipv6Addresses: {ipv6_addresses or 'None'} | "
        f"vpcIpv6Supported: {vpc_ipv6_supported} | "
        f"vpcIpv6Cidrs: {vpc_ipv6_cidrs or 'None'} | "
        f"subnetIpv6Supported: {subnet_ipv6_supported} | "
        f"subnetIpv6Cidrs: {subnet_ipv6_cidrs or 'None'} | "
        f"policy: {policy} | "
        f"message: {message} | "
        f"recommendation: {recommendation}"
    )

    # ========================================================
    # STANDARD 30-COLUMN SCHEMA
    # ========================================================

    return {

        # ----------------------------------------------------
        # Workflow & Tracking
        # ----------------------------------------------------

        "workItemType": "Task",

        "state": "To Do",

        "id": public_ip,

        "title": (
            "Convert IPV4 to IPV6"
        ),

        "category": (
            "Convert IPV4 to IPV6"
        ),

        "owner": "",

        "assignedTo": "",

        "status": "Pending for Review",

        "areaPath": (
            "AWS Cost Optimization"
        ),

        "tags": ", ".join(
            f"{key}={value}"
            for key, value in tags.items()
        ),

        "commentCount": 0,

        # ----------------------------------------------------
        # AWS Identity
        # ----------------------------------------------------

        "accountId": account_id,

        "region": region_name,

        "resourceNameOrId": (
            resource_name_or_id
        ),

        "resourceId": (
            network_interface_id
        ),

        "resourceArn": resource_arn,

        "service": "VPC",

        # ----------------------------------------------------
        # FinOps Details
        # ----------------------------------------------------

        "type": "Public IPv4",

        "policy": policy,

        "effortLevel": effort_level,

        "message": message,

        "recommendation": recommendation,

        "description": description,

        # ----------------------------------------------------
        # Cost & Savings
        #
        # CUR + Athena intentionally NOT used.
        # ----------------------------------------------------

        "currentDailyCost": None,

        "currentMonthlyCost": None,

        "estimatedMonthlySavings": None,

        "approvalComments": "",

        "reasonForRejection": "",

        "achievedSavingsMonthly": None,

        "month": "",
    }


# ============================================================
# SCAN IPV4 ADDRESSES
# ============================================================

def scan_ipv4_to_ipv6(
    region_name: str,
) -> Dict[str, Any]:

    ec2, sts = create_clients(
        region_name
    )

    account_id = get_account_id(
        sts
    )

    # --------------------------------------------------------
    # Automatically fetch ALL network interfaces
    # --------------------------------------------------------

    network_interfaces = (
        fetch_all_network_interfaces(
            ec2
        )
    )

    findings = []

    total_interfaces_scanned = 0

    total_public_ipv4 = 0

    total_ipv4_candidates = 0

    # --------------------------------------------------------
    # Process every network interface
    # --------------------------------------------------------

    for network_interface in network_interfaces:

        total_interfaces_scanned += 1

        # ----------------------------------------------------
        # Extract public IPv4 addresses
        # ----------------------------------------------------

        public_ipv4_addresses = (
            extract_public_ipv4_addresses(
                network_interface
            )
        )

        if not public_ipv4_addresses:
            continue

        total_public_ipv4 += len(
            public_ipv4_addresses
        )

        # ----------------------------------------------------
        # Fetch subnet details
        # ----------------------------------------------------

        subnet_id = network_interface.get(
            "SubnetId"
        )

        subnet = fetch_subnet_details(
            ec2,
            subnet_id
        )

        # ----------------------------------------------------
        # Fetch VPC details
        # ----------------------------------------------------

        vpc_id = network_interface.get(
            "VpcId"
        )

        vpc = fetch_vpc_details(
            ec2,
            vpc_id
        )

        # ----------------------------------------------------
        # Check every public IPv4
        # ----------------------------------------------------

        for public_ipv4 in public_ipv4_addresses:

            if not is_ipv4_candidate(
                network_interface,
                public_ipv4
            ):
                continue

            total_ipv4_candidates += 1

            finding = (
                build_ipv4_to_ipv6_finding(
                    network_interface=network_interface,
                    public_ipv4=public_ipv4,
                    subnet=subnet,
                    vpc=vpc,
                    account_id=account_id,
                    region_name=region_name,
                )
            )

            findings.append(
                finding
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    return {

        "accountId": account_id,

        "region": region_name,

        "totalNetworkInterfacesScanned": (
            total_interfaces_scanned
        ),

        "totalPublicIpv4Addresses": (
            total_public_ipv4
        ),

        "totalIpv4ToIpv6Candidates": (
            total_ipv4_candidates
        ),

        "findings": findings,
    }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    import json

    # --------------------------------------------------------
    # Only REGION is supplied.
    #
    # IPv4 addresses and resources are discovered
    # automatically.
    # --------------------------------------------------------

    region = "us-east-1"

    result = scan_ipv4_to_ipv6(
        region
    )

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )

    findings = result.get(
        "findings",
        []
    )

    if not findings:

        print(
            "\nNo IPv4 to IPv6 candidates found."
        )

    # ========================================================
    # FLATTEN FINDINGS FOR EXCEL
    # ========================================================

    flat_findings = []

    for finding in findings:

        flat_finding = {}

        for key, value in finding.items():

            if isinstance(
                value,
                (list, dict)
            ):

                flat_finding[key] = json.dumps(
                    value,
                    default=str,
                )

            else:

                flat_finding[key] = value

        flat_findings.append(
            flat_finding
        )

    # ========================================================
    # STANDARD FINOPS EXCEL SCHEMA
    # ========================================================

    STANDARD_COLUMNS = [

        # Workflow & Tracking

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

        # AWS Identity

        "accountId",
        "region",
        "resourceNameOrId",
        "resourceId",
        "resourceArn",
        "service",

        # FinOps Details

        "type",
        "policy",
        "effortLevel",
        "message",
        "recommendation",
        "description",

        # Cost & Savings

        "currentDailyCost",
        "currentMonthlyCost",
        "estimatedMonthlySavings",
        "approvalComments",
        "reasonForRejection",
        "achievedSavingsMonthly",
        "month",
    ]

    # ========================================================
    # CREATE DATAFRAME
    # ========================================================

    df = pd.DataFrame(
        flat_findings,
        columns=STANDARD_COLUMNS,
    )

    # ========================================================
    # EXPORT EXCEL
    # ========================================================

    excel_file = (
        "ipv4_to_ipv6_report.xlsx"
    )

    df.to_excel(
        excel_file,
        index=False,
    )

    print(
        f"\nResult successfully exported to "
        f"{excel_file}"
    )