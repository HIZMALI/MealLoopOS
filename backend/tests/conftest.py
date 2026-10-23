import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def csv_data():
    return b"date,menu,plate_waste_kg,kitchen_serving_waste_kg,diners\n2025-01-01,1,1,2,100\n2025-01-02,2,2,,50\n2025-01-03,1,3,1,0\n"


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    with TestClient(app) as test_client:
        yield test_client
