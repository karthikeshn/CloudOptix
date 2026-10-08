import asyncio
import logging
from app.services.base_service import BaseCloudService
from app.services.gcp.session import GCPAuthManager
from app.services.gcp.scanner import GCPProjectScanner

logger = logging.getLogger(__name__)

class GCPService(BaseCloudService):
    def __init__(self):
        self.session_manager = GCPAuthManager()
        self.scanner = GCPProjectScanner()
        
    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        """
        Validates the GCP credentials by attempting to parse them.
        """
        return await self.session_manager.test_connection(credentials)

    async def fetch_all_resources(self, credentials: dict, default_region: str = "global") -> list:
        """
        Fetches all resources using the Cloud Asset API wrapper.
        """
        def _fetch():
            creds, project_id = self.session_manager.create_session(credentials)
            return self.scanner.scan_all_resources(creds, project_id)
            
        return await asyncio.to_thread(_fetch)
