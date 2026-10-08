import asyncio
import importlib
import logging
import inspect
from app.services.aws.session import AWSSessionManager
from app.services.aws.scanner import scan_all_resources_parallel

logger = logging.getLogger(__name__)

class ControlExecutionRouter:
    def __init__(self):
        self.aws_session_manager = AWSSessionManager()
        self._services = {}

    def _get_service(self, provider: str, resource_type: str):
        provider = provider.lower()
        resource_type = resource_type.lower()
        handler_type = 'rds' if resource_type == 'aurora' else resource_type
        key = (provider, handler_type)
        if key in self._services:
            return self._services[key]

        subfolders = ['direct_power', 'scale_to_zero', 'destroy_recreate']
        for folder in subfolders:
            try:
                module_name = f"app.services.{provider}.handlers.{folder}.{handler_type}_handler"
                module = importlib.import_module(module_name)
                
                # Find the concrete Handler class inside the module dynamically
                service_class = None
                for attr_name in dir(module):
                    if attr_name.endswith("Handler"):
                        cls = getattr(module, attr_name)
                        if inspect.isclass(cls) and not inspect.isabstract(cls):
                            service_class = cls
                            break
                
                if not service_class:
                    continue
                    
                service_instance = service_class()
                self._services[key] = service_instance
                return service_instance
                
            except ImportError:
                continue
                
        logger.error(f"No Handler found for {provider} {handler_type}")
        return None

    async def get_resource_state(self, provider: str, credentials: dict, region: str, resource_type: str, native_id: str) -> str:
        service = self._get_service(provider, resource_type)
        if not service:
            if provider in ['azure', 'gcp']:
                raise NotImplementedError(f"Control operations for {provider} are planned for a future release.")
            return 'UNKNOWN'
        
        session_mgr = self.aws_session_manager if provider == 'aws' else None
        
        if resource_type.lower() == 'aurora':
            return await service.get_state(session_mgr, credentials, region, native_id, is_cluster=True)
        return await service.get_state(session_mgr, credentials, region, native_id)

    async def start_resource(self, provider: str, credentials: dict, region: str, resource_type: str, native_id: str, saved_config: str = None) -> dict:
        service = self._get_service(provider, resource_type)
        if not service:
            if provider in ['azure', 'gcp']:
                raise NotImplementedError(f"Control operations for {provider} are planned for a future release.")
            return {"status": "error", "message": f"Unsupported resource type {resource_type} for provider {provider}"}
            
        session_mgr = self.aws_session_manager if provider == 'aws' else None
        
        if resource_type.lower() == 'aurora':
            return await service.start(session_mgr, credentials, region, native_id, saved_config=saved_config, is_cluster=True)
        return await service.start(session_mgr, credentials, region, native_id, saved_config=saved_config)

    async def stop_resource(self, provider: str, credentials: dict, region: str, resource_type: str, native_id: str, saved_config: str = None) -> dict:
        service = self._get_service(provider, resource_type)
        if not service:
            if provider in ['azure', 'gcp']:
                raise NotImplementedError(f"Control operations for {provider} are planned for a future release.")
            return {"status": "error", "message": f"Unsupported resource type {resource_type} for provider {provider}"}
            
        session_mgr = self.aws_session_manager if provider == 'aws' else None
        
        if resource_type.lower() == 'aurora':
            return await service.stop(session_mgr, credentials, region, native_id, saved_config=saved_config, is_cluster=True)
        return await service.stop(session_mgr, credentials, region, native_id, saved_config=saved_config)

    async def sync_provider_resources(self, provider: str, credentials: dict, region: str = "all") -> list[dict]:
        if provider == 'aws':
            default_region = credentials.get('default_region', 'us-east-1')
            raw_resources = await scan_all_resources_parallel(credentials, default_region, region)
            return raw_resources
        else:
            raise NotImplementedError(f"Sync operations for {provider} are planned for a future release.")

    def validate_resource_hierarchy(self, resource) -> tuple[bool, str]:
        """
        Validates if a resource can be manually controlled based on its hierarchy.
        Returns (is_valid, error_message)
        """
        if resource and getattr(resource, 'parent_resource_id', None):
            is_ecs_service = (resource.service_type == 'ECS')
            is_eks_nodegroup = (resource.service_type == 'EKS' and resource.resource_id != resource.parent_resource_id)
            is_unmanaged_eks_asg = (resource.service_type == 'ASG' and resource.instance_spec and 'EKS (Unmanaged)' in resource.instance_spec)
            is_beanstalk_env = (resource.service_type == 'BEANSTALK')
            
            if not (is_ecs_service or is_eks_nodegroup or is_unmanaged_eks_asg or is_beanstalk_env):
                return False, f"Resource is natively managed by {resource.parent_resource_id}. Please control the parent instead."
        
        return True, ""

control_service = ControlExecutionRouter()
