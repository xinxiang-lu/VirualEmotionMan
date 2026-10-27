from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from pathlib import Path

import editdistance
import jieba
from datasets import Audio, load_dataset

from behind.services.speech.sensevoice_worker import build_model, build_segments


NORMALIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def normalize_text(text: str) -> str:
    text = NORMALIZE_RE.sub("", text or "")
    return text.strip().lower()


def compute_rate(distance: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return distance / total


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SenseVoice-Small on a labeled subset.")
    parser.add_argument("--dataset", default="AudioLLMs/aishell_1_zh_test")
    parser.add_argument("--split", default="test[:30]")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--use-itn", dest="use_itn", action="store_true")
    parser.add_argument("--no-use-itn", dest="use_itn", action="store_false")
    parser.set_defaults(use_itn=False)
    parser.add_argument("--use-vad", dest="use_vad", action="store_true")
    parser.add_argument("--no-use-vad", dest="use_vad", action="store_false")
    parser.set_defaults(use_vad=True)
    parser.add_argument("--merge-vad", dest="merge_vad", action="store_true")
    parser.add_argument("--no-merge-vad", dest="merge_vad", action="store_false")
    parser.set_defaults(merge_vad=True)
    parser.add_argument("--batch-size-s", type=int, default=60)
    parser.add_argument("--merge-length-s", type=int, default=15)
    parser.add_argument("--show-samples", type=int, default=5)
    args = parser.parse_args()

    os.environ["SENSEVOICE_DEVICE"] = args.device
    os.environ["SENSEVOICE_VAD_MODEL"] = (
        "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch" if args.use_vad else ""
    )
    dataset = load_dataset(args.dataset, split=args.split).cast_column("context", Audio(decode=False))
    model = build_model()

    total_char_distance = 0
    total_char_count = 0
    total_word_distance = 0
    total_word_count = 0
    total_sentence_errors = 0
    total_infer_seconds = 0.0
    processed_count = 0
    cases = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for index, sample in enumerate(dataset):
            audio_blob = sample["context"]["bytes"]
            reference = normalize_text(sample["answer"])
            if not audio_blob or not reference:
                continue

            audio_path = temp_root / f"sample_{index}.wav"
            audio_path.write_bytes(audio_blob)

            started_at = time.perf_counter()
            generate_kwargs = {
                "input": str(audio_path),
                "cache": {},
                "language": args.language,
                "use_itn": args.use_itn,
            }
            if args.use_vad:
                generate_kwargs.update(
                    {
                        "batch_size_s": args.batch_size_s,
                        "merge_vad": args.merge_vad,
                        "merge_length_s": args.merge_length_s,
                    }
                )
            results = model.generate(**generate_kwargs)
            infer_seconds = time.perf_counter() - started_at

            hypothesis = normalize_text("".join(item["text"] for item in build_segments(results)))
            ref_chars = list(reference)
            hyp_chars = list(hypothesis)
            ref_words = jieba.lcut(reference)
            hyp_words = jieba.lcut(hypothesis)

            total_char_distance += editdistance.eval(ref_chars, hyp_chars)
            total_char_count += len(ref_chars)
            total_word_distance += editdistance.eval(ref_words, hyp_words)
            total_word_count += len(ref_words)
            total_sentence_errors += int(reference != hypothesis)
            total_infer_seconds += infer_seconds
            processed_count += 1

            if len(cases) < args.show_samples:
                cases.append(
                    {
                        "index": index,
                        "reference": reference,
                        "hypothesis": hypothesis,
                        "infer_seconds": round(infer_seconds, 4),
                    }
                )

    sample_count = max(processed_count, 1)
    summary = {
        "dataset": args.dataset,
        "split": args.split,
        "language": args.language,
        "use_itn": args.use_itn,
        "use_vad": args.use_vad,
        "merge_vad": args.merge_vad if args.use_vad else False,
        "batch_size_s": args.batch_size_s if args.use_vad else None,
        "merge_length_s": args.merge_length_s if args.use_vad else None,
        "sample_count": processed_count,
        "total_char_distance": total_char_distance,
        "total_char_count": total_char_count,
        "total_word_distance": total_word_distance,
        "total_word_count": total_word_count,
        "total_sentence_errors": total_sentence_errors,
        "total_infer_seconds": round(total_infer_seconds, 4),
        "cer": round(compute_rate(total_char_distance, total_char_count), 4),
        "wer_jieba": round(compute_rate(total_word_distance, total_word_count), 4),
        "ser": round(total_sentence_errors / sample_count, 4),
        "avg_infer_seconds": round(total_infer_seconds / sample_count, 4),
        "samples": cases,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
