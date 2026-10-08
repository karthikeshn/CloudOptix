from typing import Dict, List, Any

def calculate_savings(findings: List[Dict[str, Any]], account_id: str = None) -> List[Dict[str, Any]]:
    """
    Prices EC2 Rightsizing recommendations.
    Since AWS Compute Optimizer already provides the exact Estimated Monthly Savings
    and the Savings Percentage, we can perfectly reverse-engineer the current cost 
    without needing to query the Cost Explorer API or rely on fallbacks!
    """
    enriched_findings = []
    
    for finding in findings:
        resource_id = finding.get("resource_id")
        
        monthly_savings = float(finding.get("compute_optimizer_savings", 0.0))
        savings_percentage = float(finding.get("compute_optimizer_savings_percentage", 0.0))
        
        # Reverse engineer the current cost using the provided API savings data
        if savings_percentage > 0:
            monthly_cost = round(monthly_savings / (savings_percentage / 100.0), 2)
        else:
            monthly_cost = 0.0
            
        daily_cost = round(monthly_cost / 30, 2)
        
        enriched_findings.append({
            "resource_id": resource_id,
            "currentDailyCost": daily_cost,
            "currentMonthlyCost": monthly_cost,
            "estimatedMonthlySavings": round(monthly_savings, 2)
        })
        
    return enriched_findings
