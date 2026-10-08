from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from core import database, security

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)

@router.get("/stats/{account_id}")
def get_dashboard_stats(account_id: int, db: Session = Depends(database.get_db), current_user: models.User = Depends(security.get_current_user)):
    
    # 1. Fetch tickets for this account (ignore Rejected if they exist)
    tickets = db.query(models.Ticket).filter(
        models.Ticket.account_id == account_id
    ).all()
    
    potential_total = 0.0
    achieved_total = 0.0
    
    potential_script_savings = {}
    achieved_script_savings = {}
    
    for t in tickets:
        if t.status == "Rejected":
            continue
            
        val = 0.0
        if t.potential_savings:
            clean_str = str(t.potential_savings).replace('$', '').replace(',', '').strip()
            try:
                val = float(clean_str)
            except ValueError:
                pass
                
        s_name = str(t.script_name).replace('.py', '')
        
        if t.status == "Completed":
            achieved_total += val
            if s_name not in achieved_script_savings:
                achieved_script_savings[s_name] = 0.0
            achieved_script_savings[s_name] += val
        else:
            potential_total += val
            if s_name not in potential_script_savings:
                potential_script_savings[s_name] = 0.0
            potential_script_savings[s_name] += val

    # Top Optimizations (sort and take top 5 from potential)
    sorted_scripts = sorted(potential_script_savings.items(), key=lambda x: x[1], reverse=True)
    top_opts = [{"name": k, "value": round(v, 2)} for k, v in sorted_scripts[:5] if v > 0]
    
    # We don't have "Spend" data right now since we only track waste, 
    # but we can return a placeholder or 0 for now
    spend_val = 0
    
    # We return the detailed data for the frontend to use
    return {
        "spend": f"${spend_val:,.0f}",
        "savings": f"${potential_total:,.2f}",
        "achievedSavings": f"${achieved_total:,.2f}",
        "topOptimizations": top_opts,
        "scriptSavings": potential_script_savings, 
        "achievedScriptSavings": achieved_script_savings 
    }
