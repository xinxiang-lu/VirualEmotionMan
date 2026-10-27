from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class ASRServiceError(RuntimeError):
    pass


class AsrService:
    """ASR facade with a demo fallback and a SenseVoice worker backend."""

    DEFAULT_RAFT39_PYTHON = "<ASR_PYTHON_PATH>"

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(config or {})
        self._backend = str(self._config("ASR_BACKEND", "demo")).strip().lower() or "demo"
        self._runtime_python = self._resolve_runtime_python()
        self._worker_process: Optional[subprocess.Popen[str]] = None
        self._worker_lock = threading.Lock()
        self._worker_script = Path(__file__).with_name("sensevoice_worker.py")
        self._worker_log_path = Path(self._config("ASR_WORKER_LOG_PATH", str(Path(__file__).resolve().parent.parent / "sensevoice_worker.log")))
        self._startup_timeout = float(self._config("ASR_STARTUP_TIMEOUT_SECONDS", 600))
        self._request_timeout = float(self._config("ASR_REQUEST_TIMEOUT_SECONDS", 180))
        atexit.register(self.close)

    def transcribe(self, audio_path: str, hotword: Optional[str] = None) -> dict:
        path = Path(audio_path or "sample.wav").expanduser()
        if not path.is_absolute():
            path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        if self._backend == "sensevoice_small":
            return self._transcribe_with_worker(path, hotword=hotword)

        text = self._infer_text(path, hotword=hotword)
        segments = self._build_segments(text)
        return {
            "text": text,
            "confidence": 0.91 if text else 0.0,
            "segments": segments,
            "raw_result": {
                "source": str(path),
                "hotword": hotword or "",
                "segment_count": len(segments),
                "backend": "demo",
            },
        }

    def close(self) -> None:
        process = self._worker_process
        self._worker_process = None
        if process is None:
            return

        try:
            if process.stdin:
                process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                process.stdin.flush()
        except Exception:
            pass

        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()

    def _transcribe_with_worker(self, audio_path: Path, hotword: Optional[str] = None) -> dict:
        payload = {
            "type": "transcribe",
            "audio_path": str(audio_path),
            "hotword": hotword or "",
            "language": self._config("ASR_LANGUAGE", "auto"),
            "use_itn": bool(self._config("ASR_USE_ITN", True)),
            "batch_size_s": int(self._config("ASR_BATCH_SIZE_S", 60)),
            "merge_vad": bool(self._config("ASR_MERGE_VAD", True)),
            "merge_length_s": int(self._config("ASR_MERGE_LENGTH_S", 15)),
        }

        response = self._exchange(payload)
        if not response.get("ok"):
            message = response.get("error") or "SenseVoice worker failed."
            raise ASRServiceError(message)

        return {
            "text": response.get("text", ""),
            "confidence": response.get("confidence") or 0.0,
            "segments": response.get("segments") or [],
            "raw_result": response.get("raw_result") or {},
        }

    def _exchange(self, payload: dict) -> dict:
        with self._worker_lock:
            process = self._ensure_worker()
            if process.stdin is None or process.stdout is None:
                raise ASRServiceError("SenseVoice worker stdio is unavailable.")

            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
            return self._read_json_payload(process.stdout, self._request_timeout, "SenseVoice worker returned no response.")

    def _ensure_worker(self) -> subprocess.Popen[str]:
        process = self._worker_process
        if process is not None and process.poll() is None:
            return process

        if self._runtime_python is None:
            raise ASRServiceError("ASR runtime python is not configured.")
        if not self._worker_script.exists():
            raise ASRServiceError(f"SenseVoice worker script not found: {self._worker_script}")

        self._worker_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = self._worker_log_path.open("a", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "SENSEVOICE_MODEL": str(self._config("ASR_MODEL_NAME", "iic/SenseVoiceSmall")),
                "SENSEVOICE_DEVICE": str(self._config("ASR_DEVICE", "cuda:0")),
                "SENSEVOICE_VAD_MODEL": str(self._config("ASR_VAD_MODEL_NAME", "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch")),
                "SENSEVOICE_DISABLE_UPDATE": "1" if self._config("ASR_DISABLE_UPDATE", True) else "0",
                "PYTHONIOENCODING": "utf-8",
            }
        )

        process = subprocess.Popen(
            [self._runtime_python, "-u", str(self._worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        self._worker_process = process

        ready_payload = self._read_json_payload(
            process.stdout,
            self._startup_timeout,
            f"SenseVoice worker did not become ready. Check log: {self._worker_log_path}",
        )
        if ready_payload.get("type") != "ready":
            raise ASRServiceError(ready_payload.get("error") or "SenseVoice worker failed to start.")
        return process

    def _read_json_payload(self, stream, timeout_seconds: float, empty_message: str) -> dict:
        while True:
            line = self._readline_with_timeout(stream, timeout_seconds)
            if not line:
                raise ASRServiceError(empty_message)
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def _readline_with_timeout(self, stream, timeout_seconds: float) -> str:
        holder: Dict[str, str] = {}
        error_holder: Dict[str, Exception] = {}

        def target():
            try:
                holder["line"] = stream.readline()
            except Exception as error:  # pragma: no cover - defensive
                error_holder["error"] = error

        reader = threading.Thread(target=target, daemon=True)
        reader.start()
        reader.join(timeout_seconds)
        if reader.is_alive():
            self.close()
            raise ASRServiceError(f"SenseVoice worker timed out after {timeout_seconds:.0f}s.")
        if "error" in error_holder:
            raise ASRServiceError(str(error_holder["error"]))
        return holder.get("line", "")

    def _resolve_runtime_python(self) -> Optional[str]:
        configured = str(self._config("ASR_RUNTIME_PYTHON", "")).strip()
        candidates = [configured, self.DEFAULT_RAFT39_PYTHON]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None

    def _config(self, key: str, default: Any) -> Any:
        return self.config.get(key, os.getenv(key, default))

    def _infer_text(self, audio_path: Path, hotword: Optional[str] = None) -> str:
        seed = audio_path.stem.replace("_", " ").replace("-", " ").strip().lower()

        if "sleep" in seed or "insomnia" in seed:
            return "最近失眠有点严重，整个人都很疲惫。"
        if "job" in seed or "interview" in seed:
            return "最近找工作压力很大，总担心自己表现不好。"
        if "study" in seed or "exam" in seed:
            return "最近学习压力有点大，心里一直很紧。"
        if "lonely" in seed:
            return "最近总觉得有些孤独，不太想和别人说话。"
        if hotword:
            return f"我最近一直在想{hotword}这件事。"
        return "最近有点累，也有点迷茫，想找个人聊聊。"

    def _build_segments(self, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []

        return [
            {
                "index": 0,
                "text": text,
                "start": 0,
                "end": max(800, len(text) * 180),
                "confidence": 0.91,
            }
        ]
