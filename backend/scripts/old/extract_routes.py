import os

backend_dir = r"d:\FinOpsDashboard\backend"
routers_dir = os.path.join(backend_dir, "api", "routers")

# 1. cloud_config.py
cloud_config_code = """from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

import models
import schemas
from core import database, security

router = APIRouter(
    prefix="/api/cloud-config",
    tags=["cloud-config"]
)

@router.get("", response_model=list[schemas.CloudConfigResponse])
def get_cloud_config(current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    return db.query(models.CloudConfig).filter(models.CloudConfig.owner_id == current_user.id).all()

@router.post("", response_model=schemas.CloudConfigResponse)
def save_cloud_config(config_data: schemas.CloudConfigCreate, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    config = models.CloudConfig(
        **config_data.dict(),
        owner_id=current_user.id,
        status="unverified"
    )
    
    if config_data.provider == "AWS" and not config_data.use_iam_role:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=config_data.aws_access_key_id,
                aws_secret_access_key=config_data.aws_secret_access_key,
                aws_session_token=config_data.aws_session_token,
                region_name=config_data.region or 'us-east-1'
            )
            sts.get_caller_identity()
            config.status = "verified"
            config.last_verified = datetime.now().isoformat()
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code in ['ExpiredToken', 'InvalidClientTokenId']:
                config.status = "expired"
            else:
                config.status = "invalid"
        except Exception as e:
            config.status = "invalid"

    db.add(config)
    db.commit()
    db.refresh(config)
    return config

@router.post("/{config_id}/verify")
def verify_cloud_config(config_id: int, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    config = db.query(models.CloudConfig).filter(models.CloudConfig.id == config_id, models.CloudConfig.owner_id == current_user.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    if config.provider == "AWS" and not config.use_iam_role:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                aws_session_token=config.aws_session_token,
                region_name=config.region or 'us-east-1'
            )
            sts.get_caller_identity()
            config.status = "verified"
            config.last_verified = datetime.now().isoformat()
            db.commit()
            return {"status": "verified", "last_verified": config.last_verified}
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            if error_code in ['ExpiredToken', 'InvalidClientTokenId']:
                config.status = "expired"
            else:
                config.status = "invalid"
            db.commit()
            return {"status": config.status, "detail": f"AWS Validation Error: {error_code} - {error_msg}"}
        except Exception as e:
            config.status = "invalid"
            db.commit()
            return {"status": "invalid", "detail": f"Invalid credentials: {str(e)}"}
    
    return {"status": "skipped", "detail": "IAM role or non-AWS provider"}

@router.delete("/{config_id}")
def delete_cloud_config(config_id: int, current_user: models.User = Depends(security.get_current_user), db: Session = Depends(database.get_db)):
    config = db.query(models.CloudConfig).filter(models.CloudConfig.id == config_id, models.CloudConfig.owner_id == current_user.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    db.delete(config)
    db.commit()
    return {"status": "success"}
"""

# 2. scripts.py
scripts_code = """import os
import subprocess
import glob
import csv
import ast
import re
import pandas as pd
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
    
    try:
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
                lines = [line.strip() for line in error_msg.split('\\n') if line.strip()]
                if lines:
                    error_msg = lines[-1] 
            
            raise HTTPException(status_code=500, detail=error_msg)
            
        output_files = glob.glob(os.path.join(scripts_dir, "*.csv")) + glob.glob(os.path.join(scripts_dir, "*.xlsx"))
        if not output_files:
            return {"data": []}
            
        latest_file = max(output_files, key=os.path.getmtime)
        filename = os.path.basename(latest_file)
        
        if payload and payload.account_id:
            new_filename = f"output_{payload.account_id}_{script_name}" + os.path.splitext(filename)[1]
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
        output_files = [f for f in output_files if os.path.basename(f).startswith(f"output_{account_id}_")]
        
    if not output_files:
        return {"data": None, "scriptName": None, "timestamp": None}
        
    latest_file = max(output_files, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    timestamp = os.path.getmtime(latest_file)
    
    script_name = os.path.basename(latest_file)
    if account_id is not None:
        script_name = script_name.replace(f"output_{account_id}_", "")
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
        m = re.match(r"^output_(\d+)_", filename)
        if m:
            file_acc_id = int(m.group(1))
            return file_acc_id != account_id
        return False

    if account_id is not None:
        acc_files = [f for f in all_files if os.path.basename(f).startswith(f"output_{account_id}_")]
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
"""

dashboard_code = """from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import models
from core import database, security

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)

@router.get("/stats/{account_id}")
def get_dashboard_stats(account_id: int, current_user: models.User = Depends(security.get_current_user)):
    spend_val = (account_id * 1234) % 50000 + 1000
    savings_val = (account_id * 432) % 10000 + 500
    return {
        "spend": f"${spend_val:,.0f}",
        "savings": f"${savings_val:,.0f}"
    }
"""

main_code = """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core import database
import models

# Import routers
from api.routers import auth, cloud_config, scripts, dashboard

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="FinOps Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(auth.router_users)
app.include_router(cloud_config.router)
app.include_router(scripts.router)
app.include_router(dashboard.router)
"""

with open(os.path.join(routers_dir, "cloud_config.py"), "w") as f:
    f.write(cloud_config_code)
    
with open(os.path.join(routers_dir, "scripts.py"), "w") as f:
    f.write(scripts_code)
    
with open(os.path.join(routers_dir, "dashboard.py"), "w") as f:
    f.write(dashboard_code)
    
with open(os.path.join(backend_dir, "main.py"), "w") as f:
    f.write(main_code)

print("Extraction completed!")
