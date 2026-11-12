"""Server-only OpenAI/Groq client with fixed endpoints and validated JSON output."""
import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
DIAGNOSTIC_CODES = {
    "insufficient_quota", "rate_limit_exceeded", "invalid_api_key", "model_not_found",
    "credit_balance_exhausted", "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded", "organization_usage_limit_exceeded", "slow_down",
}


class PlanningUnavailable(Exception):
    """A safe category; never expose provider responses or credentials."""


def generate_structured(instructions: str, context: dict, output_type: type[T]) -> T:
    settings = get_settings()
    key = settings.planning_api_key
    if not key or not key.get_secret_value():
        raise PlanningUnavailable("missing_key")
    schema_format = {"name": output_type.__name__, "strict": True,
                     "schema": output_type.model_json_schema()}
    if settings.llm_provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        body = {
            "model": settings.llm_model,
            "messages": [{"role": "system", "content": instructions},
                         {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            "max_completion_tokens": settings.llm_max_output_tokens,
            "response_format": {"type": "json_schema", "json_schema": schema_format},
            "stream": False,
        }
        if settings.llm_model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
            body.update(reasoning_effort="low", include_reasoning=False)
    else:
        url = "https://api.openai.com/v1/responses"
        body = {
            "model": settings.llm_model, "instructions": instructions,
            "input": json.dumps(context, ensure_ascii=False), "store": False,
            "max_output_tokens": settings.llm_max_output_tokens,
            "text": {"format": {"type": "json_schema", **schema_format}},
        }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        if settings.llm_provider == "groq":
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise PlanningUnavailable("incomplete")
            message = choice["message"]
            if message.get("refusal") or not isinstance(message.get("content"), str) or not message["content"].strip():
                raise PlanningUnavailable("refused_or_empty")
            output = message["content"]
        else:
            if data.get("status") != "completed":
                raise PlanningUnavailable("incomplete")
            chunks = [part["text"] for item in data.get("output", [])
                      if item.get("type") == "message"
                      for part in item.get("content", []) if part.get("type") == "output_text"]
            if not chunks:
                raise PlanningUnavailable("refused_or_empty")
            output = "".join(chunks)
        return output_type.model_validate_json(output)
    except httpx.HTTPStatusError as exc:
        # Log only known diagnostic categories; provider text may contain request data.
        category = "provider_error"
        try:
            code = exc.response.json().get("error", {}).get("code")
            if isinstance(code, str) and code in DIAGNOSTIC_CODES:
                category = code
        except (ValueError, AttributeError, TypeError):
            pass
        if category == "provider_error" and exc.response.status_code == 429:
            category = "rate_limit_exceeded"
        elif category == "provider_error" and exc.response.status_code == 401:
            category = "invalid_api_key"
        elif category == "provider_error" and exc.response.status_code == 403:
            category = "access_denied"
        elif category == "provider_error" and exc.response.status_code == 404:
            category = "model_not_found"
        elif category == "provider_error" and exc.response.status_code >= 500:
            category = "provider_unavailable"
        logger.warning("Planning provider %s HTTP status %s (%s)", settings.llm_provider, exc.response.status_code, category)
        raise PlanningUnavailable(category) from None
    except httpx.TimeoutException:
        logger.warning("Planning provider request timed out")
        raise PlanningUnavailable("timeout") from None
    except httpx.RequestError:
        logger.warning("Planning provider connection failed")
        raise PlanningUnavailable("connection_error") from None
    except ValidationError:
        logger.warning("Planning provider output failed validation")
        raise PlanningUnavailable("invalid_output") from None
    except (ValueError, KeyError, IndexError, AttributeError, TypeError):
        logger.warning("Planning provider response was malformed")
        raise PlanningUnavailable("invalid_response") from None
