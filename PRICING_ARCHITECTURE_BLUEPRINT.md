# AWS FinOps Pricing Architecture Blueprint

This document outlines the exact architectural flow for dynamically calculating cost savings using the official AWS Pricing API, complete with caching and region normalization.

---

## Phase 1: The Core Execution Flow

When an audit script runs, it follows this strict 4-step pipeline:

1. **Resource Discovery (The Rule Engine):**
   * The script queries the AWS environment (e.g., using `boto3.client('ec2')`) to find resources.
   * It filters these resources against specific FinOps rules (e.g., "Is this EBS volume unattached?").

2. **Gather Current Historical Cost (CUR):**
   * For every violating resource, the script checks the **Cost and Usage Report (CUR)** to see exactly what the business paid for it last month.
   * *Tool used:* `utils.cur_processor.py` (reads local billing zip files).

3. **Gather Optimized/Future Market Price (AWS Pricing API):**
   * If the script recommends migrating the resource (e.g., migrating `gp2` to `gp3`), it needs to know the market price of the *new* resource.
   * The script calls the central **Pricing Catalog** to get the current market rate for the new resource.

4. **Calculate Final Savings:**
   * The script performs the final math: `(Current Historical Cost) - (New Market Price) = Estimated Monthly Savings`.
   * The final data is exported to `.xlsx` for the frontend UI.

---

## Phase 2: The Pricing Catalog Implementation

To dynamically fetch market prices without slowing down the application, the Pricing Catalog must be split into three distinct modules:

### Module A: Region Normalization (`backend/utils/region_mapping.py`)
The AWS Pricing API **does not accept** standard region codes (like `us-east-1`). It requires human-readable names. You must create a dedicated file to handle this translation.

```python
# backend/utils/region_mapping.py

REGION_MAP = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "ap-south-1": "Asia Pacific (Mumbai)"
    # Add other regions as necessary
}

def get_pricing_region_name(region_code: str) -> str:
    """Converts 'us-east-1' into 'US East (N. Virginia)' for the Pricing API"""
    return REGION_MAP.get(region_code, "US East (N. Virginia)") # Default fallback
```

### Module B: The Master Pricing API & Cache (`backend/utils/aws_pricing.py`)
Because the AWS Pricing API takes 1-2 seconds per request, you **must** cache results in memory. If you scan 5,000 EC2 instances, you only want to hit the API once per instance type.

```python
# backend/utils/aws_pricing.py
import boto3
import json
from .region_mapping import get_pricing_region_name

# IN-MEMORY CACHE
_PRICE_CACHE = {}

def get_dynamic_ec2_price(instance_type: str, region_code: str) -> float:
    # 1. Normalize the region
    human_region = get_pricing_region_name(region_code)
    
    # 2. Check the Cache first!
    cache_key = f"ec2_{instance_type}_{human_region}"
    if cache_key in _PRICE_CACHE:
        return _PRICE_CACHE[cache_key]
        
    # 3. If not in cache, call the Master AWS Pricing API
    pricing_client = boto3.client('pricing', region_name='us-east-1')
    
    response = pricing_client.get_products(
        ServiceCode='AmazonEC2',
        Filters=[
            {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': human_region},
            {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
            {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
            {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
            {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
        ]
    )
    
    # 4. Extract the dollar amount from the JSON response
    # (Note: AWS pricing JSON is highly nested, requires careful parsing)
    price_list = response.get('PriceList', [])
    if not price_list:
        return 0.0 # Or some fallback
        
    price_data = json.loads(price_list[0])
    terms = price_data.get('terms', {}).get('OnDemand', {})
    
    # Extract actual USD rate (Simplified extraction logic)
    rate = 0.0
    for term_key, term_val in terms.items():
        for dimension_key, dimension_val in term_val.get('priceDimensions', {}).items():
            rate_usd = dimension_val.get('pricePerUnit', {}).get('USD')
            if rate_usd:
                rate = float(rate_usd)
                
    # 5. Save to cache for next time
    _PRICE_CACHE[cache_key] = rate
    
    return rate
```

### Module C: The Final Pricing Script (`backend/pricing_rules/your_script_pricing.py`)
This is where the **CUR Report** and the **Pricing API** finally come together to calculate the exact dollar savings.

```python
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# 1. Import CUR Report Processor (For Past Cost)
from utils.cur_processor import get_historical_cost

# 2. Import Master Pricing API (For Future Cost)
from utils.aws_pricing import get_dynamic_ec2_price

def calculate_savings(discovered_resources, account_id):
    enriched = []
    
    for res in discovered_resources:
        resource_id = res['resourceId']
        region = res['region']
        new_instance_type = res['recommendedInstanceType'] # e.g., 'm6g.large'
        
        # STEP A: How much did this resource actually cost us last month? (CUR REPORT)
        current_cost = get_historical_cost(resource_id=resource_id, account_id=account_id)
        
        # STEP B: What is the official AWS market rate for the optimized resource? (PRICING API)
        new_hourly_rate = get_dynamic_ec2_price(instance_type=new_instance_type, region_code=region)
        projected_monthly_cost = new_hourly_rate * 730 # 730 hours in a month
        
        # STEP C: Calculate Savings
        savings = current_cost - projected_monthly_cost
        
        # Final Output
        res['currentMonthlyCost'] = f"${current_cost:.2f}"
        res['estimatedMonthlySavings'] = f"${savings:.2f}"
        enriched.append(res)
        
    return enriched
```

---

## Summary of the Ecosystem

1. **`region_mapping.py`**: Translates `us-east-1` -> `US East (N. Virginia)`.
2. **`aws_pricing.py`**: Looks in its `_PRICE_CACHE`. If it's missing, it calls `boto3.client('pricing')` with the translated region and saves the result to the cache.
3. **`cur_processor.py`**: Reads your local ZIP billing files to find out what you actually paid in the past.
4. **`your_script_pricing.py`**: Combines the CUR past cost and the API future cost to calculate total savings!
