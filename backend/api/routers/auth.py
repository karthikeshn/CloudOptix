from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
from core import database
import schemas
from core import security

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

@router.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = security.get_user_by_username(db, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled. Contact your administrator.",
        )
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    # Bake role into token payload for the frontend
    access_token = security.create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

router_users = APIRouter(
    prefix="/api/users",
    tags=["users"]
)

@router_users.get("/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(security.get_current_user)):
    return current_user

@router_users.put("/me/password")
def change_password(
    data: schemas.PasswordChangeRequest, 
    current_user: models.User = Depends(security.get_current_user), 
    db: Session = Depends(database.get_db)
):
    if not security.verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    current_user.hashed_password = security.get_password_hash(data.new_password)
    db.commit()
    return {"status": "success"}

@router_users.post("/me/verify-password")
def verify_password(
    data: schemas.PasswordVerifyRequest, 
    current_user: models.User = Depends(security.get_current_user), 
):
    if security.verify_password(data.password, current_user.hashed_password):
        return {"valid": True}
    return {"valid": False}

@router_users.get("/engineers", response_model=list[schemas.User])
def list_engineers(current_user: models.User = Depends(security.require_role(["admin", "manager"])), db: Session = Depends(database.get_db)):
    return db.query(models.User).filter(models.User.role == "engineer", models.User.is_active == True).all()

@router_users.get("", response_model=list[schemas.User])
def list_users(current_user: models.User = Depends(security.require_role(["admin"])), db: Session = Depends(database.get_db)):
    return db.query(models.User).all()

@router_users.post("", response_model=schemas.User)
def create_user_admin(user: schemas.UserCreate, current_user: models.User = Depends(security.require_role(["admin"])), db: Session = Depends(database.get_db)):
    db_user = security.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = security.get_password_hash(user.password)
    new_user = models.User(
        username=user.username, 
        email=user.email,
        role=user.role,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router_users.put("/{user_id}", response_model=schemas.User)
def update_user_admin(user_id: int, update_data: schemas.UserUpdate, current_user: models.User = Depends(security.require_role(["admin"])), db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if update_data.email is not None:
        db_user.email = update_data.email
    if update_data.role is not None:
        db_user.role = update_data.role
    if update_data.is_active is not None:
        db_user.is_active = update_data.is_active
        
    db.commit()
    db.refresh(db_user)
    return db_user
