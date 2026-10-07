from litellm import Router
from app.config import settings
import litellm

litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

# define the models and the fallback chain
model_list = [
    {
        "model_name": "gpt-4o-mini",
        "litellm_params": {
            "model": "gpt-4o-mini",
            "api_key": settings.OPENAI_API_KEY
        }
    },
    {
        "model_name": "claude-4-5-haiku",
        "litellm_params": {
            "model": "anthropic/claude-haiku-4-5",
            "api_key": settings.ANTHROPIC_API_KEY
        }
    },
    {
        "model_name": "gpt-4o",
        "litellm_params": {
            "model": "gpt-4o",
            "api_key": settings.OPENAI_API_KEY
        }
    },
    {
        "model_name": "claude-5-5-sonnet",
        "litellm_params": {
            "model": "anthropic/claude-sonnet-5-5",
            "api_key": settings.ANTHROPIC_API_KEY
        }
    }
]
router = Router(
    model_list=model_list,
    fallbacks=[
        {"gpt-4o-mini": ["claude-4-5-haiku"]},
        {"gpt-4o": ["claude-5-5-sonnet"]}
    ]
)
