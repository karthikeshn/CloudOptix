import pytest
from httpx import AsyncClient
from typing import AsyncGenerator
import sys
import os

# Add the backend directory to sys.path so we can import from core, api, etc.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from core.database import get_db

# Dummy override for database if we want to use an in-memory SQLite later
# def override_get_db():
#     yield None

@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
