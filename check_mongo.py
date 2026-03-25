import sys
import os
from pymongo import MongoClient

def main():
    client = MongoClient("mongodb://mongo:27017/")
    db = client["backtrade"]
    coll = db["backtests"]
    
    # Get the latest backtest
    doc = coll.find_one({}, sort=[("created_at", -1)])
    if not doc:
        print("No backtests found")
        return
        
    print(f"Run ID: {doc.get('run_id')}")
    print(f"Total Trades: {doc.get('results', {}).get('total_trades')}")
    signals = doc.get("results", {}).get("signals", [])
    print(f"Total Signals: {len(signals)}")
    
    # Print the first 20 rejected signals to see why
    count = 0
    for s in signals:
        if s.get("action") == "REJECTED":
            print(f"REJECTED at {s.get('datetime')}: {s.get('reason')} - Details: {s.get('details', {}).get('why_rejected')}")
            count += 1
            if count >= 20:
                break
                
    if count == 0:
        print("No REJECTED signals found in the signals array either.")

if __name__ == "__main__":
    main()
