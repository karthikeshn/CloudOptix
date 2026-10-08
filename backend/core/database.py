import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load the database URL from the environment (e.g. from a .env file loaded by your app or test runner)
# If it doesn't exist, fall back to the production finops_v4.db
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/finops_v4.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
