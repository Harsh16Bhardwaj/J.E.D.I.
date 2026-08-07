"""Trusted, immutable model-bundle loading and embedded batch inference."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy  # noqa: E402
import sklearn  # noqa: E402
import xgboost  # noqa: E402

from backend.config import get_settings
from backend.schemas.modeling import PreparedJobV2
from backend.schemas.scoring import (  # noqa: E402
    ModelRuntimeHealth,
    ScoreResponse,
    ScoreResult,
    ScoreTimings,
)
from backend.services.model_features import (  # noqa: E402
    FEATURE_SCHEMA_HASH,
    FEATURE_SCHEMA_VERSION,
    STACKED_SCORE_FEATURES,
    build_model_features,
    feature_schema_document,
)


class ModelRuntimeError(RuntimeError):
    """A safe model error that API and orchestration layers can persist."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class LoadedBundle:
    path: Path
    manifest: dict[str, Any]
    preference_pipeline: Any
    classifier_pipeline: Any
    model_load_ms: float
    smoke_test_ms: float


def _sha256(path: Path) -> str:
    if path.suffix.casefold() == ".json":
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        canonical = normalized.replace(b"\n", b"\r\n")
        return hashlib.sha256(canonical).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clip_scores(values: np.ndarray, targets: list[str]) -> np.ndarray:
    output = np.asarray(values, dtype=float).copy()
    if output.ndim != 2 or output.shape[1] != len(targets):
        raise ModelRuntimeError("INVALID_MODEL_OUTPUT", "Ridge output shape is invalid")
    for index, target in enumerate(targets):
        high = 8.0 if target == "salary_profile_fit_score" else 5.0
        output[:, index] = np.clip(output[:, index], 0.0, high)
    if not np.isfinite(output).all():
        raise ModelRuntimeError("INVALID_MODEL_OUTPUT", "Ridge output is non-finite")
    return output


def _append_scores(frame: pd.DataFrame, scores: np.ndarray) -> pd.DataFrame:
    output = frame.copy()
    for index, column in enumerate(STACKED_SCORE_FEATURES):
        output[column] = scores[:, index]
    return output


