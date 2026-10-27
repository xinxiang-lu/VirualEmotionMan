from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from contextlib import redirect_stdout
from typing import Any, Dict, List

TOKEN_RE = re.compile(r"<\|([^|]+)\|>")


def build_model():
    device = os.getenv("SENSEVOICE_DEVICE", "cuda:0").strip() or "cuda:0"
    model_name = os.getenv("SENSEVOICE_MODEL", "iic/SenseVoiceSmall").strip() or "iic/SenseVoiceSmall"
    vad_model = os.getenv("SENSEVOICE_VAD_MODEL", "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch").strip()
    disable_update = os.getenv("SENSEVOICE_DISABLE_UPDATE", "1").lower() in {"1", "true", "yes", "on"}

    kwargs = {
        "model": model_name,
        "trust_remote_code": False,
        "device": device,
        "disable_update": disable_update,
    }
    if vad_model:
        kwargs["vad_model"] = vad_model
        kwargs["vad_kwargs"] = {"max_single_segment_time": 30000}
    with redirect_stdout(sys.stderr):
        from funasr import AutoModel

        return AutoModel(**kwargs)


def parse_meta(raw_text: str) -> Dict[str, Any]:
    tokens = TOKEN_RE.findall(raw_text or "")
    return {
        "tokens": tokens,
        "language": tokens[0] if len(tokens) >= 1 else "",
        "emotion": tokens[1] if len(tokens) >= 2 else "",
        "audio_type": tokens[2] if len(tokens) >= 3 else "",
        "itn": "withitn" in tokens,
    }


def build_segments(results: List[dict]) -> List[dict]:
    with redirect_stdout(sys.stderr):
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

    segments = []
    for index, item in enumerate(results):
        raw_text = item.get("text", "")
        text = rich_transcription_postprocess(raw_text).strip()
        if not text:
            continue
        segments.append(
            {
                "index": index,
                "text": text,
                "start": item.get("start"),
                "end": item.get("end"),
                "confidence": item.get("confidence"),
            }
        )
    return segments


def handle_transcribe(model, payload: dict) -> dict:
    audio_path = payload["audio_path"]
    started_at = time.perf_counter()
    with redirect_stdout(sys.stderr):
        results = model.generate(
            input=audio_path,
            cache={},
            language=payload.get("language") or "auto",
            use_itn=bool(payload.get("use_itn", True)),
            batch_size_s=int(payload.get("batch_size_s", 60)),
            merge_vad=bool(payload.get("merge_vad", True)),
            merge_length_s=int(payload.get("merge_length_s", 15)),
        )

    segments = build_segments(results)
    text = " ".join(item["text"] for item in segments).strip()
    meta = parse_meta(results[0].get("text", "") if results else "")
    confidence_values = [item["confidence"] for item in segments if item.get("confidence") is not None]
    confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0.0
    elapsed_seconds = round(time.perf_counter() - started_at, 4)

    return {
        "ok": True,
        "text": text,
        "confidence": confidence,
        "segments": segments,
        "raw_result": {
            "backend": "sensevoice_small",
            "model": os.getenv("SENSEVOICE_MODEL", "iic/SenseVoiceSmall"),
            "device": os.getenv("SENSEVOICE_DEVICE", "cuda:0"),
            "language": meta["language"],
            "emotion": meta["emotion"],
            "audio_type": meta["audio_type"],
            "itn": meta["itn"],
            "hotword_ignored": payload.get("hotword") or "",
            "segment_count": len(segments),
            "elapsed_seconds": elapsed_seconds,
            "results": results,
        },
    }


def main() -> int:
    try:
        model = build_model()
    except Exception as error:
        sys.stdout.write(json.dumps({"type": "error", "error": str(error)}, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        traceback.print_exc(file=sys.stderr)
        return 1

    ready_payload = {
        "type": "ready",
        "backend": "sensevoice_small",
        "model": os.getenv("SENSEVOICE_MODEL", "iic/SenseVoiceSmall"),
        "device": os.getenv("SENSEVOICE_DEVICE", "cuda:0"),
        "model_path": getattr(model, "model_path", ""),
    }
    sys.stdout.write(json.dumps(ready_payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if payload.get("type") == "shutdown":
                break
            if payload.get("type") != "transcribe":
                raise ValueError(f"Unsupported request type: {payload.get('type')}")
            response = handle_transcribe(model, payload)
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            response = {"ok": False, "error": str(error)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
