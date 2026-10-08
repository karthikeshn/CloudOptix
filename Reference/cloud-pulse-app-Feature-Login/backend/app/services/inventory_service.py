import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from app.models import InventoryResource, InventoryChange, InventorySnapshot

async def generate_trend_snapshot(db: AsyncSession, provider: str, account_name: str):
    stmt = select(InventoryResource).where(
        InventoryResource.provider == provider,
        InventoryResource.account_name == account_name,
        InventoryResource.status == "active"
    )
    result = await db.execute(stmt)
    active_items = result.scalars().all()
    
    total = len(active_items)
    billable = sum(1 for x in active_items if x.billable)
    non_billable = total - billable
    
    breakdown: Dict[str, int] = {}
    for item in active_items:
        breakdown[item.resource_type] = breakdown.get(item.resource_type, 0) + 1
        
    today_prefix = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    del_stmt = select(InventoryResource).where(
        InventoryResource.provider == provider,
        InventoryResource.account_name == account_name,
        InventoryResource.status == "deleted",
        InventoryResource.deleted_at.like(f"{today_prefix}%")
    )
    del_result = await db.execute(del_stmt)
    deleted_today_count = len(del_result.scalars().all())
    
    # Check if the last snapshot for this account has identical metrics
    last_stmt = select(InventorySnapshot).where(
        InventorySnapshot.account_name == account_name
    ).order_by(InventorySnapshot.snapshot_date.desc()).limit(1)
    last_result = await db.execute(last_stmt)
    last_snapshot = last_result.scalars().first()

    if last_snapshot and last_snapshot.total_active_count == total:
        # Update the timestamp of the last snapshot to reflect the latest sync time
        last_snapshot.snapshot_date = datetime.utcnow()
        await db.commit()
        return

    snapshot = InventorySnapshot(
        total_active_count=total,
        billable_count=billable,
        non_billable_count=non_billable,
        deleted_today=deleted_today_count,
        category_breakdown=json.dumps(breakdown),
        account_name=account_name
    )
    db.add(snapshot)
    await db.commit()


