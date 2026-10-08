from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core import security, database
import models, schemas
from typing import List
from datetime import datetime

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])

@router.get("", response_model=List[schemas.TicketResponse])
def get_tickets(
    status: str = None, 
    account_id: int = None,
    assigned_to: int = None,
    script_name: str = None,
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    query = db.query(models.Ticket)
    
    if status:
        query = query.filter(models.Ticket.status == status)
    
    if account_id:
        query = query.filter(models.Ticket.account_id == account_id)
        
    if script_name:
        query = query.filter(models.Ticket.script_name == script_name)
        
    if assigned_to:
        query = query.filter(models.Ticket.assigned_to == assigned_to)
        
    tickets = query.order_by(models.Ticket.created_at.desc()).all()
    return tickets

@router.put("/{ticket_id}/status", response_model=schemas.TicketResponse)
def update_ticket_status(
    ticket_id: int, 
    payload: schemas.TicketUpdate,
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # RBAC Checks
    if current_user.role not in ["manager", "admin"]:
        # If they are just an engineer, they can only complete THEIR OWN tickets
        if payload.status != "Completed":
            raise HTTPException(status_code=403, detail="Engineers can only mark tickets as Completed")
        if ticket.assigned_to != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update tickets assigned to you")
            
    if payload.status not in ["Pending", "Approved", "Rejected", "Completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    ticket.status = payload.status
    
    if payload.status == "Completed":
        ticket.completed_by_name = current_user.username
        ticket.completed_at = datetime.utcnow().isoformat() + "Z"
        
    import json
    if payload.approvalComments or payload.reasonForRejection:
        try:
            details_obj = json.loads(ticket.details)
            if payload.approvalComments:
                details_obj["approvalComments"] = payload.approvalComments
            if payload.reasonForRejection:
                details_obj["reasonForRejection"] = payload.reasonForRejection
            ticket.details = json.dumps(details_obj)
        except Exception:
            pass

    db.commit()
    db.refresh(ticket)
    
    return ticket

@router.put("/{ticket_id}/assign", response_model=schemas.TicketResponse)
def assign_ticket(
    ticket_id: int, 
    payload: schemas.TicketAssign,
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    if current_user.role not in ["manager", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to assign tickets")
        
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    engineer = db.query(models.User).filter(models.User.id == payload.engineer_id).first()
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer not found")
        
    ticket.assigned_to = payload.engineer_id
    ticket.assigned_to_name = engineer.username
    ticket.assigned_by_name = current_user.username
    ticket.assigned_at = datetime.utcnow().isoformat() + "Z"
    ticket.status = "In Progress"

    import json
    try:
        details_obj = json.loads(ticket.details)
        details_obj["assignedTo"] = engineer.username
        ticket.details = json.dumps(details_obj)
    except Exception:
        pass

    db.commit()
    db.refresh(ticket)
    
    return ticket

@router.put("/{ticket_id}/details", response_model=schemas.TicketResponse)
def update_ticket_details(
    ticket_id: int, 
    payload: schemas.TicketDetailsUpdate,
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.details = payload.details

    db.commit()
    db.refresh(ticket)
    
    return ticket

@router.put("/sync-edit", response_model=schemas.TicketResponse)
def sync_ticket_edit(
    payload: schemas.TicketSyncEdit,
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    import json
    
    # Try to find the ticket by script_name and resource_id
    ticket = db.query(models.Ticket).filter(
        models.Ticket.script_name == payload.script_name,
        models.Ticket.resource_id == payload.resource_id
    ).first()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found for this resource")
        
    try:
        details_obj = json.loads(ticket.details)
        details_obj[payload.field] = payload.value
        ticket.details = json.dumps(details_obj)
        
        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

