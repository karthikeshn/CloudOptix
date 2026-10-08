import asyncio
from app.services.base_service import BaseCloudService
from .session import AzureAuthManager
from .scanner import AzureResourceGraphScanner

class AzureService(BaseCloudService):
    def __init__(self):
        self.session_manager = AzureAuthManager()
        self.scanner = AzureResourceGraphScanner()
        
    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        return await self.session_manager.test_connection(credentials)
        
    async def fetch_all_resources(self, credentials: dict, subscription_id: str = None) -> list:
        """
        Fetches all resources using the Resource Graph API.
        If subscription_id is not provided, fetches across the entire tenant.
        """
        def _fetch():
            creds = self.session_manager.create_session(credentials)
            return self.scanner.scan(creds, subscription_id)
            
        return await asyncio.to_thread(_fetch)
