
import sys
import os
import json
from fastapi.testclient import TestClient

# Add project root to path to verify imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(PROJECT_ROOT, 'web-dashboard'))
sys.path.append(PROJECT_ROOT)

from server import app, RESULTS_DIR

client = TestClient(app)

def test_delete_backtest():
    # 1. Create a dummy file
    filename = "test_backtest_delete_me.json"
    file_path = os.path.join(RESULTS_DIR, filename)
    
    # Ensure directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    with open(file_path, "w") as f:
        json.dump({"test": "data"}, f)
        
    assert os.path.exists(file_path)
    
    # 2. Call DELETE endpoint
    response = client.delete(f"/api/backtest/history/{filename}")
    
    # 3. Verify response
    assert response.status_code == 200
    assert response.json() == {"message": f"Successfully deleted {filename}"}
    
    # 4. Verify file is deleted
    assert not os.path.exists(file_path)

def test_delete_non_existent_file():
    filename = "non_existent_file.json"
    response = client.delete(f"/api/backtest/history/{filename}")
    
    # 2. Expect 404 Not Found as explicitly handled in server.py
    assert response.status_code == 404
    # The actual detail might just be "File not found" or standard 404.
    # Based on server.py line 628: raise HTTPException(status_code=404, detail="File not found")
    # But FastAPI/Starlette might verify path existence before handler if path param has constraints?
    # No, filename is string.
    # Wait, the error 'Not Found' usually comes from Starlette when route doesn't match?
    # But our route matches /api/backtest/history/{filename}.
    # Let's check if the detail matches exactly.
    assert response.json()["detail"] == "File not found"

def test_delete_invalid_filename():
    # Test invalid extension
    response = client.delete("/api/backtest/history/server.py")
    assert response.status_code == 400
    assert "Invalid filename" in response.json()["detail"]
