
import os
import json
import threading
from pathlib import Path
from typing import Any, ClassVar

import requests
from dotenv import load_dotenv, set_key
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

    # Shared lock across instances
    _token_refresh_lock: ClassVar[threading.Lock] = threading.Lock()

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
    # 6. Refresh Zoho Access Token
    # -----------------------------------------

    def _refresh_access_token(self) -> str:
        """
        Generate a new Zoho access token using the refresh token.
        Update the running application and project .env file.
        """

        with self._token_refresh_lock:

            refresh_token = os.getenv("ZOHO_REFRESH_TOKEN")
            client_id = os.getenv("ZOHO_CLIENT_ID")
            client_secret = os.getenv("ZOHO_CLIENT_SECRET")

            oauth_url = os.getenv(
                "ZOHO_OAUTH_URL",
                "https://accounts.zoho.in/oauth/v2/token"
            )

            if not all([
                refresh_token,
                client_id,
                client_secret
            ]):
                raise RuntimeError(
                    "Zoho OAuth refresh configuration is incomplete."
                )

            try:

                response = requests.post(
                    oauth_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret
                    },
                    timeout=self.request_timeout
                )

                response.raise_for_status()

                token_data = response.json()

                new_access_token = token_data.get("access_token")

                if not new_access_token:
                    raise RuntimeError(
                        "Zoho did not return an access token."
                    )

                # Find project root .env file
                env_path = Path(__file__).resolve().parents[2] / ".env"

                # Update .env without overwriting other variables
                set_key(
                    str(env_path),
                    "ZOHO_ACCESS_TOKEN",
                    new_access_token
                )

                # Update running process
                os.environ["ZOHO_ACCESS_TOKEN"] = new_access_token

                # IMPORTANT: Keep the field as SecretStr
                self.access_token = SecretStr(new_access_token)

                print(
                    "[ZOHO AUTH] Access token refreshed successfully."
                )

                return new_access_token

            except requests.exceptions.RequestException as exc:

                raise RuntimeError(
                    f"Unable to refresh Zoho access token: {exc}"
                ) from exc

    # -----------------------------------------
    # 7. HTTP Request to Zoho
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

            # Access token expired or invalid
            if response.status_code == 401:

                print(
                    "[ZOHO AUTH] Access token expired. Refreshing..."
                )

                self._refresh_access_token()

                # Retry original request once with new token
                response = requests.post(
                    self.url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=self.request_timeout
                )

                print("[ZOHO AUTH] Retried request with new token.")

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
                    "Zoho rejected the prompt because it exceeds "
                    "the endpoint's maximum input length. "
                    f"HTTP {status_code}: {error_body}"
                ) from exc

            if status_code == 401:

                raise RuntimeError(
                    "Zoho authentication failed even after "
                    "refreshing the access token. Check OAuth credentials."
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
    # 8. LangChain Generation
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

        # Build request and report size without logging prompt contents
        payload = self._build_payload(messages)

        prompt_chars = len(payload["prompt"])

        payload_bytes = len(
            json.dumps(
                payload,
                ensure_ascii=False
            ).encode("utf-8")
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
