from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from time import sleep
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from .prompts import build_chat_system_prompt

try:
    import requests
except ImportError:  # pragma: no cover - urllib fallback covers minimal environments
    requests = None

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - optional dependency fallback
    ZhipuAiClient = None


class GLMServiceError(RuntimeError):
    """Raised when GLM service cannot complete a request."""


@dataclass
class GLMStatus:
    configured: bool
    sdk_available: bool
    model: str
    request_count: int
    error_count: int
    last_error: str

    @property
    def enabled(self) -> bool:
        return self.configured and self.sdk_available


class GLMService:
    def __init__(self, app=None) -> None:
        self.app = app
        self._client = None
        self.request_count = 0
        self.error_count = 0
        self.last_error = ""

    def init_app(self, app) -> None:
        self.app = app
        app.extensions["glm_service"] = self

    @property
    def provider(self) -> str:
        return (self.app.config.get("LLM_PROVIDER") or "glm").strip().lower()

    @property
    def configured(self) -> bool:
        if not self.app:
            return False
        return bool(self._provider_config()["api_key"])

    @property
    def sdk_available(self) -> bool:
        return self.provider != "glm" or ZhipuAiClient is not None

    @property
    def enabled(self) -> bool:
        return self.configured and self.sdk_available

    @property
    def model(self) -> str:
        return self._provider_config()["model"]

    def _provider_config(self) -> dict:
        provider = self.provider
        if provider == "qwen":
            return {
                "api_key": self.app.config.get("QWEN_API_KEY"),
                "base_url": self.app.config.get("QWEN_BASE_URL"),
                "model": self.app.config.get("QWEN_MODEL", "qwen-plus"),
            }
        if provider == "deepseek":
            return {
                "api_key": self.app.config.get("DEEPSEEK_API_KEY"),
                "base_url": self.app.config.get("DEEPSEEK_BASE_URL"),
                "model": self.app.config.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            }
        if provider in {"openai_compatible", "openai-compatible", "compatible"}:
            return {
                "api_key": self.app.config.get("OPENAI_COMPATIBLE_API_KEY"),
                "base_url": self.app.config.get("OPENAI_COMPATIBLE_BASE_URL"),
                "model": self.app.config.get("OPENAI_COMPATIBLE_MODEL"),
            }
        return {
            "api_key": self.app.config.get("GLM_API_KEY"),
            "base_url": self.app.config.get("GLM_BASE_URL"),
            "model": self.app.config.get("GLM_MODEL", "glm-4.7-flash"),
        }

    def _get_client(self):
        if not self.enabled:
            if not self.configured:
                raise GLMServiceError(f"{self.provider} API Key 未配置")
            raise GLMServiceError("zai-sdk 未安装，无法调用 GLM")

        if self._client is None:
            config = self._provider_config()
            self._client = ZhipuAiClient(
                api_key=config["api_key"],
                base_url=config["base_url"],
                timeout=self.app.config["GLM_TIMEOUT_SECONDS"],
            )
        return self._client

    def _chat_completions_url(self) -> str:
        base_url = (self._provider_config()["base_url"] or "").rstrip("/")
        if not base_url:
            raise GLMServiceError(f"{self.provider} base_url 未配置")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def build_system_prompt(self, custom_prompt: str = "", rag_context: dict | None = None) -> str:
        return build_chat_system_prompt(self.app, custom_prompt, rag_context=rag_context)

    def _is_rate_limit_error(self, error: Exception) -> bool:
        message = str(error)
        return "429" in message or "Rate limit" in message or '"code":"1302"' in message or "'code': '1302'" in message

    def _generate_text(
        self,
        payload_messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        retry_attempts = max(1, int(self.app.config.get("GLM_RETRY_ATTEMPTS", 1)))
        backoff_seconds = float(self.app.config.get("GLM_RETRY_BACKOFF_SECONDS", 1.5))
        thinking_type = (self.app.config.get("GLM_THINKING_TYPE") or "").strip()
        last_error = None

        for attempt in range(retry_attempts):
            try:
                if self.provider == "glm":
                    response = self._generate_text_zhipu(payload_messages, temperature=temperature, max_tokens=max_tokens, thinking_type=thinking_type)
                else:
                    response = self._generate_text_openai_compatible(payload_messages, temperature=temperature, max_tokens=max_tokens)
                self.request_count += 1
                self.last_error = ""
                return response
            except Exception as error:  # pragma: no cover - depends on external API
                last_error = error
                if self._is_rate_limit_error(error) and attempt < retry_attempts - 1:
                    sleep(backoff_seconds * (2**attempt))
                    continue
                break

        self.request_count += 1
        self.error_count += 1
        self.last_error = str(last_error)

        if last_error is not None and self._is_rate_limit_error(last_error):
            raise GLMServiceError(f"{self.provider} 请求频率受限，稍后再试: {last_error}") from last_error
        raise GLMServiceError(f"{self.provider} 调用失败: {last_error}") from last_error

    def _generate_text_zhipu(
        self,
        payload_messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking_type: str = "",
    ) -> str:
        client = self._get_client()
        request_kwargs = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": self.app.config["GLM_TEMPERATURE"] if temperature is None else temperature,
            "max_tokens": self.app.config["GLM_MAX_TOKENS"] if max_tokens is None else max_tokens,
        }
        if thinking_type:
            request_kwargs["thinking"] = {"type": thinking_type}
        response = client.chat.completions.create(**request_kwargs)
        return self._extract_text(response)

    def _generate_text_openai_compatible(
        self,
        payload_messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if not self.enabled:
            raise GLMServiceError(f"{self.provider} 未配置或不可用")
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": self.app.config["GLM_TEMPERATURE"] if temperature is None else temperature,
            "max_tokens": self.app.config["GLM_MAX_TOKENS"] if max_tokens is None else max_tokens,
        }
        response_payload = self._post_openai_compatible(payload)

        choices = response_payload.get("choices") or []
        if not choices:
            raise GLMServiceError(f"{self.provider} 返回内容为空")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)
        text = str(content).strip()
        if not text:
            raise GLMServiceError(f"{self.provider} 返回文本为空")
        return text

    def _post_openai_compatible(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self._provider_config()['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = self.app.config["GLM_TIMEOUT_SECONDS"]
        url = self._chat_completions_url()
        last_error: Exception | None = None

        if requests is not None:
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as error:
                status_code = error.response.status_code if error.response is not None else "unknown"
                detail = error.response.text if error.response is not None else str(error)
                raise GLMServiceError(f"HTTP {status_code}: {detail}") from error
            except requests.RequestException as error:
                last_error = error
            except ValueError as error:
                raise GLMServiceError("响应不是合法 JSON") from error

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            raise GLMServiceError(f"HTTP {error.code}: {detail}") from error
        except URLError as error:
            last_error = error
        except ValueError as error:
            raise GLMServiceError("响应不是合法 JSON") from error

        if os.name == "nt":
            try:
                return self._post_openai_compatible_with_curl(url, payload, headers, timeout)
            except GLMServiceError as error:
                last_error = error

        raise GLMServiceError(str(last_error)) from last_error

    def _post_openai_compatible_with_curl(
        self,
        url: str,
        payload: dict,
        headers: dict,
        timeout: int | float,
    ) -> dict:
        payload_file = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="ascii") as file:
                json.dump(payload, file, ensure_ascii=True)
                payload_file = file.name

            cmd = [
                "curl.exe",
                "-sS",
                "--max-time",
                str(int(timeout)),
                "-X",
                "POST",
                url,
                "-H",
                "Content-Type: application/json",
                "-H",
                f"Authorization: {headers['Authorization']}",
                "--data-binary",
                f"@{payload_file}",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=float(timeout) + 5,
                check=False,
            )
            if result.returncode != 0:
                raise GLMServiceError(result.stderr.strip() or f"curl exited with {result.returncode}")
            response_payload = json.loads(result.stdout)
            if "error" in response_payload:
                raise GLMServiceError(json.dumps(response_payload["error"], ensure_ascii=False))
            return response_payload
        except FileNotFoundError as error:
            raise GLMServiceError("curl.exe 不可用") from error
        except subprocess.TimeoutExpired as error:
            raise GLMServiceError("curl 请求超时") from error
        except ValueError as error:
            raise GLMServiceError("响应不是合法 JSON") from error
        finally:
            if payload_file:
                try:
                    os.unlink(payload_file)
                except OSError:
                    pass

    def generate_text(
        self,
        messages: list[dict],
        *,
        system_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload_messages = [{"role": "system", "content": system_prompt}, *messages]
        return self._generate_text(
            payload_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def generate_reply(
        self,
        messages: list[dict],
        custom_prompt: str = "",
        rag_context: dict | None = None,
    ) -> str:
        return self.generate_text(
            messages=messages,
            system_prompt=self.build_system_prompt(custom_prompt, rag_context=rag_context),
        )

    def _extract_text(self, response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise GLMServiceError("GLM 返回内容为空")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    text_parts.append(item.get("text", ""))
                else:
                    text_parts.append(getattr(item, "text", ""))
            content = "".join(text_parts)

        text = (content or "").strip()
        if not text:
            raise GLMServiceError("GLM 返回文本为空")
        return text

    def status(self) -> GLMStatus:
        return GLMStatus(
            configured=self.configured,
            sdk_available=self.sdk_available,
            model=self.model,
            request_count=self.request_count,
            error_count=self.error_count,
            last_error=self.last_error,
        )
