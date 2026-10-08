from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import asyncio
from botocore.exceptions import ClientError, EndpointConnectionError

def parse_aws_client_error(e: Exception) -> str:
    if isinstance(e, EndpointConnectionError):
        return "Service endpoint is not available in this region."
        
    error_code = e.response.get('Error', {}).get('Code', 'UnknownError') if hasattr(e, 'response') and e.response else 'UnknownError'
    error_message = e.response.get('Error', {}).get('Message', str(e)) if hasattr(e, 'response') and e.response else str(e)
    
    if error_code == 'OptInRequired':
        return "Service is not opted-in or subscribed in this region."
    elif error_code in ['AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation']:
        return "IAM Policy missing or insufficient permissions."
    elif error_code == 'AuthFailure':
        return "AWS Credentials are invalid or expired."
    return f"[{error_code}] {error_message}"

class ControlResourceHandler(ABC):
    """
    Abstract base class for specific cloud resources (e.g. EC2, RDS).
    Combines both Discovery (scanning) and Control (start/stop) logic into a single cohesive unit.
    """
    
    _error_cache = set()

    @classmethod
    def log_once(cls, service_name: str, error_message: str):
        key = f"{service_name}_{error_message}"
        if key not in cls._error_cache:
            cls._error_cache.add(key)
            logging.warning(f"[{service_name}] {error_message}")

    def _run_with_error_handling(self, func, error_return_type: str, success_return: Any, *args, **kwargs):
        """Standardized try-catch wrapper for AWS execution methods."""
        try:
            res = func(*args, **kwargs)
            if callable(success_return):
                return success_return(res)
            return success_return if success_return is not None else res
        except ClientError as e:
            err_msg = parse_aws_client_error(e)
            if error_return_type == "list":
                self.log_once(self.__class__.__name__, err_msg)
                return []
            elif error_return_type == "state":
                logging.error(f"Error in {self.__class__.__name__}: {err_msg}")
                return "error"
            else:
                return {"status": "error", "message": err_msg}
        except Exception as e:
            err_msg = str(e)
            if error_return_type == "list":
                self.log_once(self.__class__.__name__, err_msg)
                return []
            elif error_return_type == "state":
                logging.error(f"Unexpected error in {self.__class__.__name__}: {err_msg}")
                return "error"
            else:
                return {"status": "error", "message": err_msg}
            
    @abstractmethod
    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        """Discover resources of this type in a given region."""
        pass

    @abstractmethod
    async def get_state(self, session_manager, credentials: dict, region: str, native_id: str) -> str:
        """Get the real-time operational state of a specific resource."""
        pass

    @abstractmethod
    async def start(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        """Power ON a specific resource."""
        pass

    @abstractmethod
    async def stop(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        """Power OFF a specific resource."""
        pass

class BaseDirectPowerHandler(ControlResourceHandler):
    """
    Base class for resources that support Direct Power Control (Native Start/Stop).
    Handles boilerplate Boto3 async dispatching and error catching.
    """
    async def async_scan_region(self, session_manager, credentials: dict, region: str, executor=None) -> List[Dict[str, Any]]:
        import random
        await asyncio.sleep(random.uniform(0.1, 1.5))
        def _scan():
            session = session_manager.create_session(credentials, region)
            return self._run_with_error_handling(self._execute_scan_region, "list", None, session, region)
        if executor:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, _scan)
        return await asyncio.to_thread(_scan)

    async def get_state(self, session_manager, credentials: dict, region: str, native_id: str, **kwargs) -> str:
        def _get():
            session = session_manager.create_session(credentials, region)
            return self._run_with_error_handling(self._execute_get_state, "state", None, session, native_id, **kwargs)
        return await asyncio.to_thread(_get)

    async def start(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        state = await self.get_state(session_manager, credentials, region, native_id, **kwargs)
        if state != 'STOPPED':
            return {"status": "error", "message": f"Resource {native_id} is in '{state}' state, must be 'STOPPED' to start."}
            
        def _start():
            session = session_manager.create_session(credentials, region)
            success = {"status": "success", "action": "START", "resource_id": native_id, "message": "Successfully initiated START sequence."}
            return self._run_with_error_handling(self._execute_start, "dict", success, session, native_id, **kwargs)
        return await asyncio.to_thread(_start)

    async def stop(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        state = await self.get_state(session_manager, credentials, region, native_id, **kwargs)
        if state != 'RUNNING':
            return {"status": "error", "message": f"Resource {native_id} is in '{state}' state, must be 'RUNNING' to stop."}
            
        def _stop():
            session = session_manager.create_session(credentials, region)
            success = {"status": "success", "action": "STOP", "resource_id": native_id, "message": "Successfully initiated STOP sequence."}
            return self._run_with_error_handling(self._execute_stop, "dict", success, session, native_id, **kwargs)
        return await asyncio.to_thread(_stop)

    @abstractmethod
    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        pass

    @abstractmethod
    def _execute_start(self, session, native_id: str, **kwargs):
        pass

    @abstractmethod
    def _execute_stop(self, session, native_id: str, **kwargs):
        pass

class BaseScaleToZeroHandler(ControlResourceHandler):
    """
    Base class for resources that are scaled to zero (e.g. ASG, ECS).
    Maintains capacity state using saved_config JSON.
    """
    async def async_scan_region(self, session_manager, credentials: dict, region: str, executor=None) -> List[Dict[str, Any]]:
        import random
        await asyncio.sleep(random.uniform(0.1, 1.5))
        def _scan():
            session = session_manager.create_session(credentials, region)
            return self._run_with_error_handling(self._execute_scan_region, "list", None, session, region)
        if executor:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, _scan)
        return await asyncio.to_thread(_scan)

    async def get_state(self, session_manager, credentials: dict, region: str, native_id: str, **kwargs) -> str:
        def _get():
            session = session_manager.create_session(credentials, region)
            return self._run_with_error_handling(self._execute_get_state, "state", None, session, native_id, region=region, **kwargs)
        return await asyncio.to_thread(_get)

    async def start(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        state = await self.get_state(session_manager, credentials, region, native_id, **kwargs)
        if state != 'STOPPED':
            return {"status": "error", "message": f"Resource {native_id} is in '{state}' state, must be 'STOPPED' to start."}
            
        def _start():
            session = session_manager.create_session(credentials, region)
            success = {"status": "success", "action": "START", "resource_id": native_id, "message": "Successfully initiated SCALE_TO_ORIGINAL sequence."}
            return self._run_with_error_handling(self._execute_start, "dict", success, session, native_id, saved_config, region=region, **kwargs)
        return await asyncio.to_thread(_start)

    async def stop(self, session_manager, credentials: dict, region: str, native_id: str, saved_config: str = None, **kwargs) -> dict:
        state = await self.get_state(session_manager, credentials, region, native_id, **kwargs)
        if state != 'RUNNING':
            return {"status": "error", "message": f"Resource {native_id} is in '{state}' state, must be 'RUNNING' to stop."}
            
        def _stop():
            session = session_manager.create_session(credentials, region)
            def success_fn(new_saved_config):
                res = {"status": "success", "action": "STOP", "resource_id": native_id, "message": "Successfully initiated SCALE_TO_ZERO sequence."}
                if new_saved_config:
                    res["saved_config_json"] = new_saved_config
                return res
            return self._run_with_error_handling(self._execute_stop, "dict", success_fn, session, native_id, region=region, **kwargs)
        return await asyncio.to_thread(_stop)

    @abstractmethod
    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        pass

    @abstractmethod
    def _execute_start(self, session, native_id: str, saved_config: str, **kwargs):
        pass

    @abstractmethod
    def _execute_stop(self, session, native_id: str, **kwargs) -> str:
        pass
