from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    DISCORD_WEBHOOK_URL: str
    MATCH_THRESHOLD: int = 80
    CLOUDFLARE_TUNNEL_TOKEN: str = ""
    
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
