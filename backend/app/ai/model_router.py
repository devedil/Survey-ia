import json
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from backend.app.ai.call_budget import ModelCallBudget, ModelCallLimitError
from backend.app.core.config import get_settings
from backend.app.usage.models import ModelUsage
from backend.app.usage.pricing_catalog import calculate_cost
from backend.app.usage.repository import record_usage


class ModelConfigurationError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelResult:
    data: dict[str, Any]
    model: str
    input_tokens: int | None
    output_tokens: int | None


class ModelRouter:
    def __init__(self, client: Any | None = None):
        self.settings = get_settings()
        self._client_override = client

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if not self.settings.openai_api_key or self.settings.openai_api_key == "replace_me":
            raise ModelConfigurationError("OPENAI_API_KEY must be configured")
        if not self.settings.openai_default_model:
            raise ModelConfigurationError("OPENAI_DEFAULT_MODEL must be configured")
        return OpenAI(
            api_key=self.settings.openai_api_key,
            max_retries=self.settings.max_retries_per_question,
        )

    def complete_json(
        self,
        db: Session,
        *,
        profile_id: str | None,
        operation: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        call_budget: ModelCallBudget | None = None,
    ) -> ModelResult:
        model = self.settings.openai_default_model or "unconfigured"
        started = time.perf_counter()
        input_tokens = output_tokens = cached_tokens = None
        status = "failed"
        error_code = None
        error_message = None
        try:
            if call_budget:
                call_budget.consume()
            serialized_payload = json.dumps(user_payload, ensure_ascii=False)
            prompt_size = len(system_prompt) + len(serialized_payload)
            if prompt_size > self.settings.max_input_tokens_per_call * 3:
                raise ModelProviderError(
                    "Model input exceeds MAX_INPUT_TOKENS_PER_CALL",
                    "input_limit_exceeded",
                )
            response = self._client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": serialized_payload},
                ],
                response_format={"type": "json_object"},
                max_tokens=self.settings.max_output_tokens_per_call,
            )
            choice = response.choices[0]
            if not choice.message.content:
                raise ModelProviderError("Model returned an empty response", "empty_response")
            try:
                data = json.loads(choice.message.content)
            except json.JSONDecodeError as error:
                raise ModelProviderError("Model returned invalid JSON", "invalid_json") from error
            if not isinstance(data, dict):
                raise ModelProviderError("Model response must be a JSON object", "invalid_shape")
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else None
            output_tokens = usage.completion_tokens if usage else None
            cached_tokens = None
            if usage and getattr(usage, "prompt_tokens_details", None):
                cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", None)
            model = response.model or model
            status = "succeeded"
            return ModelResult(data, model, input_tokens, output_tokens)
        except ModelConfigurationError as error:
            error_code = "configuration_error"
            error_message = str(error)
            raise
        except ModelCallLimitError as error:
            error_code = "call_limit_exceeded"
            error_message = str(error)
            raise
        except ModelProviderError as error:
            error_code = error.code or "provider_error"
            error_message = str(error)
            raise
        except Exception as error:
            error_code = type(error).__name__
            error_message = "Model provider request failed"
            raise ModelProviderError(error_message, error_code) from error
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            price = (
                calculate_cost(model, input_tokens, output_tokens)
                if input_tokens is not None and output_tokens is not None
                else None
            )
            record_usage(
                db,
                ModelUsage(
                    profile_id=profile_id,
                    operation=operation,
                    provider="openai",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=cached_tokens,
                    cost_usd=price[0] if price else None,
                    cost_is_estimated=price is None,
                    pricing_version=price[1] if price else None,
                    duration_ms=duration_ms,
                    status=status,
                    error_code=error_code,
                    error_message=error_message,
                ),
            )
