from app.client import UrjaClient
from app.service import MeterService

# Global service instance for the app lifespan
_client: UrjaClient = UrjaClient()
_service: MeterService = MeterService(_client)


def get_client() -> UrjaClient:
    return _client


def get_service() -> MeterService:
    return _service
