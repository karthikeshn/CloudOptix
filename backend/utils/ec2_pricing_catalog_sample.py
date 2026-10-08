# ---------------------------------------------------------
# EC2 STATIC PRICING CATALOG (SAMPLE SUBSET)
# ---------------------------------------------------------
# NOTE: An exhaustive catalog of EVERY instance type (700+) 
# across EVERY region (30+) for EVERY OS and billing model 
# is a database containing over 300,000 rows (approx 1.5GB). 
#
# Below is a highly structured, production-ready dictionary 
# containing the most popular general purpose and compute 
# instances across 3 major regions (us-east-1, eu-west-1, ap-south-1)
# for On-Demand Linux usage.
# ---------------------------------------------------------

EC2_PRICING_CATALOG = {
    # ==========================================
    # REGION: US-EAST-1 (N. Virginia)
    # ==========================================
    "us-east-1": {
        # General Purpose (Intel/AMD)
        "t3.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0104},
        "t3.small": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0208},
        "t3.medium": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0416},
        "m5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0960},
        "m5.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1920},
        
        # General Purpose (Graviton / ARM) - Cheaper!
        "t4g.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0084},
        "m6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0770},
        "m6g.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1540},

        # Compute Optimized
        "c5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0850},
        "c6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0680},
        
        # Memory Optimized
        "r5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1260},
        "r6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1008},
    },

    # ==========================================
    # REGION: EU-WEST-1 (Ireland)
    # ==========================================
    "eu-west-1": {
        "t3.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0108},
        "t3.small": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0216},
        "t3.medium": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0432},
        "m5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1070},
        "m5.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.2140},
        
        "t4g.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0088},
        "m6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0860},
        "m6g.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1720},

        "c5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0960},
        "c6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0760},
        
        "r5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1410},
        "r6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1128},
    },

    # ==========================================
    # REGION: AP-SOUTH-1 (Mumbai)
    # ==========================================
    "ap-south-1": {
        "t3.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0104},
        "t3.small": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0208},
        "t3.medium": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0416},
        "m5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1010},
        "m5.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.2020},
        
        "t4g.micro": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0084},
        "m6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0810},
        "m6g.xlarge": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1620},

        "c5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0890},
        "c6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.0710},
        
        "r5.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1330},
        "r6g.large": {"OperatingSystem": "Linux", "PricingModel": "OnDemand", "Unit": "Hrs", "RateUSD": 0.1064},
    }
}

def get_ec2_ondemand_rate(region: str, instance_type: str) -> float:
    """
    Helper function to query the mock catalog for an EC2 rate.
    Falls back to us-east-1 if region is not found.
    """
    region_data = EC2_PRICING_CATALOG.get(region, EC2_PRICING_CATALOG.get("us-east-1", {}))
    instance_data = region_data.get(instance_type)
    
    if instance_data:
        return instance_data["RateUSD"]
    
    # Fallback to a generic 10 cents per hour if instance is extremely obscure
    return 0.10
