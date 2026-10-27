from __future__ import annotations

import importlib.util
import json
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from flask import current_app

from ..extensions import db
from ..models import MultimodalAnalysis, User


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class MultimodalServiceError(RuntimeError):
    """Raised when multimodal storage or analysis cannot be completed."""


class MultimodalServiceUnavailableError(MultimodalServiceError):
    """Raised when optional multimodal dependencies are not available."""


@dataclass
class StoredMedia:
    audio_path: Optional[Path]
    video_path: Optional[Path]
    audio_url: Optional[str]
    video_url: Optional[str]


@dataclass
class MediaAlignment:
    model_fps: int
    model_seq_len: int
    source_fps: int
    source_frame_count: int
    clip_end_frame: Optional[int]
    source_duration_sec: float


class MultimodalService:
    AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".webm", ".ogg", ".opus"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    ASR_MODULE = "behind.services.speech.asr_service"
    DIGITAL_HUMAN_MODULES = (
        "live2d_service.src.reaction_generation_service",
        "live2d_service.src.multimodal_summary",
        "live2d_service.src.render_adapter",
        "live2d_service.src.haru_adapter",
    )

    def __init__(self, app=None) -> None:
        self.app = app
        self._reaction_service = None
        self._haru_adapter = None
        self._summarizer = None
        self._asr_service = None
        self._render_adapter = None
        self._capability_cache: dict[str, tuple[bool, str]] = {}

    def init_app(self, app) -> None:
        self.app = app
        app.extensions["multimodal_service"] = self

    def capability_status(self) -> dict:
        asr_available, asr_reason = self._probe_module(self.ASR_MODULE)

        digital_results = [self._probe_module(module_name) for module_name in self.DIGITAL_HUMAN_MODULES]
        digital_available = all(item[0] for item in digital_results)
        digital_reasons = [item[1] for item in digital_results if item[1]]
        digital_reason = "; ".join(digital_reasons)

        multimodal_available = asr_available and digital_available
        multimodal_reason = ""
        if not multimodal_available:
            multimodal_reason = "; ".join(reason for reason in [asr_reason, digital_reason] if reason)

        return {
            "asr": {
                "available": asr_available,
                "reason": asr_reason,
            },
            "digital_human": {
                "available": digital_available,
                "reason": digital_reason,
            },
            "multimodal": {
                "available": multimodal_available,
                "reason": multimodal_reason,
            },
        }

    def process_message_media(
        self,
        user_id: int,
        conversation_id: int,
        message_id: int,
        content_text: str,
        audio_file=None,
        video_file=None,
    ) -> dict:
        self._ensure_media_capabilities(audio_file=audio_file, video_file=video_file)

        stored = self.save_message_media(
            conversation_id=conversation_id,
            message_id=message_id,
            audio_file=audio_file,
            video_file=video_file,
        )
        identity_payload = self._resolve_identity_payload(user_id)
        transcript = self._transcribe_audio(stored.audio_path) if stored.audio_path else None
        message_text = self._build_message_text(content_text, transcript, stored)
        assistant_text = self._build_assistant_text(content_text, transcript)

        summary_payload = None
        if stored.audio_path and stored.video_path:
            try:
                prediction_result, summary_payload = self._run_full_multimodal_analysis(
                    conversation_id=conversation_id,
                    message_id=message_id,
                    stored=stored,
                    transcript=transcript,
                    identity_payload=identity_payload,
                )
                prediction_path = self._save_prediction_artifact(message_id, prediction_result)
                summary_path = self._save_summary_artifact(message_id, summary_payload)
                self._upsert_analysis_record(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    summary_payload=summary_payload,
                    prediction_artifact_path=prediction_path,
                    summary_artifact_path=summary_path,
                    has_prediction=True,
                )
                assistant_text = self._build_assistant_text(content_text, transcript, summary_payload=summary_payload)
            except MultimodalServiceUnavailableError:
                raise
            except Exception as error:  # pragma: no cover - runtime integration path
                current_app.logger.warning("Multimodal analysis failed for message %s: %s", message_id, error)
                summary_payload = self._build_error_summary(
                    message_id=message_id,
                    stored=stored,
                    transcript=transcript,
                    error=error,
                    identity_payload=identity_payload,
                )
                summary_path = self._save_summary_artifact(message_id, summary_payload)
                self._upsert_analysis_record(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    summary_payload=summary_payload,
                    summary_artifact_path=summary_path,
                    has_prediction=False,
                )
        elif stored.audio_path or stored.video_path:
            summary_payload = self._build_partial_summary(
                message_id=message_id,
                stored=stored,
                transcript=transcript,
                identity_payload=identity_payload,
            )
            summary_path = self._save_summary_artifact(message_id, summary_payload)
            self._upsert_analysis_record(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                summary_payload=summary_payload,
                summary_artifact_path=summary_path,
                has_prediction=False,
            )

        return {
            "message_text": message_text,
            "assistant_text": assistant_text,
            "audio_url": stored.audio_url,
            "video_url": stored.video_url,
            "multimodal_summary": summary_payload,
        }

    def save_message_media(self, conversation_id: int, message_id: int, audio_file=None, video_file=None) -> StoredMedia:
        message_dir = self._message_dir(conversation_id, message_id)
        message_dir.mkdir(parents=True, exist_ok=True)

        audio_path = None
        video_path = None
        audio_url = None
        video_url = None

        if audio_file and getattr(audio_file, "filename", ""):
            audio_suffix = self._validated_suffix(audio_file.filename, self.AUDIO_EXTENSIONS, ".wav")
            audio_path = message_dir / f"audio{audio_suffix}"
            audio_file.save(audio_path)
            audio_url = f"/api/conversations/{conversation_id}/messages/{message_id}/media/audio"

        if video_file and getattr(video_file, "filename", ""):
            video_suffix = self._validated_suffix(video_file.filename, self.VIDEO_EXTENSIONS, ".mp4")
            video_path = message_dir / f"video{video_suffix}"
            video_file.save(video_path)
            video_url = f"/api/conversations/{conversation_id}/messages/{message_id}/media/video"

        return StoredMedia(
            audio_path=audio_path,
            video_path=video_path,
            audio_url=audio_url,
            video_url=video_url,
        )

    def get_message_media_path(self, conversation_id: int, message_id: int, kind: str) -> Optional[Path]:
        message_dir = self._message_dir(conversation_id, message_id)
        if not message_dir.exists():
            return None

        prefix = "audio" if kind == "audio" else "video"
        candidates = sorted(message_dir.glob(f"{prefix}.*"))
        return candidates[0] if candidates else None

    def get_message_media_mimetype(self, path: Path) -> str:
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"

    def load_message_summary(self, message_id: int) -> Optional[dict]:
        record = MultimodalAnalysis.query.filter_by(message_id=message_id).first()
        if record is not None:
            payload = record.get_summary_payload()
            if payload:
                if "identity" not in payload:
                    payload["identity"] = self._resolve_identity_payload(record.user_id)
                payload.pop("rendering", None)
                return payload

        summary_path = self._summary_path(message_id)
        if not summary_path.exists():
            return None
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if "identity" not in payload and record is not None:
                payload["identity"] = self._resolve_identity_payload(record.user_id)
            payload.pop("rendering", None)
            return payload
        except Exception:  # pragma: no cover - defensive
            current_app.logger.warning("Failed to read multimodal summary for message %s", message_id)
            return None

    def load_full_analysis(self, message_id: int) -> Optional[dict]:
        record = MultimodalAnalysis.query.filter_by(message_id=message_id).first()
        summary = self.load_message_summary(message_id)
        prediction_path = (
            Path(record.prediction_artifact_path)
            if record and record.prediction_artifact_path
            else self._prediction_path(message_id)
        )
        if summary is None and not prediction_path.exists():
            return None
        if not prediction_path.exists():
            return {"summary": summary, "prediction_result": None}
        if summary is not None:
            summary.pop("rendering", None)

        loaded = np.load(prediction_path, allow_pickle=True)
        prediction_result = {
            "meta": {
                "sample_id": summary.get("sample_id") if summary else f"chat/message/{message_id}",
                "fps": int(loaded["fps"][0]),
                "seq_len": int(loaded["seq_len"][0]),
                "candidate_num": int(loaded["candidate_num"][0]),
            },
            "conditioning_summary": json.loads(str(loaded["conditioning_summary_json"][0])),
            "prediction_emotion": loaded["prediction_emotion"].tolist(),
            "prediction_3dmm": loaded["prediction_3dmm"].tolist(),
            "selected_candidate": int(loaded["selected_candidate"][0]),
            "candidate_scores": loaded["candidate_scores"].tolist(),
        }
        prediction_result["render_adapter_payload"] = self._ensure_render_adapter().convert(prediction_result)
        live2d_payload = self._ensure_haru_adapter().convert(prediction_result)
        prediction_result["live2d_adapter_payload"] = live2d_payload
        prediction_result["haru_adapter_payload"] = live2d_payload
        return {
            "summary": summary,
            "prediction_result": prediction_result,
        }

    def _run_full_multimodal_analysis(
        self,
        conversation_id: int,
        message_id: int,
        stored: StoredMedia,
        transcript: Optional[dict],
        identity_payload: Optional[dict],
    ) -> tuple[dict, dict]:
        alignment = self._inspect_media(stored.video_path, stored.audio_path)
        fps = alignment.model_fps
        seq_len = alignment.model_seq_len
        sample = {
            "meta": {
                "sample_id": f"chat/{conversation_id}/message/{message_id}",
                "fps": fps,
                "seq_len": seq_len,
                "candidate_num": int(self._config("DIGITAL_HUMAN_CANDIDATE_NUM", 3)),
            },
            "speaker_text": transcript.get("text", "") if transcript else "",
            "source_paths": {
                "audio_path": str(stored.audio_path),
                "video_path": str(stored.video_path),
                "clip_start": 0,
                "clip_end": alignment.clip_end_frame,
            },
        }
        prediction_result = self._ensure_reaction_service().predict(sample)
        summary = self._ensure_summarizer().summarize(sample, prediction_result)
        live2d_payload = prediction_result.get("live2d_adapter_payload") or prediction_result.get("haru_adapter_payload")
        if not live2d_payload:
            live2d_payload = self._ensure_haru_adapter().convert(prediction_result)
        summary_payload = {
            "analysis_mode": "full_multimodal",
            "message_id": message_id,
            "sample_id": summary["sample_id"],
            "selected_candidate": summary["selected_candidate"],
            "transcript_text": transcript.get("text", "") if transcript else "",
            "transcript_confidence": transcript.get("confidence") if transcript else None,
            "overall_summary": summary["overall_summary"],
            "supporting_statistics": summary["supporting_statistics"],
            "key_segments": summary["key_segments"],
            "event_tags": summary["event_tags"],
            "prediction_meta": {
                "fps": fps,
                "seq_len": seq_len,
                "source_fps": alignment.source_fps,
                "source_frame_count": alignment.source_frame_count,
                "source_duration_sec": round(alignment.source_duration_sec, 4),
                "candidate_num": sample["meta"]["candidate_num"],
                "selected_candidate": prediction_result["selected_candidate"],
                "candidate_scores": prediction_result["candidate_scores"],
                "backend": prediction_result["conditioning_summary"].get("backend", ""),
                "input_mode": prediction_result["conditioning_summary"].get("input_mode", ""),
            },
            "media": {
                "has_audio": bool(stored.audio_url),
                "has_video": bool(stored.video_url),
                "audio_url": stored.audio_url,
                "video_url": stored.video_url,
            },
            "identity": identity_payload,
            "live2d_mapping": self._ensure_haru_adapter().build_summary(live2d_payload),
            "haru_mapping": self._ensure_haru_adapter().build_summary(live2d_payload),
        }
        return prediction_result, summary_payload

    def _build_partial_summary(
        self,
        message_id: int,
        stored: StoredMedia,
        transcript: Optional[dict],
        identity_payload: Optional[dict],
    ) -> dict:
        tags = []
        if stored.audio_url:
            tags.append("已保存音频输入")
        if stored.video_url:
            tags.append("已保存视频输入")
        if stored.audio_url and not stored.video_url:
            tags.append("缺少视频，未生成25/58维特征")
        if stored.video_url and not stored.audio_url:
            tags.append("缺少音频，未生成25/58维特征")
        if transcript and transcript.get("text"):
            tags.append("已完成语音转写")

        return {
            "analysis_mode": "partial_media",
            "message_id": message_id,
            "sample_id": f"chat/message/{message_id}",
            "selected_candidate": None,
            "transcript_text": transcript.get("text", "") if transcript else "",
            "transcript_confidence": transcript.get("confidence") if transcript else None,
            "overall_summary": None,
            "supporting_statistics": None,
            "key_segments": [],
            "event_tags": tags,
            "prediction_meta": None,
            "media": {
                "has_audio": bool(stored.audio_url),
                "has_video": bool(stored.video_url),
                "audio_url": stored.audio_url,
                "video_url": stored.video_url,
            },
            "identity": identity_payload,
        }

    def _build_error_summary(
        self,
        message_id: int,
        stored: StoredMedia,
        transcript: Optional[dict],
        error: Exception,
        identity_payload: Optional[dict],
    ) -> dict:
        return {
            "analysis_mode": "analysis_error",
            "message_id": message_id,
            "sample_id": f"chat/message/{message_id}",
            "selected_candidate": None,
            "transcript_text": transcript.get("text", "") if transcript else "",
            "transcript_confidence": transcript.get("confidence") if transcript else None,
            "overall_summary": None,
            "supporting_statistics": None,
            "key_segments": [],
            "event_tags": ["原始模态已保存", "多模态分析失败"],
            "prediction_meta": None,
            "media": {
                "has_audio": bool(stored.audio_url),
                "has_video": bool(stored.video_url),
                "audio_url": stored.audio_url,
                "video_url": stored.video_url,
            },
            "identity": identity_payload,
            "error": str(error),
        }

    def _save_prediction_artifact(self, message_id: int, prediction_result: dict) -> Path:
        prediction_path = self._prediction_path(message_id)
        prediction_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            prediction_path,
            prediction_emotion=np.array(prediction_result["prediction_emotion"], dtype=np.float32),
            prediction_3dmm=np.array(prediction_result["prediction_3dmm"], dtype=np.float32),
            selected_candidate=np.array([prediction_result["selected_candidate"]], dtype=np.int32),
            candidate_scores=np.array(prediction_result["candidate_scores"], dtype=np.float32),
            seq_len=np.array([prediction_result["meta"]["seq_len"]], dtype=np.int32),
            fps=np.array([prediction_result["meta"]["fps"]], dtype=np.int32),
            candidate_num=np.array([prediction_result["meta"]["candidate_num"]], dtype=np.int32),
            conditioning_summary_json=np.array(
                [json.dumps(prediction_result.get("conditioning_summary", {}), ensure_ascii=False)],
                dtype=object,
            ),
        )
        return prediction_path.resolve()

    def _save_summary_artifact(self, message_id: int, summary_payload: dict) -> Path:
        summary_path = self._summary_path(message_id)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary_path.resolve()

    def _upsert_analysis_record(
        self,
        user_id: int,
        conversation_id: int,
        message_id: int,
        summary_payload: dict,
        prediction_artifact_path: Optional[Path] = None,
        summary_artifact_path: Optional[Path] = None,
        has_prediction: bool = False,
    ) -> None:
        record = MultimodalAnalysis.query.filter_by(message_id=message_id).first()
        if record is None:
            record = MultimodalAnalysis(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            db.session.add(record)

        record.analysis_mode = summary_payload.get("analysis_mode") or "partial_media"
        record.selected_candidate = summary_payload.get("selected_candidate")
        record.transcript_text = summary_payload.get("transcript_text") or ""
        record.transcript_confidence = summary_payload.get("transcript_confidence")
        record.set_summary_payload(summary_payload)
        record.has_prediction = has_prediction
        record.prediction_artifact_path = (
            str(prediction_artifact_path) if prediction_artifact_path is not None else record.prediction_artifact_path
        )
        record.summary_artifact_path = (
            str(summary_artifact_path) if summary_artifact_path is not None else record.summary_artifact_path
        )

    def _transcribe_audio(self, audio_path: Path) -> Optional[dict]:
        try:
            return self._ensure_asr_service().transcribe(str(audio_path))
        except MultimodalServiceError:
            raise
        except Exception as error:  # pragma: no cover - runtime integration path
            current_app.logger.warning("ASR failed for %s: %s", audio_path, error)
            return None

    def _build_message_text(self, content_text: str, transcript: Optional[dict], stored: StoredMedia) -> str:
        content_text = (content_text or "").strip()
        if content_text:
            return content_text
        transcript_text = (transcript or {}).get("text", "").strip()
        if transcript_text:
            return transcript_text
        parts = []
        if stored.audio_url:
            parts.append("[已上传音频]")
        if stored.video_url:
            parts.append("[已上传视频]")
        return " ".join(parts)

    def _build_assistant_text(self, content_text: str, transcript: Optional[dict], summary_payload: Optional[dict] = None) -> str:
        typed_text = (content_text or "").strip()
        transcript_text = (transcript or {}).get("text", "").strip()
        parts = []
        if typed_text:
            parts.append(f"用户文本：{typed_text}")
        if transcript_text and transcript_text != typed_text:
            parts.append(f"语音转写：{transcript_text}")
        if summary_payload and summary_payload.get("analysis_mode") == "full_multimodal":
            parts.append(self._build_multimodal_context(summary_payload))
        elif summary_payload and summary_payload.get("analysis_mode") == "partial_media":
            parts.append("用户附带了原始音频或视频，但当前缺少完整音视频配对，未生成25维和58维特征。")
        elif summary_payload and summary_payload.get("analysis_mode") == "analysis_error":
            parts.append("用户附带了原始音频和视频，但多模态分析暂时失败。")
        if not parts:
            return "用户发送了一条新消息，请给出温和、具体、陪伴式的回应。"
        return "\n\n".join(parts)

    def _build_multimodal_context(self, summary_payload: dict) -> str:
        overall = summary_payload.get("overall_summary") or {}
        event_tags = summary_payload.get("event_tags") or []
        key_segments = summary_payload.get("key_segments") or []
        lines = [
            "本轮多模态分析摘要：",
            f"- 时长: {overall.get('duration_sec', 0)} 秒",
            f"- 音频能量: {overall.get('audio_energy_level', 'unknown')}",
            f"- 音频波动: {overall.get('audio_variation', 'unknown')}",
            f"- valence 趋势: {overall.get('valence_trend', 'unknown')}",
            f"- arousal 水平: {overall.get('arousal_level', 'unknown')}",
            f"- 主导表情: {overall.get('dominant_expression', 'unknown')}",
            f"- 头姿趋势: {overall.get('head_pose_trend', 'unknown')}",
        ]
        if event_tags:
            lines.append(f"- 事件标签: {', '.join(event_tags[:6])}")
        if key_segments:
            segment_text = "; ".join(
                f"{item.get('start_sec', 0)}-{item.get('end_sec', 0)}秒:{item.get('state', '')}"
                for item in key_segments[:3]
            )
            lines.append(f"- 关键片段: {segment_text}")
        return "\n".join(lines)

    def _inspect_media(self, video_path: Path, audio_path: Optional[Path]) -> MediaAlignment:
        model_fps = int(self._config("DIGITAL_HUMAN_DEFAULT_FPS", 25))
        source_fps = model_fps
        source_frame_count = 0
        source_duration_sec = 0.0
        try:
            import cv2

            capture = cv2.VideoCapture(str(video_path))
            if capture.isOpened():
                detected_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
                frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if detected_fps > 0:
                    source_fps = max(1, int(round(detected_fps)))
                if frame_count > 0:
                    source_frame_count = frame_count
                    if detected_fps > 0:
                        source_duration_sec = frame_count / detected_fps
            capture.release()
        except Exception as error:  # pragma: no cover - runtime integration path
            current_app.logger.warning("Video inspection failed for %s: %s", video_path, error)

        if source_duration_sec <= 0 and audio_path:
            try:
                import librosa

                source_duration_sec = float(librosa.get_duration(path=str(audio_path)) or 0.0)
            except Exception as error:  # pragma: no cover - runtime integration path
                current_app.logger.warning("Audio inspection failed for %s: %s", audio_path, error)

        max_seq_len = int(self._config("DIGITAL_HUMAN_MAX_SEQ_LEN", 751))
        model_seq_len = int(round(source_duration_sec * model_fps)) if source_duration_sec > 0 else max_seq_len
        model_seq_len = max(1, min(model_seq_len or max_seq_len, max_seq_len))

        clip_end_frame = source_frame_count or None
        if clip_end_frame and source_duration_sec > 0:
            max_duration_sec = model_seq_len / max(model_fps, 1)
            if max_duration_sec < source_duration_sec:
                clip_end_frame = max(1, min(source_frame_count, int(round(max_duration_sec * max(source_fps, 1)))))

        return MediaAlignment(
            model_fps=model_fps,
            model_seq_len=model_seq_len,
            source_fps=source_fps,
            source_frame_count=source_frame_count,
            clip_end_frame=clip_end_frame,
            source_duration_sec=source_duration_sec,
        )

    def _validated_suffix(self, filename: str, allowed_extensions: set[str], default_suffix: str) -> str:
        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            return default_suffix
        if suffix not in allowed_extensions:
            allowed_text = ", ".join(sorted(allowed_extensions))
            raise MultimodalServiceError(f"Unsupported media type: {suffix}. Allowed: {allowed_text}")
        return suffix

    def _message_dir(self, conversation_id: int, message_id: int) -> Path:
        return Path(self._config("CHAT_MEDIA_ROOT")) / f"conversation_{conversation_id}" / f"message_{message_id}"

    def _analysis_dir(self) -> Path:
        return Path(self._config("MULTIMODAL_ANALYSIS_ROOT"))

    def _resolve_identity_payload(self, user_id: int) -> Optional[dict]:
        identity_service = current_app.extensions.get("digital_human_identity_service")
        if identity_service is None:
            return None

        user = User.query.get(user_id)
        selected_code = user.settings.digital_human_code if user and user.settings else ""
        identity = identity_service.get_selected_identity(selected_code)
        if identity is None:
            return None

        return {
            "code": identity["code"],
            "label": identity["label"],
            "portrait_url": identity["portrait_url"],
            "model_path": identity["model_url"],
        }

    def _summary_path(self, message_id: int) -> Path:
        return self._analysis_dir() / f"message_{message_id}_summary.json"

    def _prediction_path(self, message_id: int) -> Path:
        return self._analysis_dir() / f"message_{message_id}_prediction.npz"

    def _config(self, key: str, default=None):
        return current_app.config.get(key, default)

    def _probe_module(self, module_name: str) -> tuple[bool, str]:
        cached = self._capability_cache.get(module_name)
        if cached is not None:
            return cached

        try:
            available = importlib.util.find_spec(module_name) is not None
        except Exception as error:  # pragma: no cover - defensive
            result = (False, f"{type(error).__name__}: {error}")
        else:
            result = (available, "" if available else f"missing module: {module_name}")

        self._capability_cache[module_name] = result
        return result

    def _ensure_media_capabilities(self, *, audio_file=None, video_file=None) -> None:
        status = self.capability_status()
        if audio_file and not status["asr"]["available"]:
            raise MultimodalServiceUnavailableError("当前环境未启用语音输入能力，请补充 behind/services/speech 后重试。")
        if video_file and not status["digital_human"]["available"]:
            raise MultimodalServiceUnavailableError("当前环境未启用视频/多模态分析能力，请补充 live2d_service 后重试。")

    def _ensure_reaction_service(self):
        if self._reaction_service is None:
            try:
                from live2d_service.src.reaction_generation_service import ReactionGenerationService
            except ImportError as error:
                raise MultimodalServiceUnavailableError(
                    "当前环境未启用视频/多模态分析能力，请补充 live2d_service 后重试。"
                ) from error

            config = {}
            checkpoint_path = self._config("DIGITAL_HUMAN_CHECKPOINT_PATH")
            if checkpoint_path:
                checkpoint_file = Path(checkpoint_path)
                if checkpoint_file.exists():
                    config["checkpoint_path"] = str(checkpoint_file)
            device = (self._config("DIGITAL_HUMAN_DEVICE") or "").strip()
            if device:
                config["device"] = device
            config["emotion_ema_alpha"] = float(self._config("DIGITAL_HUMAN_EMOTION_EMA_ALPHA", 0.4))
            config["speaker_emotion_blend"] = float(self._config("DIGITAL_HUMAN_SPEAKER_EMOTION_BLEND", 0.01))
            config["speaker_emotion_shift"] = int(self._config("DIGITAL_HUMAN_SPEAKER_EMOTION_SHIFT", 2))
            config["prediction_emotion_shift"] = int(self._config("DIGITAL_HUMAN_PREDICTION_EMOTION_SHIFT", -4))
            config["emotion_au_gain"] = float(self._config("DIGITAL_HUMAN_EMOTION_AU_GAIN", 1.3))
            config["emotion_va_gain"] = float(self._config("DIGITAL_HUMAN_EMOTION_VA_GAIN", 1.2))
            config["emotion_exp_temperature"] = float(self._config("DIGITAL_HUMAN_EMOTION_EXP_TEMPERATURE", 0.8))
            config["candidate_emotion_spread"] = float(self._config("DIGITAL_HUMAN_CANDIDATE_EMOTION_SPREAD", 2.0))
            self._reaction_service = ReactionGenerationService(config=config)
        return self._reaction_service

    def _ensure_summarizer(self):
        if self._summarizer is None:
            try:
                from live2d_service.src.multimodal_summary import MultimodalStateSummarizer
            except ImportError as error:
                raise MultimodalServiceUnavailableError(
                    "当前环境未启用视频/多模态分析能力，请补充 live2d_service 后重试。"
                ) from error

            self._summarizer = MultimodalStateSummarizer(
                window_seconds=float(self._config("DIGITAL_HUMAN_SUMMARY_WINDOW_SECONDS", 3.0)),
                max_segments=int(self._config("DIGITAL_HUMAN_SUMMARY_SEGMENTS", 3)),
            )
        return self._summarizer

    def _ensure_asr_service(self):
        if self._asr_service is None:
            try:
                from behind.services.speech.asr_service import AsrService
            except ImportError as error:
                raise MultimodalServiceUnavailableError(
                    "当前环境未启用语音输入能力，请补充 behind/services/speech 后重试。"
                ) from error

            self._asr_service = AsrService(current_app.config)
        return self._asr_service

    def _ensure_render_adapter(self):
        if self._render_adapter is None:
            try:
                from live2d_service.src.render_adapter import RenderAdapter
            except ImportError as error:
                raise MultimodalServiceUnavailableError(
                    "当前环境未启用视频/多模态分析能力，请补充 live2d_service 后重试。"
                ) from error

            self._render_adapter = RenderAdapter()
        return self._render_adapter

    def _ensure_haru_adapter(self):
        if self._haru_adapter is None:
            try:
                from live2d_service.src.haru_adapter import HaruParameterAdapter
            except ImportError as error:
                raise MultimodalServiceUnavailableError(
                    "当前环境未启用视频/多模态分析能力，请补充 live2d_service 后重试。"
                ) from error

            self._haru_adapter = HaruParameterAdapter()
        return self._haru_adapter
