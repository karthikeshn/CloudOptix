from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core import database
import models

# Import routers
from api.routers import auth, cloud_config, scripts, dashboard, tickets, cur_costs

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
app.include_router(tickets.router)
app.include_router(cur_costs.router)
