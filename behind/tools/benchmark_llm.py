from __future__ import annotations

import argparse
import statistics
import time

from behind.app import create_app
from behind.services.ai import GLMServiceError


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the configured LLM provider.")
    parser.add_argument("--provider", choices=["glm", "qwen", "deepseek", "openai_compatible"], default=None)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--prompt", default="我这次数学考试没考好，晚上一直想，睡不着。")
    args = parser.parse_args()

    app = create_app("default")
    if args.provider:
        app.config["LLM_PROVIDER"] = args.provider

    with app.app_context():
        service = app.extensions["glm_service"]
        print(f"provider={service.provider} model={service.model} enabled={service.enabled}")
        samples = []
        for index in range(max(1, args.rounds)):
            start = time.perf_counter()
            try:
                text = service.generate_text(
                    messages=[{"role": "user", "content": args.prompt}],
                    system_prompt="你是心陪陪，请用中文温和回应用户，先共情，再给一个很小的下一步。",
                    temperature=0.2,
                    max_tokens=220,
                )
            except GLMServiceError as error:
                elapsed = time.perf_counter() - start
                print(f"#{index + 1} ERROR {elapsed:.2f}s {error}")
                continue
            elapsed = time.perf_counter() - start
            samples.append(elapsed)
            print(f"#{index + 1} {elapsed:.2f}s {text[:120].replace(chr(10), ' ')}")

        if samples:
            print(f"avg={statistics.mean(samples):.2f}s min={min(samples):.2f}s max={max(samples):.2f}s")


if __name__ == "__main__":
    main()
