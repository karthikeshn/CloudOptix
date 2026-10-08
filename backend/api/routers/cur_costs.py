from fastapi import APIRouter, HTTPException, Query
from typing import List
from utils.cur_processor import get_main_services, get_ecosystems, get_resource_costs

router = APIRouter(prefix="/api/costs", tags=["Cost Explorer"])

@router.get("/services")
def list_services():
    try:
        return get_main_services()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ecosystems")
def list_ecosystems(services: List[str] = Query(default=[])):
    try:
        return get_ecosystems(services)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resources")
def list_resources(services: List[str] = Query(default=[]), ecosystems: List[str] = Query(default=[])):
    try:
        return get_resource_costs(services, ecosystems)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
