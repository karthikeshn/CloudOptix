from abc import ABC, abstractmethod

class BaseCloudService(ABC):
    """
    Abstract interface for cloud service providers (AWS, Azure, GCP).
    Enforces standardized execution methods across multi-cloud provider services.
    """
    @abstractmethod
    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        pass

    async def get_state(self, credentials: dict, region: str, native_id: str) -> str:
        raise NotImplementedError("get_state must be implemented by concrete provider services.")

    async def start(self, credentials: dict, region: str, native_id: str) -> dict:
        raise NotImplementedError("start must be implemented by concrete provider services.")

    async def stop(self, credentials: dict, region: str, native_id: str) -> dict:
        raise NotImplementedError("stop must be implemented by concrete provider services.")
