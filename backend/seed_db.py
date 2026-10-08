import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

from core.database import engine, SessionLocal, Base
import models
from core.security import get_password_hash

def seed():
    # Drop all tables and recreate to ensure schema is fresh
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if admin exists
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            print("Creating default admin account...")
            hashed_pw = get_password_hash("adminpassword123")
            admin_user = models.User(
                username="admin", 
                email="admin@finops.local",
                hashed_password=hashed_pw,
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            print("Admin account created successfully!")
            print("Username: admin")
            print("Password: adminpassword123")
        else:
            print("Admin already exists.")
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
