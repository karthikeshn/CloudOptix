from app.models.control.control_action_log import ControlActionLog

def log_control_action(
    session,
    native_id: str,
    account_name: str,
    provider: str,
    action_type: str,
    status: str,
    details: str,
    resource_name: str = None,
    resource_type: str = None
) -> ControlActionLog:
    """Helper function to cleanly generate and attach a ControlActionLog to the database session."""
    log_entry = ControlActionLog(
        native_id=native_id,
        resource_name=resource_name,
        resource_type=resource_type,
        account_name=account_name,
        provider=provider,
        action_type=action_type,
        status=status,
        details=details
    )
    session.add(log_entry)
    return log_entry
