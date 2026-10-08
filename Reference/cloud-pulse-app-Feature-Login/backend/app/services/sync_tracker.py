import asyncio
from typing import Dict, Any

# Dictionary to store sync status
_active_syncs: Dict[str, bool] = {}
_sync_messages: Dict[str, str] = {}

def set_sync_status(module: str, account_name: str, is_syncing: bool, message: str = None):
    key = f"{module}_{account_name}"
    _active_syncs[key] = is_syncing
    if message:
        _sync_messages[key] = message

def get_sync_status(module: str, account_name: str) -> bool:
    # Used internally in python if someone just wants the bool
    key = f"{module}_{account_name}"
    return _active_syncs.get(key, False)

def get_sync_state(module: str, account_name: str) -> Dict[str, Any]:
    key = f"{module}_{account_name}"
    is_syncing = _active_syncs.get(key, False)
    message = _sync_messages.get(key)
    
    # If not syncing anymore, we can return the message and then clear it so we don't return it forever.
    # Actually, leaving it there is fine, but clearing it after one read is safer.
    result = {"is_syncing": is_syncing, "message": message}
    
    if not is_syncing and key in _sync_messages:
        del _sync_messages[key]
        
    return result
