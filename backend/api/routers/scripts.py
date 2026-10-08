import os
import subprocess
import glob
import csv
import ast
import re
import json
import pandas as pd
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import schemas
from core import database, security

router = APIRouter(
    prefix="/api/scripts",
    tags=["scripts"]
)

class ValidateScriptsRequest(BaseModel):
    scripts: list[str]

class RunScriptRequest(BaseModel):
    account_id: int | None = None

def get_scripts_dir():
    # Since this file is in backend/api/routers, the scripts dir is ../../scripts
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts")

@router.post("/validate")
def validate_scripts(request: ValidateScriptsRequest, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    scripts_dir = get_scripts_dir()
    unsafe_prefixes = ("delete_", "remove_", "update_", "modify_", "put_", "post_", "create_", "stop_", "terminate_", "drop_")
    results = {}
    
    for script_name in request.scripts:
        script_path = os.path.join(scripts_dir, script_name)
        if not os.path.exists(script_path):
            continue
            
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                code = f.read()
            tree = ast.parse(code)
            
            is_unsafe = False
            reason = None
            
            local_funcs = {node.name.lower() for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
            allowed_funcs = {"create_client", "create_session"}
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute):
                        func_name = func.attr.lower()
                        display_name = f"{func.attr}()"
                    elif isinstance(func, ast.Name):
                        func_name = func.id.lower()
                        display_name = f"{func.id}()"
                    else:
                        continue
                        
                    if (func_name.startswith(unsafe_prefixes) 
                        and func_name not in local_funcs 
                        and func_name not in allowed_funcs):
                        is_unsafe = True
                        reason = f"Found unsafe operation: {display_name}"
                        break
                        
                if is_unsafe:
                    break
                    
            status = "rejected" if is_unsafe else "approved"
            results[script_name] = {"status": status, "reason": reason}
            
            validation_record = db.query(models.ScriptValidation).filter(models.ScriptValidation.script_name == script_name).first()
            if not validation_record:
                validation_record = models.ScriptValidation(script_name=script_name)
                db.add(validation_record)
                
            validation_record.status = status
            validation_record.reason = reason
            validation_record.last_validated = datetime.now().isoformat()
            
        except Exception as e:
            results[script_name] = {"status": "rejected", "reason": f"Parse error: {str(e)}"}
            
    db.commit()
    return results

@router.get("")
def get_scripts(current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    scripts_dir = get_scripts_dir()
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
    scripts = [f for f in os.listdir(scripts_dir) if f.endswith(".py")]
    
    validations = db.query(models.ScriptValidation).all()
    validation_map = {v.script_name: {"status": v.status, "reason": v.reason} for v in validations}
    
    return {"scripts": scripts, "validations": validation_map}

@router.post("/{script_name}/run")
def run_script(script_name: str, payload: RunScriptRequest = None, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    scripts_dir = get_scripts_dir()
    script_path = os.path.join(scripts_dir, script_name)
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Script not found")
        
    env_vars = os.environ.copy()
    if payload and payload.account_id:
        config = db.query(models.CloudConfig).filter(models.CloudConfig.id == payload.account_id, models.CloudConfig.owner_id == current_user.id).first()
        if config:
            if config.aws_access_key_id:
                env_vars["AWS_ACCESS_KEY_ID"] = config.aws_access_key_id
            if config.aws_secret_access_key:
                env_vars["AWS_SECRET_ACCESS_KEY"] = config.aws_secret_access_key
            if config.aws_session_token:
                env_vars["AWS_SESSION_TOKEN"] = config.aws_session_token
            if config.region:
                env_vars["AWS_REGION"] = config.region
                env_vars["AWS_DEFAULT_REGION"] = config.region
    
    try:
        start_time = time.time()
        result = subprocess.run(["python", script_path], capture_output=True, text=True, env=env_vars, cwd=scripts_dir)
        
        if result.returncode != 0:
            error_msg = result.stderr
            if "ExpiredToken" in error_msg:
                error_msg = "AWS Token Expired. Please update your credentials."
            elif "InvalidClientTokenId" in error_msg:
                error_msg = "AWS Security Token is invalid."
            elif "AccessDenied" in error_msg:
                error_msg = "Access Denied. Insufficient permissions."
            else:
                lines = [line.strip() for line in error_msg.split('\n') if line.strip()]
                if lines:
                    error_msg = lines[-1] 
            
            raise HTTPException(status_code=500, detail=error_msg)
            
        output_files = glob.glob(os.path.join(scripts_dir, "*.csv")) + glob.glob(os.path.join(scripts_dir, "*.xlsx"))
        
        # Only consider files created/modified after the script started
        recent_files = [f for f in output_files if os.path.getmtime(f) >= start_time - 2.0]
        
        if not recent_files:
            return {"data": []}
            
        latest_file = max(recent_files, key=os.path.getmtime)
        filename = os.path.basename(latest_file)
        
        if payload and payload.account_id:
            config_obj = db.query(models.CloudConfig).filter(models.CloudConfig.id == payload.account_id).first()
            aws_acc = config_obj.aws_account_id if config_obj and config_obj.aws_account_id else str(payload.account_id)
            new_filename = f"output_{aws_acc}_{script_name}" + os.path.splitext(filename)[1]
            new_file_path = os.path.join(scripts_dir, new_filename)
            if latest_file != new_file_path:
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)
                os.rename(latest_file, new_file_path)
                latest_file = new_file_path
                filename = new_filename
        
        data = []
        if latest_file.endswith(".csv"):
            with open(latest_file, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
        elif latest_file.endswith(".xlsx"):
            df = pd.read_excel(latest_file)
            df = df.fillna("")
            data = df.to_dict(orient="records")
            
        # --- Phase 2: Create Tickets from Results ---
        now_iso = datetime.utcnow().isoformat() + "Z"
        
        # Heuristic for recommended action based on script name
        rec_action = "Investigate resource"
        s_name_lower = script_name.lower()
        if "unattached" in s_name_lower or "idle" in s_name_lower or "old" in s_name_lower:
            if "ebs" in s_name_lower or "snapshot" in s_name_lower:
                rec_action = "Delete Resource"
            elif "ec2" in s_name_lower or "rds" in s_name_lower:
                rec_action = "Stop or Terminate Resource"
        
        for row in data:
            # Try to identify resource ID (heuristics based on common column names)
            res_id = "unknown"
            
            # Explicitly check best candidate columns first
            for candidate in ["resourceId", "resourceNameOrId", "resource_id", "Resource ID", "VolumeId", "InstanceId"]:
                if candidate in row and str(row[candidate]).strip():
                    res_id = str(row[candidate]).strip()
                    break
                    
            if res_id == "unknown":
                for key, val in row.items():
                    k_lower = str(key).lower()
                    val_str = str(val).strip()
                    if val_str and ("id" in k_lower or "arn" in k_lower or "name" in k_lower):
                        # skip if the column is 'accountid' or 'id' if it's purely numerical and we expect a string resource
                        if k_lower == "accountid":
                            continue
                        res_id = val_str
                        break
            
            # Try to identify potential savings
            savings = None
            
            # Prioritize the explicit savings column
            if "estimatedMonthlySavings" in row and str(row["estimatedMonthlySavings"]).strip():
                savings = str(row["estimatedMonthlySavings"]).strip()
            elif "achievedSavingsMonthly" in row and str(row["achievedSavingsMonthly"]).strip():
                savings = str(row["achievedSavingsMonthly"]).strip()
            else:
                # Fallback to the old heuristic if explicit columns aren't found
                for key, val in row.items():
                    k_lower = str(key).lower()
                    val_str = str(val).strip()
                    if val_str and ("saving" in k_lower or "price" in k_lower):
                        savings = val_str
                        break
                    
            # Check if ticket already exists for this resource and script
            existing_ticket = db.query(models.Ticket).filter(
                models.Ticket.script_name == script_name,
                models.Ticket.resource_id == res_id,
                models.Ticket.account_id == (payload.account_id if payload else None)
            ).first()
            
            details_json = json.dumps(row)
            
            if existing_ticket:
                existing_ticket.potential_savings = savings
                existing_ticket.details = details_json
                existing_ticket.recommended_action = rec_action
            else:
                new_ticket = models.Ticket(
                    script_name=script_name,
                    account_id=payload.account_id if payload else None,
                    resource_id=res_id,
                    potential_savings=savings,
                    status="Pending",
                    details=details_json,
                    created_at=now_iso,
                    recommended_action=rec_action
                )
                db.add(new_ticket)
                db.flush() # flush so the next iteration can find it if needed
        
        db.commit()
        # --------------------------------------------
                
        return {"data": data, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/latest-run")
def get_latest_run_results(account_id: int | None = None, current_user: models.User = Depends(security.get_current_user)):
    scripts_dir = get_scripts_dir()
    if not os.path.exists(scripts_dir):
        return {"data": None, "scriptName": None, "timestamp": None}
    
    output_files = glob.glob(os.path.join(scripts_dir, "*.csv")) + glob.glob(os.path.join(scripts_dir, "*.xlsx"))
    
    if account_id is not None:
        account_obj = db.query(models.CloudConfig).filter(models.CloudConfig.id == account_id).first()
        acc_str = account_obj.aws_account_id if account_obj and account_obj.aws_account_id else str(account_id)
        output_files = [f for f in output_files if os.path.basename(f).startswith(f"output_{acc_str}_")]
        
    if not output_files:
        return {"data": None, "scriptName": None, "timestamp": None}
        
    latest_file = max(output_files, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    timestamp = os.path.getmtime(latest_file)
    
    script_name = os.path.basename(latest_file)
    if account_id is not None:
        account_obj = db.query(models.CloudConfig).filter(models.CloudConfig.id == account_id).first()
        acc_str = account_obj.aws_account_id if account_obj and account_obj.aws_account_id else str(account_id)
        script_name = script_name.replace(f"output_{acc_str}_", "")
    else:
        script_name = script_name.replace("output_", "")
    script_name = script_name.replace(".csv", "").replace(".xlsx", "")
    
    data = []
    try:
        if latest_file.endswith(".csv"):
            with open(latest_file, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
        elif latest_file.endswith(".xlsx"):
            df = pd.read_excel(latest_file)
            df = df.fillna("")
            data = df.to_dict(orient="records")
            
        return {"data": data, "scriptName": script_name, "timestamp": timestamp, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
def download_script_result(filename: str, current_user: models.User = Depends(security.get_current_user)):
    scripts_dir = get_scripts_dir()
    file_path = os.path.join(scripts_dir, filename)
    
    if not os.path.abspath(file_path).startswith(os.path.abspath(scripts_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path=file_path, filename=filename)

@router.get("/results/view")
def view_script_result(script_name: str, account_id: int | None = None, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    scripts_dir = get_scripts_dir()
    if not os.path.exists(scripts_dir):
        return {"status": "empty", "message": "Scripts directory not found"}
        
    clean_name = script_name.replace(".py", "").strip()
    
    account_obj = None
    if account_id is not None:
        account_obj = db.query(models.CloudConfig).filter(models.CloudConfig.id == account_id, models.CloudConfig.owner_id == current_user.id).first()
    account_label = account_obj.account_name if account_obj and account_obj.account_name else f"Account {account_id}" if account_id else "this account"

    all_files = glob.glob(os.path.join(scripts_dir, "*.csv")) + glob.glob(os.path.join(scripts_dir, "*.xlsx"))
    matched_file = None
    
    def is_other_account_file(filename):
        if account_id is None:
            return False
        acc_str = account_obj.aws_account_id if account_obj and account_obj.aws_account_id else str(account_id)
        m = re.match(r"^output_([a-zA-Z0-9]+)_", filename)
        if m:
            file_acc_id = m.group(1)
            return file_acc_id != acc_str
        return False

    if account_id is not None:
        acc_str = account_obj.aws_account_id if account_obj and account_obj.aws_account_id else str(account_id)
        acc_files = [f for f in all_files if os.path.basename(f).startswith(f"output_{acc_str}_")]
        clean_slug = clean_name.lower().replace(" ", "_").replace("-", "_")
        keywords = [w for w in clean_name.lower().replace("(", "").replace(")", "").split() if len(w) > 2]
        
        acc_matches = []
        for f in acc_files:
            fname = os.path.basename(f).lower().replace(" ", "_").replace("-", "_")
            if clean_slug in fname or (keywords and all(kw in fname for kw in keywords[:2])):
                acc_matches.append(f)
                
        if acc_matches:
            matched_file = max(acc_matches, key=os.path.getmtime)
            
    if not matched_file:
        clean_slug = clean_name.lower().replace(" ", "_").replace("-", "_")
        keywords = [w for w in clean_name.lower().replace("(", "").replace(")", "").split() if len(w) > 2]
        matches = []
        for f in all_files:
            fname = os.path.basename(f).lower().replace(" ", "_").replace("-", "_")
            if is_other_account_file(os.path.basename(f)):
                continue
            if clean_slug in fname or (keywords and all(kw in fname for kw in keywords[:2])):
                matches.append(f)
                
        if matches:
            matched_file = max(matches, key=os.path.getmtime)
            
    if not matched_file:
        return {"status": "empty", "message": f"No output result sheet found for ticket '{clean_name}' under account '{account_label}'."}
        
    filename = os.path.basename(matched_file)
    timestamp = os.path.getmtime(matched_file)
    data = []
    
    try:
        if matched_file.endswith(".csv"):
            with open(matched_file, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
        elif matched_file.endswith(".xlsx"):
            df = pd.read_excel(matched_file)
            df = df.fillna("")
            data = df.to_dict(orient="records")
            
        return {
            "status": "found",
            "data": data,
            "filename": filename,
            "timestamp": timestamp,
            "script_name": script_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse result sheet: {str(e)}")
