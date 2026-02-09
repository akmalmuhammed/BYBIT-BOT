import sys
import os
from datetime import datetime, timezone, timedelta

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import get_current_time, TIMEZONE

def verify_time():
    print(f"Verifying Timezone Configuration...")
    current_time = get_current_time()
    print(f"Current Configured Time: {current_time}")
    print(f"Timezone Info: {current_time.tzinfo}")
    
    utc_now = datetime.now(timezone.utc)
    print(f"UTC Now: {utc_now}")
    
    diff = current_time.replace(tzinfo=None) - utc_now.replace(tzinfo=None)
    # Round to nearest hour to avoid second-level differences
    hours_diff = round(diff.total_seconds() / 3600)
    
    print(f"Difference from UTC: {hours_diff} hours")
    
    if hours_diff == 3:
        print("✅ SUCCESS: Timezone is correctly set to UTC+3")
    else:
        print(f"❌ FAILURE: Expected +3 hours, got {hours_diff} hours")

if __name__ == "__main__":
    verify_time()
