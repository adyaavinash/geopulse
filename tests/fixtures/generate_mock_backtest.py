import json
import random
from datetime import datetime, timedelta
import os

def generate():
    # 3. Backtest (AI vs Without AI)
    backtest = {
        "dates": [],
        "ai_portfolio": [],
        "sp500_baseline": [],
        "events": []
    }
    
    current_ai = 10000.0
    current_sp500 = 10000.0
    
    curr_date = datetime(2000, 1, 1)
    end_date = datetime.now()
    
    themes = ["chokepoint_hormuz", "market_crash", "armed_conflict_escalation", "sanctions_exportcontrols"]
    
    while curr_date < end_date:
        backtest["dates"].append(curr_date.strftime("%Y-%m-%d"))
        
        # Base market movement
        sp500_return = random.uniform(-0.03, 0.04)
        current_sp500 *= (1 + sp500_return)
        
        # AI beats it by avoiding crashes and leveraging events
        ai_return = sp500_return + random.uniform(-0.005, 0.015) 
        
        # Generate some mock events
        if random.random() < 0.02:
            event_theme = random.choice(themes)
            # AI detects event and gains alpha
            ai_return += random.uniform(0.02, 0.08)
            
            backtest["events"].append({
                "date": curr_date.strftime("%Y-%m-%d"),
                "theme": event_theme,
                "ai_decision": "Hedged / Long" if ai_return > 0 else "Short",
                "alpha_gained": round((ai_return - sp500_return) * 100, 2)
            })
            
        current_ai *= (1 + ai_return)
        
        backtest["ai_portfolio"].append(round(current_ai, 2))
        backtest["sp500_baseline"].append(round(current_sp500, 2))
        
        curr_date += timedelta(days=30)
    
    os.makedirs("tests/fixtures", exist_ok=True)
    with open("tests/fixtures/mock_backtest.json", "w") as f:
        json.dump(backtest, f, indent=2)

if __name__ == "__main__":
    generate()
    print("Generated mock backtest dataset in tests/fixtures/")
