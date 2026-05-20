import os
import phoenix as px
import time
from loguru import logger

# Set environment variables like observability.py
os.environ["PHOENIX_GRPC_PORT"] = "4517"
os.environ["PHOENIX_HOST"] = "127.0.0.1"
phoenix_dir = os.path.join(os.getcwd(), "data", "phoenix_test")
os.makedirs(phoenix_dir, exist_ok=True)
os.environ["PHOENIX_DATA_DIR"] = phoenix_dir

print("Attempting to launch Phoenix without redirection...")
try:
    # Set a longer timeout if possible, though launch_app might not expose it directly in all versions
    # But let's see the error output
    session = px.launch_app()
    print("Phoenix launched successfully!")
    print(f"URL: {session.url}")
    time.sleep(5)
    px.close_app()
except Exception as e:
    print(f"Caught exception: {e}")
