import os
import json
import asyncio
import logging
try:
    from google import genai
except ImportError:
    genai = None
from litellm import Router
import litellm
from app.config import settings

logger = logging.getLogger(__name__)

if settings.GOOGLE_APPLICATION_CREDENTIALS:
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.GOOGLE_APPLICATION_CREDENTIALS)

litellm.drop_params = True
if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
else:
    litellm.success_callback = []
    litellm.failure_callback = []


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
                logger.info(
                    f"[Cache Metric] Prompt Caching Hit: {cached_tokens}/{prompt_tokens} tokens ({hit_rate:.1f}% cached)"
                )
    except Exception as e:
        logger.debug(f"Error checking cache metrics: {e}")


def _resolve_gcp_project() -> str:
    if settings.GCP_PROJECT_ID and settings.GCP_PROJECT_ID != "your-project-id":
        return settings.GCP_PROJECT_ID

    env_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    if env_project and env_project != "your-project-id":
        return env_project

    adc_candidates = [
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        settings.GOOGLE_APPLICATION_CREDENTIALS,
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
    ]
    for path in adc_candidates:
        if path and os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    creds_data = json.load(f)
                detected_project = creds_data.get("project_id") or creds_data.get("quota_project_id")
                if detected_project:
                    return detected_project
            except Exception as e:
                logger.debug(f"Could not read project ID from credentials file {path}: {e}")

    return settings.GCP_PROJECT_ID or "your-project-id"


try:
    # Authentication happens automatically in the background
    client = genai.Client(
        vertexai=True,
        project=_resolve_gcp_project(),
        location=settings.GCP_LOCATION,
    )
except Exception as e:
    logger.debug(f"Deferred genai.Client initialization until first call: {e}")
    client = None


def get_genai_client():
    global client
    if client is None:
        if genai is None:
            raise RuntimeError("google-genai package is not installed. Run: pip install google-genai")
        # Authentication happens automatically in the background
        client = genai.Client(
            vertexai=True,
            project=_resolve_gcp_project(),
            location=settings.GCP_LOCATION,
        )
    return client


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class GenAIResponseWrapper:
    """Normalizes google.genai GenerateContentResponse so both .text and .choices[0].message.content work."""

    def __init__(self, raw_response):
        text = getattr(raw_response, "text", None)
        if text is None and hasattr(raw_response, "choices") and raw_response.choices:
            text = raw_response.choices[0].message.content
        self.text = text or ""
        self.choices = [_Choice(self.text)]
        self.usage = getattr(raw_response, "usage", None)
        self.raw_response = raw_response


# OpenAI fallback models via LiteLLM
model_list = [
    {
        "model_name": "gpt-6-luna",
        "litellm_params": {
            "model": "gpt-6-luna",
            "api_key": settings.OPENAI_API_KEY,
        },
    },
    {
        "model_name": "gpt-6.1-sol",
        "litellm_params": {
            "model": "gpt-6.1-sol",
            "api_key": settings.OPENAI_API_KEY,
        },
    },
]

GOOGLE_TO_OPENAI_FALLBACK = {
    "gemini-3.8-flash": "gpt-6-luna",
    "gemini-3.6-flash": "gpt-6-luna",
    "gemini-4-argon": "gpt-6.1-sol",
}

litellm_router = Router(model_list=model_list)


def _messages_to_contents(messages, contents) -> str:
    if contents is not None:
        return contents
    if not messages:
        return ""
    return "\n\n".join(m.get("content", "") for m in messages if m.get("content"))


class GooglePrimaryRouter:
    """
    Routes primary LLM requests to Google Vertex AI (gemini-3.8-flash / gemini-4-argon)
    using google.genai.Client, and falls back to OpenAI models (gpt-6-luna / gpt-6.1-sol)
    via LiteLLM if the Google model call fails.
    """

    def __init__(self, fallback_router: Router, fallback_map: dict[str, str]):
        self.litellm_router = fallback_router
        self.fallback_map = fallback_map

    async def acompletion(self, model: str, messages=None, contents=None, **kwargs):
        prompt_contents = _messages_to_contents(messages, contents)
        fallback_messages = messages or [{"role": "user", "content": str(prompt_contents)}]

        if model in self.fallback_map or model.startswith("gemini"):
            try:
                genai_client = get_genai_client()
                response = await asyncio.to_thread(
                    genai_client.models.generate_content,
                    model=model,
                    contents=prompt_contents,
                )
                return GenAIResponseWrapper(response)
            except Exception as e:
                fallback_model = self.fallback_map.get(model, "gpt-6-luna")
                logger.warning(
                    f"Primary Google model '{model}' failed ({e}). Falling back to OpenAI model '{fallback_model}'."
                )
                return await self.litellm_router.acompletion(
                    model=fallback_model,
                    messages=fallback_messages,
                    **kwargs,
                )

        return await self.litellm_router.acompletion(
            model=model,
            messages=fallback_messages,
            **kwargs,
        )


router = GooglePrimaryRouter(
    fallback_router=litellm_router,
    fallback_map=GOOGLE_TO_OPENAI_FALLBACK,
)
