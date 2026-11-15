
import os
import json
from typing import Any

import requests
from dotenv import load_dotenv
from pydantic import ConfigDict, SecretStr

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun


# Load environment variables
load_dotenv()


class ZohoRequestTooLargeError(RuntimeError):
    """Raised when Zoho rejects a prompt because its input is too large."""


class ZohoQuickMLChat(BaseChatModel):

    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    # -----------------------------------------
    # Zoho QuickML Configuration
    # -----------------------------------------

    url: str = os.getenv("ZOHO_QUICKML_URL", "")

    endpoint_key: SecretStr = SecretStr(
        os.getenv("ZOHO_QUICKML_KEY", "")
    )

    access_token: SecretStr = SecretStr(
        os.getenv("ZOHO_ACCESS_TOKEN", "")
    )

    catalyst_org: str = os.getenv(
        "ZOHO_CATALYST_ORG", ""
    )

    environment: str = "Development"

    request_timeout: float = 60.0

    # -----------------------------------------
    # 1. LangChain Model Identification
    # -----------------------------------------

    @property
    def _llm_type(self) -> str:
        return "zoho-quickml"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "endpoint": self.url,
            "environment": self.environment
        }

    # -----------------------------------------
    # 2. Authentication Headers
    # -----------------------------------------

    def _get_headers(self) -> dict[str, str]:

        return {
            "x-quickml-endpoint-key":
                self.endpoint_key.get_secret_value(),

            "Authorization":
                f"Zoho-oauthtoken "
                f"{self.access_token.get_secret_value()}",

            "CATALYST-ORG": self.catalyst_org,

            "Content-Type": "application/json",

            "Environment": self.environment
        }

    # -----------------------------------------
    # 3. Convert LangChain Messages
    # -----------------------------------------

    def _convert_messages(
        self,
        messages: list[BaseMessage]
    ) -> str:

        converted_messages = []

        for message in messages:

            role_mapping = {
                "system": "System",
                "human": "User",
                "ai": "Assistant"
            }

            role = role_mapping.get(message.type)

            if role is None:
                raise ValueError(
                    f"Unsupported message type: {message.type}"
                )

            if not isinstance(message.content, str):
                raise ValueError(
                    "Only text messages are currently supported."
                )

            converted_messages.append(
                f"{role}: {message.content}"
            )

        return "\n".join(converted_messages)

    # -----------------------------------------
    # 4. Build Zoho Request Payload
    # -----------------------------------------

    def _build_payload(
        self,
        messages: list[BaseMessage]
    ) -> dict[str, Any]:

        prompt = self._convert_messages(messages)

        return {
            "prompt": prompt
        }

    # -----------------------------------------
    # 5. Extract Generated Text
    # -----------------------------------------

    def _extract_response(
        self,
        data: dict[str, Any]
    ) -> str:

        try:

            generated_text = data["data"][0]["data"]

            if not isinstance(generated_text, str):
                raise ValueError(
                    "Generated response is not text."
                )

            return generated_text

        except (KeyError, IndexError, TypeError) as exc:

            raise ValueError(
                f"Unexpected Zoho response structure: {data}"
            ) from exc

    # -----------------------------------------
    # 6. HTTP Request to Zoho
    # -----------------------------------------

    def _call_zoho(
        self,
        payload: dict[str, Any]
    ) -> dict[str, Any]:

        if not self.url:
            raise ValueError(
                "ZOHO_QUICKML_URL is not configured."
            )

        try:

            response = requests.post(
                self.url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.request_timeout
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.Timeout as exc:

            raise RuntimeError(
                "Zoho QuickML request timed out."
            ) from exc

        except requests.exceptions.HTTPError as exc:

            error_body = exc.response.text[:1000]
            status_code = exc.response.status_code

            if "MORE_THAN_MAX_LENGTH" in error_body:
                raise ZohoRequestTooLargeError(
                    "Zoho rejected the prompt because it exceeds the "
                    "endpoint's maximum input length. Reduce previous-section "
                    "context, source facts, memory rules, or revision text. "
                    f"HTTP {status_code}: {error_body}"
                ) from exc

            raise RuntimeError(
                f"Zoho HTTP error: {status_code}. "
                f"Details: {error_body}"
            ) from exc

        except requests.exceptions.ConnectionError as exc:

            raise RuntimeError(
                "Unable to connect to Zoho QuickML."
            ) from exc

        except requests.exceptions.RequestException as exc:

            raise RuntimeError(
                f"Zoho request failed: {exc}"
            ) from exc

        except ValueError as exc:

            raise RuntimeError(
                f"Invalid JSON response from Zoho: {exc}"
            ) from exc

    # -----------------------------------------
    # 7. LangChain Generation
    # -----------------------------------------

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any
    ) -> ChatResult:

        if stop:
            raise NotImplementedError(
                "Stop sequences are not supported by "
                "this adapter yet."
            )

        # Build request and report its size without logging prompt contents.
        payload = self._build_payload(messages)
        prompt_chars = len(payload["prompt"])
        payload_bytes = len(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        print(
            f"[ZOHO REQUEST] prompt_chars={prompt_chars:,}, "
            f"payload_bytes={payload_bytes:,}"
        )

        # Call Zoho API
        data = self._call_zoho(payload)

        # Extract generated text
        generated_text = self._extract_response(data)

        # Extract token usage
        usage = data.get("usage", {})

        usage_metadata = None

        if usage:
            usage_metadata = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }

        # Create LangChain AIMessage
        ai_message = AIMessage(
            content=generated_text,
            usage_metadata=usage_metadata,
            response_metadata={
                "model_name": data.get("model"),
                "finish_reason": data.get("finish_reason")
            }
        )

        # Return ChatResult
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=ai_message
                )
            ]
        )
