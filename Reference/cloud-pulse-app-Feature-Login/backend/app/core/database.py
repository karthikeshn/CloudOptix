from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, event
from sqlalchemy.orm import declarative_base
from app.core.config import settings

Base = declarative_base()

engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,
    connect_args={"timeout": 30.0}
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    from app.models.control.control_resource import ControlResource
    from app.models.config.config_cloud_account import ConfigCloudAccount
    from app.models.control.control_action_log import ControlActionLog
    from app.models.inventory.inventory_resource import InventoryResource
    from app.models.inventory.inventory_change import InventoryChange
    from app.models.inventory.inventory_snapshot import InventorySnapshot
    from app.models.system.system_notification import SystemNotification
    from app.models.system.user import SystemUser
    from app.core.security import get_password_hash
    
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        
        # Performance Indexes
        try:
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_res_status ON inventory_resources(status)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_res_type ON inventory_resources(resource_type)"))
            # Composite index for the most common query pattern
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inv_res_acc_stat ON inventory_resources(account_name, status, provider)"))
        except Exception:
            pass
            
        # Schema Migrations
        try:
            await conn.execute(text("ALTER TABLE config_cloud_accounts ADD COLUMN last_error VARCHAR"))
        except Exception:
            pass

        await conn.run_sync(Base.metadata.create_all)
        
    async with SessionLocal() as db:
        # Check if default admin exists
        from sqlalchemy.future import select
        result = await db.execute(select(SystemUser).limit(1))
        if not result.scalars().first():
            # Seed default admin user
            admin_user = SystemUser(
                username="admin",
                email="admin@cloudpulse.local",
                password_hash=get_password_hash("cd@12345"),
                is_superuser=True
            )
            db.add(admin_user)
            await db.commit()
            print("Default admin user seeded. Username: admin | Password: cd@12345")
            
async def get_db():
    async with SessionLocal() as session:
        yield session