async def sync_inventory(
    db: AsyncSession, 
    provider: str, 
    account_name: str, 
    fetched_resources: List[Dict[str, Any]]
) -> Dict[str, int]:
    ist_delta = timedelta(hours=5, minutes=30)
    current_ist_time = (datetime.utcnow() + ist_delta).strftime("%Y-%m-%d %H:%M:%S IST")
    
    # Pre-Sync Data Migration: Auto-Merge Orphaned Data
    # If the user deleted the config and recreated it with a new name, we can identify 
    # the old data using the unique linked_account (e.g. AWS Account ID) and adopt it.
    if fetched_resources:
        active_linked = fetched_resources[0].get("linked_account")
        if active_linked:
            # Find the old orphaned account names
            old_accounts_stmt = select(InventoryResource.account_name).where(
                InventoryResource.provider == provider,
                InventoryResource.linked_account == active_linked,
                InventoryResource.account_name != account_name
            ).distinct()
            old_result = await db.execute(old_accounts_stmt)
            old_accounts = old_result.scalars().all()
            
            if old_accounts:
                # Merge Inventory
                await db.execute(
                    update(InventoryResource)
                    .where(
                        InventoryResource.provider == provider,
                        InventoryResource.linked_account == active_linked,
                        InventoryResource.account_name != account_name
                    )
                    .values(account_name=account_name)
                )
                
                # Merge Change Logs
                await db.execute(
                    update(InventoryChange)
                    .where(InventoryChange.account_name.in_(old_accounts))
                    .values(account_name=account_name)
                )
                
                # Merge Snapshots
                await db.execute(
                    update(InventorySnapshot)
                    .where(InventorySnapshot.account_name.in_(old_accounts))
                    .values(account_name=account_name)
                )
                await db.commit()
    
    fetched_native_ids = [f["native_id"] for f in fetched_resources]
    
    stmt = select(InventoryResource).where(
        (InventoryResource.provider == provider) &
        ((InventoryResource.account_name == account_name) | (InventoryResource.native_id.in_(fetched_native_ids)))
    )
    result = await db.execute(stmt)
    db_resources = result.scalars().all()
    
    db_map = {r.native_id: r for r in db_resources}
    fetched_map = {f["native_id"]: f for f in fetched_resources}
    
    metrics = {"created": 0, "deleted": 0, "updated": 0}
    
    # Phase A: Detect New and Still Active Items
    for native_id, item in fetched_map.items():
        aws_created = item.get("first_seen_date")
        if native_id not in db_map:
            new_item = InventoryResource(
                native_id=native_id,
                name=item.get("name"),
                tags=item.get("tags"),
                resource_type=item["type"],
                provider=provider,
                account_name=account_name,
                region=item["region"],
                linked_account=item.get("linked_account"),
                billable=item["billable"],
                billing_tier=item.get("billing_tier"),
                status="active",
                first_seen_date=aws_created if aws_created else current_ist_time,
                deleted_at=None
            )
            db.add(new_item)
            change_log = InventoryChange(native_id=native_id, change_type="created", account_name=account_name)
            db.add(change_log)
            metrics["created"] += 1
        else:
            db_item = db_map[native_id]
            updated = False
            changes_dict = {}
            
            # Adopt orphaned resources individually if they missed the bulk auto-merge
            if db_item.account_name != account_name:
                db_item.account_name = account_name
                updated = True
                
            if db_item.status == "deleted":
                changes_dict["status"] = {"old": "deleted", "new": "active"}
                db_item.status = "active"
                db_item.deleted_at = None
                updated = True
                
            if "name" in item and db_item.name != item["name"]:
                changes_dict["name"] = {"old": db_item.name, "new": item["name"]}
                db_item.name = item["name"]
                updated = True
                
            if "tags" in item and db_item.tags != item["tags"]:
                changes_dict["tags"] = {"old": db_item.tags, "new": item["tags"]}
                db_item.tags = item["tags"]
                updated = True
                
            if "billing_tier" in item and db_item.billing_tier != item["billing_tier"]:
                changes_dict["billing_tier"] = {"old": db_item.billing_tier, "new": item["billing_tier"]}
                db_item.billing_tier = item["billing_tier"]
                updated = True
                
            if "billable" in item and db_item.billable != item["billable"]:
                changes_dict["billable"] = {"old": db_item.billable, "new": item["billable"]}
                db_item.billable = item["billable"]
                updated = True
                
            db_item.linked_account = item.get("linked_account")
            
            if changes_dict:
                change_log = InventoryChange(
                    native_id=native_id, 
                    change_type="updated", 
                    account_name=account_name,
                    details=json.dumps(changes_dict)
                )
                db.add(change_log)
                
            if updated:
                metrics["updated"] += 1

    # Phase B: Detect Deleted Items
    for native_id, db_item in db_map.items():
        if native_id not in fetched_map and db_item.status == "active":
            db_item.status = "deleted"
            db_item.deleted_at = current_ist_time
            change_log = InventoryChange(native_id=native_id, change_type="deleted", account_name=account_name)
            db.add(change_log)
            metrics["deleted"] += 1

    await db.commit()
    
    # Phase C: Data Pruning (Safe Database Optimization)
    # Automatically delete audit logs older than 90 days to prevent infinite SQLite growth
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        from sqlalchemy import delete
        cleanup_stmt = delete(InventoryChange).where(
            (InventoryChange.account_name == account_name) & 
            (InventoryChange.timestamp < cutoff_date)
        )
        await db.execute(cleanup_stmt)
        await db.commit()
    except Exception as e:
        print(f"Data pruning failed: {e}")
    
    await generate_trend_snapshot(db, provider, account_name)
    
    metrics["total_active"] = len(fetched_map)
    return metrics
