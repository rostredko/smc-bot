import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add web-dashboard directory to path to import server
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web-dashboard'))

from server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_user_configs():
    """Clear user_configs before each test for isolation."""
    from db.repositories import UserConfigRepository
    repo = UserConfigRepository()
    for name in repo.list_names():
        repo.delete(name)
    yield


def test_list_empty_configs():
    response = client.get("/api/user-configs")
    assert response.status_code == 200
    assert response.json() == {"configs": []}

def test_save_and_list_config():
    test_config = {"symbol": "BTC/USDT", "initial_capital": 10000}
    
    # Save
    response = client.post("/api/user-configs/test_template", json=test_config)
    assert response.status_code == 200
    assert "saved successfully" in response.json()["message"]
    
    # List
    response = client.get("/api/user-configs")
    assert response.status_code == 200
    assert response.json() == {"configs": ["test_template"]}

def test_get_config():
    test_config = {"symbol": "ETH/USDT", "leverage": 5}
    client.post("/api/user-configs/eth_template", json=test_config)
    
    response = client.get("/api/user-configs/eth_template")
    assert response.status_code == 200
    assert response.json() == test_config

def test_get_nonexistent_config():
    response = client.get("/api/user-configs/does_not_exist")
    assert response.status_code == 404

def test_delete_config():
    test_config = {"test": "data"}
    client.post("/api/user-configs/to_delete", json=test_config)
    
    response = client.delete("/api/user-configs/to_delete")
    assert response.status_code == 200
    
    response = client.get("/api/user-configs")
    assert response.json() == {"configs": []}

def test_path_traversal_protection():
    response = client.get("/api/user-configs/name..withdots")
    assert response.status_code == 400
    
    response = client.post("/api/user-configs/name..withdots", json={})
    assert response.status_code == 400
    
    response = client.delete("/api/user-configs/name..withdots")
    assert response.status_code == 400
