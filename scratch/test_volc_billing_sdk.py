import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from app.core.quota.manager import quota_manager
from app.infra.usage_tracker import usage_tracker

async def main():
    print("Pre-sync cloud remaining tokens:")
    print(usage_tracker.cloud_remaining_tokens)
    
    print("\nRunning sync_all...")
    await quota_manager.sync_all()
    
    print("\nPost-sync cloud remaining tokens:")
    print(usage_tracker.cloud_remaining_tokens)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
