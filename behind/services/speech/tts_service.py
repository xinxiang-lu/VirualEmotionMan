from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class TtsServiceError(RuntimeError):
    pass


class TtsService:
    """TTS facade backed by Doubao cloud TTS, with a local demo fallback."""

    DEFAULT_DOUBAO_BASE_URL = "https://sami.bytedance.com/api/v1/invoke"
    DEFAULT_DOUBAO_LEGACY_BASE_URL = "https://openspeech.bytedance.com/api/v1/tts"
    DEFAULT_DOUBAO_TOKEN_URL = "https://open.volcengineapi.com/?Action=GetToken&Version=2021-07-27"
    DOUBAO_TOKEN_VERSION = "volc-auth-v1"
    DOUBAO_SERVICE = "sami"
    DOUBAO_REGION = "cn-north-1"
    DOUBAO_ALGORITHM = "HMAC-SHA256"
    DOUBAO_REQUEST_TERMINATOR = "request"
    DOUBAO_CONTENT_TYPE = "application/json; charset=utf-8"
    DOUBAO_SUCCESS_CODE = 20000000
    DEFAULT_SPEED = 1.0
    UI_MIN_SPEED = 0.8
    UI_MAX_SPEED = 1.2
    EFFECTIVE_MIN_SPEED = 0.6
    EFFECTIVE_MAX_SPEED = 1.4
    DEFAULT_DOUBAO_AVATAR_VOICES = {
        "": "zh_female_vv_uranus_bigtts",
        "haru": "zh_female_xiaohe_uranus_bigtts",
        "hiyori": "zh_female_vv_uranus_bigtts",
        "soft_female": "zh_female_vv_uranus_bigtts",
        "neutral_light": "zh_female_xiaohe_uranus_bigtts",
        "vivi": "zh_female_vv_uranus_bigtts",
        "xiaohe": "zh_female_xiaohe_uranus_bigtts",
    }

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(config or {})
        self.output_dir = str(self._config("STATIC_AUDIO_DIR", "static/audio"))
        self.url_prefix = str(self._config("STATIC_AUDIO_URL_PREFIX", "/static/audio"))
        self._backend = str(self._config("TTS_BACKEND", "demo")).strip().lower() or "demo"
        self._request_timeout = float(self._config("TTS_REQUEST_TIMEOUT_SECONDS", 60))

        self._doubao_base_url = str(
            self._config(
                "DOUBAO_TTS_BASE_URL",
                self._config("VOLCENGINE_TTS_BASE_URL", self.DEFAULT_DOUBAO_BASE_URL),
            )
        ).strip()
        self._doubao_legacy_base_url = str(
            self._config(
                "DOUBAO_TTS_LEGACY_BASE_URL",
                self._config("VOLCENGINE_TTS_LEGACY_BASE_URL", self.DEFAULT_DOUBAO_LEGACY_BASE_URL),
            )
        ).strip()
        self._doubao_app_id = str(
            self._config("DOUBAO_TTS_APP_ID", self._config("VOLCENGINE_TTS_APP_ID", ""))
        ).strip()
        self._doubao_access_token = str(
            self._config("DOUBAO_TTS_ACCESS_TOKEN", self._config("VOLCENGINE_TTS_ACCESS_TOKEN", ""))
        ).strip()
        self._doubao_app_key = str(
            self._config("DOUBAO_TTS_APP_KEY", self._config("VOLCENGINE_TTS_APP_KEY", ""))
        ).strip()
        self._doubao_token = str(
            self._config("DOUBAO_TTS_TOKEN", self._config("VOLCENGINE_TTS_TOKEN", ""))
        ).strip()
        self._doubao_access_key_id = str(
            self._config(
                "DOUBAO_TTS_ACCESS_KEY_ID",
                self._config("VOLCENGINE_TTS_ACCESS_KEY_ID", self._config("VOLC_ACCESSKEY", "")),
            )
        ).strip()
        self._doubao_secret_access_key = str(
            self._config(
                "DOUBAO_TTS_SECRET_ACCESS_KEY",
                self._config("VOLCENGINE_TTS_SECRET_ACCESS_KEY", self._config("VOLC_SECRETKEY", "")),
            )
        ).strip()
        self._doubao_token_url = str(
            self._config(
                "DOUBAO_TTS_TOKEN_URL",
                self._config("VOLCENGINE_TTS_TOKEN_URL", self.DEFAULT_DOUBAO_TOKEN_URL),
            )
        ).strip()
        self._doubao_speaker = str(
            self._config("DOUBAO_TTS_SPEAKER", self._config("VOLCENGINE_TTS_SPEAKER", "zh_female_qingxin"))
        ).strip() or "zh_female_qingxin"
        self._doubao_cluster = str(
            self._config("DOUBAO_TTS_CLUSTER", self._config("VOLCENGINE_TTS_CLUSTER", "volcano_tts"))
        ).strip() or "volcano_tts"
        self._doubao_voice_type = str(
            self._config(
                "DOUBAO_TTS_VOICE_TYPE",
                self._config("VOLCENGINE_TTS_VOICE_TYPE", "zh_female_vv_uranus_bigtts"),
            )
        ).strip() or "zh_female_vv_uranus_bigtts"
        self._doubao_sample_rate = int(
            self._config("DOUBAO_TTS_SAMPLE_RATE", self._config("VOLCENGINE_TTS_SAMPLE_RATE", 24000))
        )
        self._doubao_enable_timestamp = self._parse_bool(
            self._config(
                "DOUBAO_TTS_ENABLE_TIMESTAMP",
                self._config("VOLCENGINE_TTS_ENABLE_TIMESTAMP", False),
            )
        )
        self._doubao_timeout = float(
            self._config(
                "DOUBAO_TTS_TIMEOUT_SECONDS",
                self._config("VOLCENGINE_TTS_TIMEOUT_SECONDS", self._request_timeout),
            )
        )
        self._doubao_token_expiration_seconds = int(
            self._config(
                "DOUBAO_TTS_TOKEN_EXPIRATION_SECONDS",
                self._config("VOLCENGINE_TTS_TOKEN_EXPIRATION_SECONDS", 3600),
            )
        )
        self._doubao_token_lock = threading.Lock()
        self._doubao_cached_token: Optional[str] = self._doubao_token or None
        self._doubao_cached_token_expires_at: float = 0.0

        if self._backend == "doubao_http":
            if not self._doubao_app_key:
                raise TtsServiceError("Doubao TTS app key is not configured.")
            if not self._doubao_token and (not self._doubao_access_key_id or not self._doubao_secret_access_key):
                raise TtsServiceError("Doubao TTS requires either token or access key credentials.")
            if not self._doubao_base_url:
                raise TtsServiceError("Doubao TTS base URL is not configured.")
        if self._backend == "doubao_legacy_http":
            if not self._doubao_app_id or not self._doubao_access_token:
                raise TtsServiceError("Doubao legacy TTS app ID/access token is not configured.")
            if not self._doubao_legacy_base_url:
                raise TtsServiceError("Doubao legacy TTS base URL is not configured.")

        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def synthesize(self, text: str, voice_code: str = "", speed: float | None = None) -> str:
        clean_text = (text or "").strip()
        if not clean_text:
            raise ValueError("tts text is required")

        filename = f"tts_{uuid.uuid4().hex}.wav"
        output_path = Path(self.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._backend == "doubao_http":
            self._synthesize_with_doubao_http(
                text=clean_text,
                voice_code=voice_code,
                speed=speed,
                output_path=output_path,
            )
        elif self._backend == "doubao_legacy_http":
            self._synthesize_with_doubao_legacy_http(
                text=clean_text,
                voice_code=voice_code,
                speed=speed,
                output_path=output_path,
            )
        else:
            self._write_demo_wav(str(output_path), clean_text)

        return f"{self.url_prefix.rstrip('/')}/{filename}"

    def close(self) -> None:
        return None

    def prewarm(self, text: str = "", voice_code: str = "", speed: float | None = None, force: bool = False) -> dict:
        return {"ok": True, "skipped": True, "elapsed_seconds": 0.0}

    def _synthesize_with_doubao_http(self, text: str, voice_code: str, speed: float | None, output_path: Path) -> None:
        request_payload = {
            "speaker": self._resolve_doubao_speaker(voice_code),
            "text": text,
            "audio_config": {
                "format": "wav",
                "sample_rate": self._doubao_sample_rate,
                "speech_rate": self._resolve_doubao_speech_rate(speed),
            },
        }
        if self._doubao_enable_timestamp:
            request_payload["audio_config"]["enable_timestamp"] = True

        body = {
            "appkey": self._doubao_app_key,
            "token": self._resolve_doubao_token(),
            "namespace": "TTS",
            "payload": json.dumps(request_payload, ensure_ascii=False),
        }
        request = urllib.request.Request(
            self._doubao_base_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        payload = self._post_json(request, "Doubao TTS")

        status_code = int(payload.get("status_code") or 0)
        if status_code != self.DOUBAO_SUCCESS_CODE:
            raise TtsServiceError(
                f"Doubao TTS failed: status_code={status_code}, status_text={payload.get('status_text', '')}"
            )

        self._write_base64_audio(payload.get("data"), output_path, "Doubao TTS")

    def _synthesize_with_doubao_legacy_http(
        self,
        text: str,
        voice_code: str,
        speed: float | None,
        output_path: Path,
    ) -> None:
        request_payload = {
            "app": {
                "appid": self._doubao_app_id,
                "token": self._doubao_access_token,
                "cluster": self._doubao_cluster,
            },
            "user": {"uid": str(uuid.uuid4())},
            "audio": {
                "voice_type": self._resolve_doubao_voice_type(voice_code),
                "encoding": "wav",
                "rate": self._doubao_sample_rate,
                "speed_ratio": self._resolve_doubao_speed_ratio(speed),
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
                "language": "cn",
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }
        request = urllib.request.Request(
            self._doubao_legacy_base_url,
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer;{self._doubao_access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        payload = self._post_json(request, "Doubao legacy TTS")

        status_code = int(payload.get("code") or 0)
        if status_code != 3000:
            raise TtsServiceError(
                f"Doubao legacy TTS failed: code={status_code}, message={payload.get('message', '')}"
            )

        self._write_base64_audio(payload.get("data"), output_path, "Doubao legacy TTS")

    def _post_json(self, request: urllib.request.Request, label: str) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=self._doubao_timeout) as response:
                raw_response = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            raise TtsServiceError(f"{label} HTTP {error.code}: {error_body}") from error
        except urllib.error.URLError as error:
            raise TtsServiceError(f"{label} request failed: {error}") from error

        try:
            return json.loads(raw_response)
        except json.JSONDecodeError as error:
            raise TtsServiceError(f"{label} returned invalid JSON: {raw_response[:200]}") from error

    def _write_base64_audio(self, audio_base64: Any, output_path: Path, label: str) -> None:
        audio_base64 = str(audio_base64 or "").strip()
        if not audio_base64:
            raise TtsServiceError(f"{label} returned empty audio data.")

        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as error:
            raise TtsServiceError(f"{label} returned invalid base64 audio.") from error

        output_path.write_bytes(audio_bytes)

    def _resolve_doubao_speaker(self, voice_code: str) -> str:
        return str(voice_code or "").strip() or self._doubao_speaker

    def _resolve_doubao_voice_type(self, voice_code: str) -> str:
        normalized = str(voice_code or "").strip()
        if normalized in self.DEFAULT_DOUBAO_AVATAR_VOICES:
            return self.DEFAULT_DOUBAO_AVATAR_VOICES[normalized]
        return self._doubao_voice_type

    def _resolve_speed(self, speed: float | None) -> float:
        fallback = self._config("TTS_SPEED", self.DEFAULT_SPEED)
        try:
            numeric = float(fallback if speed is None else speed)
        except (TypeError, ValueError):
            numeric = float(self.DEFAULT_SPEED)

        # UI stores a gentler 0.8-1.2 range; map it to a stronger effective
        # range so the difference is easier to hear in practice.
        if self.UI_MIN_SPEED <= numeric <= self.UI_MAX_SPEED:
            if numeric == self.DEFAULT_SPEED:
                return self.DEFAULT_SPEED
            if numeric < self.DEFAULT_SPEED:
                ratio = (self.DEFAULT_SPEED - numeric) / (self.DEFAULT_SPEED - self.UI_MIN_SPEED)
                effective = self.DEFAULT_SPEED - ratio * (self.DEFAULT_SPEED - self.EFFECTIVE_MIN_SPEED)
            else:
                ratio = (numeric - self.DEFAULT_SPEED) / (self.UI_MAX_SPEED - self.DEFAULT_SPEED)
                effective = self.DEFAULT_SPEED + ratio * (self.EFFECTIVE_MAX_SPEED - self.DEFAULT_SPEED)
            return round(effective, 2)

        return min(self.EFFECTIVE_MAX_SPEED, max(self.EFFECTIVE_MIN_SPEED, numeric))

    def _resolve_doubao_speech_rate(self, speed: float | None) -> int:
        effective_speed = self._resolve_speed(speed)
        return max(-50, min(100, int(round((effective_speed - 1.0) * 100))))

    def _resolve_doubao_speed_ratio(self, speed: float | None) -> float:
        return round(self._resolve_speed(speed), 2)

    def _resolve_doubao_token(self) -> str:
        if self._doubao_token:
            return self._doubao_token

        with self._doubao_token_lock:
            if self._doubao_cached_token and (self._doubao_cached_token_expires_at - time.time()) > 60:
                return self._doubao_cached_token

            token, expires_at = self._fetch_doubao_token()
            self._doubao_cached_token = token
            self._doubao_cached_token_expires_at = expires_at
            return token

    def _fetch_doubao_token(self) -> tuple[str, float]:
        payload = {
            "appkey": self._doubao_app_key,
            "token_version": self.DOUBAO_TOKEN_VERSION,
            "expiration": self._doubao_token_expiration_seconds,
        }
        body_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        request_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        request_date = request_timestamp[:8]
        parsed_url = urllib.parse.urlparse(self._doubao_token_url)
        host = parsed_url.netloc or "open.volcengineapi.com"
        path = parsed_url.path or "/"
        canonical_query = parsed_url.query or "Action=GetToken&Version=2021-07-27"

        canonical_headers = {
            "content-type": self.DOUBAO_CONTENT_TYPE,
            "host": host,
            "x-content-sha256": body_hash,
            "x-date": request_timestamp,
        }
        signed_headers = ";".join(sorted(canonical_headers))
        canonical_header_block = "".join(
            f"{header}:{canonical_headers[header]}\n" for header in sorted(canonical_headers)
        )
        canonical_request = "\n".join(
            [
                "POST",
                path,
                canonical_query,
                canonical_header_block,
                signed_headers,
                body_hash,
            ]
        )
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        credential_scope = "/".join(
            [
                request_date,
                self.DOUBAO_REGION,
                self.DOUBAO_SERVICE,
                self.DOUBAO_REQUEST_TERMINATOR,
            ]
        )
        string_to_sign = "\n".join(
            [
                self.DOUBAO_ALGORITHM,
                request_timestamp,
                credential_scope,
                hashed_canonical_request,
            ]
        )
        signing_key = self._sign_hmac(self._doubao_secret_access_key.encode("utf-8"), request_date)
        signing_key = self._sign_hmac(signing_key, self.DOUBAO_REGION)
        signing_key = self._sign_hmac(signing_key, self.DOUBAO_SERVICE)
        signing_key = self._sign_hmac(signing_key, self.DOUBAO_REQUEST_TERMINATOR)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"{self.DOUBAO_ALGORITHM} "
            f"Credential={self._doubao_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        request = urllib.request.Request(
            self._doubao_token_url,
            data=body_bytes,
            headers={
                "Host": host,
                "Content-Type": self.DOUBAO_CONTENT_TYPE,
                "X-Date": request_timestamp,
                "X-Content-Sha256": body_hash,
                "Authorization": authorization,
            },
            method="POST",
        )
        response_payload = self._post_json(request, "Doubao token")

        status_code = int(response_payload.get("status_code") or 0)
        if status_code != self.DOUBAO_SUCCESS_CODE:
            raise TtsServiceError(
                f"Doubao token failed: status_code={status_code}, status_text={response_payload.get('status_text', '')}"
            )

        token = str(response_payload.get("token") or "").strip()
        if not token:
            raise TtsServiceError("Doubao token response did not include token.")

        expires_at = float(response_payload.get("expires_at") or 0)
        if expires_at <= 0:
            expires_at = time.time() + max(300, self._doubao_token_expiration_seconds)
        return token, expires_at

    def _sign_hmac(self, key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    def _config(self, key: str, default: Any) -> Any:
        return self.config.get(key, os.getenv(key, default))

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _write_demo_wav(self, output_path: str, text: str) -> None:
        sample_rate = 16000
        duration = min(max(0.8, len(text) * 0.05), 4.0)
        total_frames = int(sample_rate * duration)
        frequency = 440.0
        amplitude = 8000

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            for frame_index in range(total_frames):
                envelope = 1.0 - (frame_index / max(total_frames, 1)) * 0.3
                value = int(
                    amplitude
                    * envelope
                    * math.sin(2.0 * math.pi * frequency * frame_index / sample_rate)
                )
                wav_file.writeframesraw(struct.pack("<h", value))
