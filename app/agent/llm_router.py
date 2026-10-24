from litellm import Router
from app.config import settings
import litellm
import logging

logger = logging.getLogger(__name__)

litellm.drop_params = True
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

class EvaluationTransientError(Exception):
    """Raised when an LLM call fails due to transient network, timeout, or rate-limit errors."""
    pass

def log_cache_metrics(response):
    try:
        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = getattr(details, "cached_tokens", 0) if details else 0
            if cached_tokens > 0 and prompt_tokens > 0:
                hit_rate = (cached_tokens / prompt_tokens) * 100
                logger.info(f"[Cache Metric] OpenAI Prompt Caching Hit: {cached_tokens}/{prompt_tokens} tokens ({hit_rate:.1f}% cached)")
    except Exception as e:
        logger.debug(f"Error checking cache metrics: {e}")

# define the models and the fallback chain
model_list = [
    {
        "model_name": "gpt-6-luna",
        "litellm_params": {
            "model": "gpt-6-luna",
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
        "model_name": "gpt-6.1-sol",
        "litellm_params": {
            "model": "gpt-6.1-sol",
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
        {"gpt-6-luna": ["claude-4-5-haiku"]},
        {"gpt-6.1-sol": ["claude-5-5-sonnet"]}
    ]
)
