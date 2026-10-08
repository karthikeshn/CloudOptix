from typing import Dict, List, Any

def calculate_savings(findings: List[Dict[str, Any]], account_id: str = None) -> List[Dict[str, Any]]:
    """
    Prices Custom EC2 Rightsizing recommendations.
    Since we aren't using Compute Optimizer, we need to mock/estimate standard instance rates.
    """
    enriched_findings = []
    
    # Fallback mock pricing logic per instance size modifier
    size_multiplier = {
        "24xlarge": 24, "16xlarge": 16, "12xlarge": 12, "8xlarge": 8, "4xlarge": 4, 
        "2xlarge": 2, "xlarge": 1, "large": 0.5, "medium": 0.25, "small": 0.125, "micro": 0.0625, "nano": 0.03125
    }
    
    for finding in findings:
        resource_id = finding.get("resource_id")
        current_type = finding.get("currentInstanceType", "t3.medium")
        target_type = finding.get("targetInstanceType", "t3.small")
        
        # Calculate standard rate based on size multiplier assumption (e.g. baseline of $150/mo for xlarge)
        current_size = current_type.split('.')[-1] if '.' in current_type else "xlarge"
        target_size = target_type.split('.')[-1] if '.' in target_type else "large"
        
        base_rate = 150.0 
        
        current_monthly_cost = round(base_rate * size_multiplier.get(current_size, 1), 2)
        target_monthly_cost = round(base_rate * size_multiplier.get(target_size, 0.5), 2)
        
        monthly_savings = round(current_monthly_cost - target_monthly_cost, 2)
        if monthly_savings < 0:
            monthly_savings = 0.0
            
        daily_cost = round(current_monthly_cost / 30, 2)
        
        enriched_findings.append({
            "resource_id": resource_id,
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": current_monthly_cost,
            "estimatedMonthlySavings": monthly_savings
        })
        
    return enriched_findings
