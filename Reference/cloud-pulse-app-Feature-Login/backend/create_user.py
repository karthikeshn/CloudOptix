import asyncio
import getpass
from app.core.database import SessionLocal
from app.models.system.user import SystemUser
from app.core.security import get_password_hash
from sqlalchemy.future import select

async def create_new_user(username, email, password, is_superuser=False):
    async with SessionLocal() as db:
        # Check if user already exists
        result = await db.execute(select(SystemUser).where(SystemUser.username == username))
        if result.scalars().first():
            print(f"\nError: User '{username}' already exists!")
            return

        new_user = SystemUser(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            is_superuser=is_superuser
        )
        db.add(new_user)
        await db.commit()
        print(f"\nSuccess! User '{username}' created successfully.")

if __name__ == "__main__":
    print("=== Create New Cloud Pulse User ===")
    
    username = input("Enter Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        exit(1)
        
    email = input("Enter Email (optional): ").strip()
    if not email:
        email = None
        
    password = input("Enter Password: ").strip()
    if not password:
        print("Password cannot be empty.")
        exit(1)
        
    is_admin = input("Make this user an admin? (y/n) [n]: ").strip().lower()
    is_superuser = is_admin == 'y'

    print(f"\nCreating user '{username}'...")
    asyncio.run(create_new_user(username, email, password, is_superuser))




# To create new Login id and Password in cloud pulse
# .\venv\Scripts\python.exe create_user.py
