from fastapi import APIRouter, Depends, HTTPException
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
def get_cloud_config(current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
    return db.query(models.CloudConfig).filter(models.CloudConfig.owner_id == current_user.id).all()

@router.post("", response_model=schemas.CloudConfigResponse)
def save_cloud_config(config_data: schemas.CloudConfigCreate, current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
    temp_aws_account_id = None
    temp_status = "unverified"
    last_verified_str = None
    
    if config_data.provider == "AWS" and not config_data.use_iam_role:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=config_data.aws_access_key_id,
                aws_secret_access_key=config_data.aws_secret_access_key,
                aws_session_token=config_data.aws_session_token,
                region_name=config_data.region or 'us-east-1'
            )
            identity = sts.get_caller_identity()
            temp_aws_account_id = identity.get('Account')
            temp_status = "verified"
            last_verified_str = datetime.now().isoformat()
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code in ['ExpiredToken', 'InvalidClientTokenId']:
                temp_status = "expired"
            else:
                temp_status = "invalid"
        except Exception as e:
            temp_status = "invalid"

    # Check if this AWS account ID is already in the database for this user
    existing_config = None
    if temp_aws_account_id:
        existing_config = db.query(models.CloudConfig).filter(
            models.CloudConfig.owner_id == current_user.id,
            models.CloudConfig.aws_account_id == temp_aws_account_id
        ).first()
        
    if existing_config:
        # UPSERT: Re-activate and update existing config
        existing_config.provider = config_data.provider
        existing_config.account_name = config_data.account_name
        existing_config.region = config_data.region
        existing_config.use_iam_role = config_data.use_iam_role
        existing_config.aws_access_key_id = config_data.aws_access_key_id
        existing_config.aws_secret_access_key = config_data.aws_secret_access_key
        existing_config.aws_session_token = config_data.aws_session_token
        existing_config.assume_role_arn = config_data.assume_role_arn
        existing_config.external_id = config_data.external_id
        existing_config.status = temp_status
        if last_verified_str:
            existing_config.last_verified = last_verified_str
        existing_config.is_deleted = False
        db.commit()
        db.refresh(existing_config)
        return existing_config
    else:
        # Create completely new config
        config = models.CloudConfig(
            **config_data.dict(),
            owner_id=current_user.id,
            status=temp_status,
            aws_account_id=temp_aws_account_id
        )
        if last_verified_str:
            config.last_verified = last_verified_str
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

@router.post("/{config_id}/verify")
def verify_cloud_config(config_id: int, current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
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
            identity = sts.get_caller_identity()
            config.aws_account_id = identity.get('Account')
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
def delete_cloud_config(config_id: int, current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
    config = db.query(models.CloudConfig).filter(models.CloudConfig.id == config_id, models.CloudConfig.owner_id == current_user.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    # Soft delete instead of hard delete to preserve history
    config.is_deleted = True
    config.aws_access_key_id = None
    config.aws_secret_access_key = None
    config.aws_session_token = None
    config.status = "unverified"
    
    db.commit()
    return {"status": "success"}

@router.put("/{config_id}", response_model=schemas.CloudConfigResponse)
def update_cloud_config(config_id: int, config_data: schemas.CloudConfigCreate, current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
    config = db.query(models.CloudConfig).filter(models.CloudConfig.id == config_id, models.CloudConfig.owner_id == current_user.id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    config.provider = config_data.provider
    config.account_name = config_data.account_name
    config.region = config_data.region
    config.use_iam_role = config_data.use_iam_role
    config.aws_access_key_id = config_data.aws_access_key_id
    config.aws_secret_access_key = config_data.aws_secret_access_key
    config.aws_session_token = config_data.aws_session_token
    config.assume_role_arn = config_data.assume_role_arn
    config.external_id = config_data.external_id
    
    config.status = "unverified"
    
    if config.provider == "AWS" and not config.use_iam_role:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=config.aws_access_key_id,
                aws_secret_access_key=config.aws_secret_access_key,
                aws_session_token=config.aws_session_token,
                region_name=config.region or 'us-east-1'
            )
            identity = sts.get_caller_identity()
            config.aws_account_id = identity.get('Account')
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

    # Always undelete when updating an account
    config.is_deleted = False

    db.commit()
    db.refresh(config)
    return config
