"""Local smoke and batch-size benchmark commands for the embedded bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from backend.schemas.modeling import PreparedJobV2
from backend.services.model_runtime import model_runtime


def golden_job() -> PreparedJobV2:
    path = Path(__file__).parents[1] / "model_bundles" / "jedi-ranking-v1"
    return PreparedJobV2.model_validate_json(
        (path / "golden_input.json").read_text(encoding="utf-8")
    )


def smoke() -> dict:
    runtime = model_runtime.warmup()
    result = model_runtime.score(
        [golden_job()],
        batch_id="local-smoke-batch",
        processing_run_id="local-smoke-run",
        model_version_id="local-smoke-model",
    )
    return {
        "runtime": runtime.model_dump(mode="json", by_alias=True),
        "result": result.model_dump(mode="json", by_alias=True),
    }


def benchmark() -> dict:
    base = golden_job()
    model_runtime.warmup()
    measurements: list[dict] = []
    for size in (1, 25, 100, 500):
        rows = [
            base.model_copy(
                update={
                    "job_id": f"benchmark-job-{index:03d}",
                    "code": f"BENCH-{index:03d}",
                }
            )
            for index in range(size)
        ]
        started = perf_counter()
        response = model_runtime.score(
            rows,
            batch_id=f"benchmark-{size}",
            processing_run_id=f"benchmark-run-{size}",
            model_version_id="benchmark-model",
        )
        measurements.append(
            {
                "batchSize": size,
                "wallMs": round((perf_counter() - started) * 1000.0, 3),
                "stageTimingsMs": response.timings_ms.model_dump(by_alias=True),
                "outputCount": len(response.results),
            }
        )
    return {"benchmarks": measurements}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("smoke", "benchmark"))
    args = parser.parse_args()
    print(json.dumps(smoke() if args.action == "smoke" else benchmark(), indent=2))


if __name__ == "__main__":
    main()
