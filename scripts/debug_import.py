print("DEBUG: Starting import...")
try:
    import app.model_manager
    print("DEBUG: Import successful!")
except Exception as e:
    print(f"DEBUG: Import failed: {e}")