class EmbeddedModelRuntime:
    """Process-global lazy loader reused while a serverless instance is warm."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = "UNINITIALIZED"
        self._bundle: LoadedBundle | None = None
        self._error_code: str | None = None

    @staticmethod
    def _bundle_path() -> Path:
        configured = Path(get_settings().model_bundle_root)
        root = (
            configured
            if configured.is_absolute()
            else Path(__file__).parents[1] / configured
        )
        return root / "jedi-ranking-v1"

    def _verify_manifest(self, path: Path) -> dict[str, Any]:
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            raise ModelRuntimeError(
                "MODEL_ARTIFACT_MISSING", "Model manifest is missing"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelRuntimeError(
                "MODEL_MANIFEST_INVALID", "Model manifest is invalid"
            ) from exc
        required = {
            "modelVersion",
            "artifactHash",
            "featureSchemaVersion",
            "featureSchemaHash",
            "requestContractVersion",
            "responseContractVersion",
            "rankingStrategy",
            "decisionThreshold",
            "scoreTargets",
            "scoreWeights",
            "artifacts",
            "runtime",
        }
        if required - manifest.keys():
            raise ModelRuntimeError(
                "MODEL_MANIFEST_INVALID", "Model manifest is incomplete"
            )
        if (
            manifest["featureSchemaVersion"] != FEATURE_SCHEMA_VERSION
            or manifest["featureSchemaHash"] != FEATURE_SCHEMA_HASH
        ):
            raise ModelRuntimeError(
                "FEATURE_SCHEMA_MISMATCH", "Model feature contract is incompatible"
            )
        try:
            bundled_schema = json.loads(
                (path / "feature_schema.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelRuntimeError(
                "FEATURE_SCHEMA_MISMATCH", "Bundled feature schema is invalid"
            ) from exc
        if bundled_schema != feature_schema_document():
            raise ModelRuntimeError(
                "FEATURE_SCHEMA_MISMATCH", "Bundled feature names or order differ"
            )
        if (
            manifest["requestContractVersion"] != "score-request-v1"
            or manifest["responseContractVersion"] != "score-response-v1"
        ):
            raise ModelRuntimeError(
                "MODEL_CONTRACT_MISMATCH", "Model HTTP contract is incompatible"
            )
        for filename, expected in manifest["artifacts"].items():
            artifact = path / filename
            if not artifact.is_file():
                raise ModelRuntimeError(
                    "MODEL_ARTIFACT_MISSING",
                    f"Required artifact is missing: {filename}",
                )
            if _sha256(artifact) != expected:
                raise ModelRuntimeError(
                    "MODEL_CHECKSUM_MISMATCH", f"Artifact checksum failed: {filename}"
                )
        aggregate = hashlib.sha256(
            json.dumps(manifest["artifacts"], sort_keys=True).encode()
        ).hexdigest()
        if aggregate != manifest["artifactHash"]:
            raise ModelRuntimeError("MODEL_CHECKSUM_MISMATCH", "Bundle checksum failed")
        current = {
            "python": ".".join(platform.python_version_tuple()[:2]),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikitLearn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "joblib": joblib.__version__,
        }
        if current != manifest["runtime"]:
            raise ModelRuntimeError(
                "MODEL_DEPENDENCY_MISMATCH", "Pinned model dependencies do not match"
            )
        return manifest

    def _smoke_test(
        self, path: Path, manifest: dict[str, Any], preference: Any, classifier: Any
    ) -> float:
        started = perf_counter()
        try:
            prepared = PreparedJobV2.model_validate_json(
                (path / "golden_input.json").read_text(encoding="utf-8")
            )
            expected = json.loads(
                (path / "golden_output.json").read_text(encoding="utf-8")
            )
            frame = pd.DataFrame(build_model_features([prepared]))
            scores = _clip_scores(preference.predict(frame), manifest["scoreTargets"])
            probability = float(
                classifier.predict_proba(_append_scores(frame, scores))[0, 1]
            )
        except ModelRuntimeError:
            raise
        except Exception as exc:
            raise ModelRuntimeError(
                "MODEL_GOLDEN_FAILED", "Golden prediction could not run"
            ) from exc
        actual = [*scores[0].tolist(), probability]
        wanted = [*expected["componentScores"].values(), expected["applyProbability"]]
        if not np.allclose(actual, wanted, rtol=1e-6, atol=1e-7):
            raise ModelRuntimeError(
                "MODEL_GOLDEN_MISMATCH", "Golden prediction does not match"
            )
        return (perf_counter() - started) * 1000.0

    def load(self) -> tuple[LoadedBundle, bool, float]:
        if self._bundle is not None:
            return self._bundle, False, 0.0
        with self._lock:
            if self._bundle is not None:
                return self._bundle, False, 0.0
            self._state = "LOADING"
            started = perf_counter()
            try:
                path = self._bundle_path()
                manifest = self._verify_manifest(path)
                preference = joblib.load(path / "preference_pipeline.joblib")
                classifier = joblib.load(path / "classifier_pipeline.joblib")
                smoke_ms = self._smoke_test(path, manifest, preference, classifier)
                load_ms = (perf_counter() - started) * 1000.0
                self._bundle = LoadedBundle(
                    path=path,
                    manifest=manifest,
                    preference_pipeline=preference,
                    classifier_pipeline=classifier,
                    model_load_ms=load_ms,
                    smoke_test_ms=smoke_ms,
                )
                self._state = "READY"
                self._error_code = None
                return self._bundle, True, load_ms
            except ModelRuntimeError as exc:
                self._state = "FAILED"
                self._error_code = exc.code
                raise
            except Exception as exc:
                self._state = "FAILED"
                self._error_code = "MODEL_LOAD_FAILED"
                raise ModelRuntimeError(
                    "MODEL_LOAD_FAILED", "Model bundle could not be loaded"
                ) from exc

    def health(self) -> ModelRuntimeHealth:
        bundle = self._bundle
        manifest = bundle.manifest if bundle else {}
        return ModelRuntimeHealth(
            state=self._state,
            ready=bundle is not None,
            model_version=manifest.get("modelVersion"),
            feature_schema_version=manifest.get("featureSchemaVersion"),
            request_contract_version=manifest.get("requestContractVersion"),
            response_contract_version=manifest.get("responseContractVersion"),
            artifact_hash=manifest.get("artifactHash"),
            cold_start=None if bundle is None else False,
            model_load_ms=bundle.model_load_ms if bundle else None,
            smoke_test_ms=bundle.smoke_test_ms if bundle else None,
            error_code=self._error_code,
        )

    def warmup(self) -> ModelRuntimeHealth:
        bundle, cold, _ = self.load()
        response = self.health()
        return response.model_copy(
            update={"cold_start": cold, "model_load_ms": bundle.model_load_ms}
        )

    def score(
        self,
        prepared: list[PreparedJobV2],
        *,
        batch_id: str,
        processing_run_id: str,
        model_version_id: str,
        expected_artifact_hash: str | None = None,
        expected_bundle_version: str | None = None,
    ) -> ScoreResponse:
        total_started = perf_counter()
        bundle, cold_start, load_ms = self.load()
        manifest = bundle.manifest
        if (
            expected_artifact_hash
            and expected_artifact_hash != manifest["artifactHash"]
        ):
            raise ModelRuntimeError(
                "MODEL_VERSION_MISMATCH", "Run is pinned to a different artifact"
            )
        if (
            expected_bundle_version
            and expected_bundle_version != manifest["modelVersion"]
        ):
            raise ModelRuntimeError(
                "MODEL_VERSION_MISMATCH", "Run is pinned to a different bundle"
            )
        feature_started = perf_counter()
        try:
            frame = pd.DataFrame(build_model_features(prepared))
        except Exception as exc:
            raise ModelRuntimeError(
                "INVALID_FEATURE_INPUT", "Prepared feature input is invalid"
            ) from exc
        feature_ms = (perf_counter() - feature_started) * 1000.0

        preference_started = perf_counter()
        try:
            component_values = _clip_scores(
                bundle.preference_pipeline.predict(frame), manifest["scoreTargets"]
            )
        except ModelRuntimeError:
            raise
        except Exception as exc:
            raise ModelRuntimeError(
                "PREFERENCE_SCORING_FAILED", "Preference scoring failed", retryable=True
            ) from exc
        weights = manifest["scoreWeights"]
        ranking_values = np.zeros(len(prepared), dtype=float)
        for index, target in enumerate(manifest["scoreTargets"]):
            high = 8.0 if target == "salary_profile_fit_score" else 5.0
            ranking_values += component_values[:, index] / high * float(weights[target])
        ranking_values = np.clip(ranking_values * 100.0, 0.0, 100.0)
        preference_ms = (perf_counter() - preference_started) * 1000.0

        classification_started = perf_counter()
        try:
            probabilities = np.asarray(
                bundle.classifier_pipeline.predict_proba(
                    _append_scores(frame, component_values)
                )[:, 1],
                dtype=float,
            )
        except Exception as exc:
            raise ModelRuntimeError(
                "CLASSIFICATION_FAILED", "Apply classification failed", retryable=True
            ) from exc
        classification_ms = (perf_counter() - classification_started) * 1000.0

        validation_started = perf_counter()
        threshold = float(manifest["decisionThreshold"])
        if not np.isfinite(probabilities).all() or np.any(
            (probabilities < 0) | (probabilities > 1)
        ):
            raise ModelRuntimeError(
                "INVALID_MODEL_OUTPUT", "Classifier probabilities are invalid"
            )
        decisions = probabilities >= threshold
        indexes = list(range(len(prepared)))
        indexes.sort(
            key=lambda index: (
                2
                if prepared[index].can_apply_now is False
                else (0 if decisions[index] else 1),
                -ranking_values[index],
                -probabilities[index],
                prepared[index].job_id,
            )
        )
        results: list[ScoreResult] = []
        for rank, index in enumerate(indexes, start=1):
            row = prepared[index]
            warnings = (
                ["APPLICATION_AVAILABILITY_UNKNOWN"]
                if row.can_apply_now is None
                else []
            )
            component_scores = {
                target: float(component_values[index, target_index])
                for target_index, target in enumerate(manifest["scoreTargets"])
            }
            results.append(
                ScoreResult(
                    job_id=row.job_id,
                    rank=rank,
                    ranking_score=float(ranking_values[index]),
                    jedi_preference_score=float(ranking_values[index]),
                    apply_probability=float(probabilities[index]),
                    model_apply_decision=bool(decisions[index]),
                    apply_recommendation=bool(
                        decisions[index] and row.can_apply_now is not False
                    ),
                    component_scores=component_scores,
                    warnings=warnings,
                )
            )
        if {item.job_id for item in results} != {
            item.job_id for item in prepared
        } or len(results) != len(prepared):
            raise ModelRuntimeError(
                "INVALID_MODEL_OUTPUT", "Output does not cover the exact input job set"
            )
        validation_ms = (perf_counter() - validation_started) * 1000.0
        total_ms = (perf_counter() - total_started) * 1000.0
        return ScoreResponse(
            batch_id=batch_id,
            processing_run_id=processing_run_id,
            model_version_id=model_version_id,
            artifact_hash=manifest["artifactHash"],
            decision_threshold=threshold,
            cold_start=cold_start,
            timings_ms=ScoreTimings(
                model_load=load_ms,
                feature_build=feature_ms,
                preference_scoring=preference_ms,
                classification=classification_ms,
                validation=validation_ms,
                total=total_ms,
            ),
            results=results,
        )

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state = "UNINITIALIZED"
            self._bundle = None
            self._error_code = None


model_runtime = EmbeddedModelRuntime()
