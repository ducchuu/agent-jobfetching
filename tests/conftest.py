import os

# Ensure offline test suite runs cleanly in environments without a .env file (e.g. CI runners)
os.environ.setdefault("GCP_PROJECT_ID", "mock-gcp-project")
os.environ.setdefault("GCP_LOCATION", "us-central1")
os.environ.setdefault("OPENAI_API_KEY", "mock-openai-key")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock")

