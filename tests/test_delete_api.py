import sys
import os
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(PROJECT_ROOT, 'web-dashboard'))
sys.path.append(PROJECT_ROOT)

from server import app
from db.repositories import BacktestRepository

client = TestClient(app)


def test_delete_backtest():
    filename = "test_backtest_delete_me.json"
    run_id = "test_backtest_delete_me"
    BacktestRepository().save(run_id, {"test": "data"})

    response = client.delete(f"/api/backtest/history/{filename}")
    assert response.status_code == 200
    assert response.json() == {"message": f"Successfully deleted {filename}"}

    assert BacktestRepository().get_by_id(run_id) is None


def test_delete_non_existent_file():
    filename = "non_existent_file.json"
    response = client.delete(f"/api/backtest/history/{filename}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"

def test_delete_invalid_filename():
    # Test invalid extension
    response = client.delete("/api/backtest/history/server.py")
    assert response.status_code == 400
    assert "Invalid filename" in response.json()["detail"]
