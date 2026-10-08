"""
AWS Region Mapping for Pricing API

The AWS Pricing API requires human-readable region names (e.g., 'US East (N. Virginia)')
instead of standard boto3 region codes (e.g., 'us-east-1'). 
This module handles the translation between the two.
"""

AWS_REGION_MAPPING = {
    # US Regions
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    
    # Canada
    "ca-central-1": "Canada (Central)",
    "ca-west-1": "Canada West (Calgary)",
    
    # Europe
    "eu-central-1": "EU (Frankfurt)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-north-1": "EU (Stockholm)",
    "eu-south-1": "Europe (Milan)",
    "eu-south-2": "Europe (Spain)",
    
    # Asia Pacific
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-south-2": "Asia Pacific (Hyderabad)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-southeast-3": "Asia Pacific (Jakarta)",
    "ap-southeast-4": "Asia Pacific (Melbourne)",
    
    # Middle East & Africa
    "af-south-1": "Africa (Cape Town)",
    "me-south-1": "Middle East (Bahrain)",
    "me-central-1": "Middle East (UAE)",
    
    # South America
    "sa-east-1": "South America (Sao Paulo)"
}

def get_pricing_region(boto3_region: str) -> str:
    """
    Converts a standard boto3 region code (e.g., 'us-east-1') 
    to the human-readable region name required by the AWS Pricing API.
    
    If the region is not found in the mapping, it returns the original string as a fallback.
    """
    return AWS_REGION_MAPPING.get(boto3_region, boto3_region)
