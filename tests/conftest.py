import os

# Ensure offline test suite runs cleanly in environments without a .env file (e.g. CI runners)
os.environ.setdefault("OPENAI_API_KEY", "mock-openai-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "mock-anthropic-key")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock")

