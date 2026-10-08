# FinOps Dashboard: Blueprint for Creating New Scripts

This guide provides the exact standard conventions, function signatures, and required file updates necessary to add a brand new AWS FinOps optimization policy to the dashboard ecosystem.

## 1. The Main Script (`backend/scripts/YourNewScript.py`)
Since the backend runs this file via the terminal (`subprocess.run`), the function names don't *technically* matter to the server, but to follow the repository's clean standard, your script should be structured exactly like this:

```python
import boto3
import pandas as pd
from typing import List, Dict, Any

# 1. Import your custom pricing script
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from pricing_rules.your_new_script_pricing import calculate_savings

def fetch_resources(client) -> List[Dict[str, Any]]:
    # Use boto3 paginators to fetch resources
    pass

def build_finding(resource: Dict, account_id: str, region: str) -> Dict[str, Any]:
    # Build the dictionary mapping (resourceId, service, etc.)
    pass

def main():
    # 1. Initialize Boto3 Client (let it auto-fetch injected env variables)
    # 2. Call fetch_resources()
    # 3. Pass results to calculate_savings() from your pricing script
    # 4. Save the final list as an Excel file (.xlsx) with the 24 required columns
    pass

if __name__ == "__main__":
    main()
```

## 2. The Pricing Script (`backend/pricing_rules/your_new_script_pricing.py`)
This script isolates your math. It must expose one specific function that takes in the raw resources, calculates the money, and returns them enriched.

```python
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.cur_processor import get_historical_cost
from utils.aws_pricing import get_your_new_service_rates  # You will create this

def calculate_savings(discovered_resources: List[Dict], account_id: str) -> List[Dict]:
    enriched = []
    
    # 1. Get the new market rate from the catalog
    new_rates = get_your_new_service_rates("us-east-1")
    
    for res in discovered_resources:
        resource_id = res['resourceId']
        
        # 2. Find what they actually paid last month
        current_cost = get_historical_cost(resource_id=resource_id, account_id=account_id)
        
        # 3. Do the math
        projected_cost = calculate_new_cost(res, new_rates)
        savings = current_cost - projected_cost
        
        # 4. Attach costs to the dictionary
        res['currentMonthlyCost'] = f"${current_cost:.2f}"
        res['estimatedMonthlySavings'] = f"${savings:.2f}"
        enriched.append(res)
        
    return enriched
```

## 3. The Other Files You MUST Update

Whenever you add a new script, you must update two other files to make the whole ecosystem work:

1. **`backend/utils/aws_pricing.py` (The Catalog):**
   You must add a new function here (e.g., `def get_lambda_rates(region):`) that returns the hardcoded baseline market rate for whatever new AWS service you are optimizing. Your pricing script will import this function.
2. **`frontend/src/utils/scriptManifest.json` (The UI Dropdowns):**
   You must register your new script here so the React frontend knows it exists. You must add the exact filename as a key, and assign it the correct `category` and `service` so it shows up in the UI filters correctly!
