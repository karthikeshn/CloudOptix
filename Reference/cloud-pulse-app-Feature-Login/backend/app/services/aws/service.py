import asyncio
from app.services.base_service import BaseCloudService
from .session import AWSSessionManager
from .scanner import ResourceExplorerScanner

class AWSService(BaseCloudService):
    def __init__(self):
        self.session_manager = AWSSessionManager()
        self.scanner = ResourceExplorerScanner()
        
    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        return await self.session_manager.test_connection(credentials)

    async def fetch_all_resources(self, credentials: dict, region: str = None) -> list[dict]:
        def _fetch():
            session = self.session_manager.create_session(credentials, region)
            return self.scanner.scan(session, region)
            
        return await asyncio.to_thread(_fetch)


