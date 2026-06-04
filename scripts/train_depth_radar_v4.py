from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - runtime dependency guard
    lgb = None  # type: ignore[assignment]

from deep6.ml.depth_radar.causal_features import CAUSAL_FEATURE_NAMES
from deep6.ml.depth_radar.episode import InteractionOutcome, WallIntent
from deep6.ml.depth_radar.episode_labeler import EpisodeLabeler


INTENT_CLASS_NAMES = [
    WallIntent.PASSIVE_REAL.value,
    WallIntent.SPOOF_LIKE.value,
    WallIntent.RESERVE_REFRESH.value,
    WallIntent.MIGRATORY.value,
]
INTENT_LABEL_TO_ID = {name: idx for idx, name in enumerate(INTENT_CLASS_NAMES)}

INTERACTION_CLASS_NAMES = [
    InteractionOutcome.BOUNCE.value,
    InteractionOutcome.BREAK.value,
    InteractionOutcome.CHURN.value,
]
INTERACTION_LABEL_TO_ID = {name: idx for idx, name in enumerate(INTERACTION_CLASS_NAMES)}

BASE_MULTICLASS_PARAMS: dict[str, Any] = {
    "objective": "multiclass",
    "metric": "multi_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
}


def require_lightgbm() -> None:
    if lgb is None:
        raise RuntimeError("lightgbm is not installed. Install it with `pip install lightgbm`.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train DepthRadar V4 intent + interaction models")
    parser.add_argument("--input", required=True, help="Path to Databento DBN/ZST MBO file")
    parser.add_argument("--output-dir", required=True, help="Directory for parquet outputs and trained models")
    parser.add_argument("--min-wall-size", type=int, default=50, help="Minimum wall size for episode labeling")
    parser.add_argument("--snapshot-interval", type=int, default=2, help="Snapshot interval in seconds")
    parser.add_argument(
        "--skip-label",
        action="store_true",
        help="Skip episode labeling and reuse existing parquet files in output-dir",
    )
    parser.add_argument(
        "--label-only",
        action="store_true",
        help="Run labeling only, save parquet files, then exit",
    )
    return parser.parse_args()


def load_or_label_data(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    episodes_path = output_dir / "episodes.parquet"
    snapshots_path = output_dir / "snapshots.parquet"
    touches_path = output_dir / "touches.parquet"

    if args.skip_label:
        missing = [path.name for path in (episodes_path, snapshots_path, touches_path) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "--skip-label requested, but required parquet files are missing: " + ", ".join(missing)
            )
        print(f"[label] Skipping Stage 1 and loading parquet files from {output_dir}")
        return (
            pd.read_parquet(episodes_path),
            pd.read_parquet(snapshots_path),
            pd.read_parquet(touches_path),
        )

    print(
        "[label] Stage 1: labeling MBO file "
        f"(min_wall_size={args.min_wall_size}, snapshot_interval={args.snapshot_interval})"
    )
    labeler = EpisodeLabeler(
        min_wall_size=args.min_wall_size,
        snapshot_interval_sec=args.snapshot_interval,
    )
    episodes_df, snapshots_df, touches_df = labeler.process_mbo_file(args.input)
    episodes_df.to_parquet(episodes_path, index=False)
    snapshots_df.to_parquet(snapshots_path, index=False)
    touches_df.to_parquet(touches_path, index=False)
    print(
        "[label] Wrote "
        f"episodes={len(episodes_df)} snapshots={len(snapshots_df)} touches={len(touches_df)} to {output_dir}"
    )
    return episodes_df, snapshots_df, touches_df


def ensure_required_columns(frame: pd.DataFrame, required: list[str], frame_name: str) -> None:
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(f"{frame_name} is missing required columns: {missing}")


def sort_temporally(frame: pd.DataFrame, timestamp_col: str, frame_name: str) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True)
    if timestamps.isna().all():
        raise ValueError(f"{frame_name} has no parseable timestamps in column `{timestamp_col}`.")
    return frame.assign(_sort_ts=timestamps).sort_values("_sort_ts", kind="stable").drop(columns="_sort_ts")


def build_feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    ensure_required_columns(frame, list(CAUSAL_FEATURE_NAMES), "training frame")
    matrix = frame.loc[:, CAUSAL_FEATURE_NAMES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return matrix.to_numpy(dtype=np.float64)


def compute_balanced_sample_weights(targets: np.ndarray) -> np.ndarray:
    unique, counts = np.unique(targets, return_counts=True)
    total = len(targets)
    num_classes = len(unique)
    class_weights = {
        int(label): total / (num_classes * int(count))
        for label, count in zip(unique, counts, strict=False)
    }
    return np.asarray([class_weights[int(label)] for label in targets], dtype=np.float64)


def split_walk_forward(
    frame: pd.DataFrame,
    timestamp_col: str,
    label_col: str,
    label_to_id: dict[str, int],
    frame_name: str,
) -> dict[str, Any]:
    ensure_required_columns(frame, [timestamp_col, label_col], frame_name)
    cleaned = frame.copy()
    cleaned[label_col] = cleaned[label_col].astype(str).str.upper()
    cleaned = cleaned[cleaned[label_col].isin(label_to_id)].copy()
    if cleaned.empty:
        raise ValueError(f"{frame_name} has no rows with supported labels in `{label_col}`.")

    cleaned = sort_temporally(cleaned, timestamp_col, frame_name)
    X = build_feature_matrix(cleaned)
    y = cleaned[label_col].map(label_to_id).astype(np.int8).to_numpy()

    if len(cleaned) < 2:
        raise ValueError(f"{frame_name} needs at least 2 rows for an 80/20 walk-forward split.")

    split_idx = int(len(cleaned) * 0.8)
    split_idx = min(max(split_idx, 1), len(cleaned) - 1)

    return {
        "frame": cleaned,
        "X_train": X[:split_idx],
        "X_test": X[split_idx:],
        "y_train": y[:split_idx],
        "y_test": y[split_idx:],
        "train_frame": cleaned.iloc[:split_idx].copy(),
        "test_frame": cleaned.iloc[split_idx:].copy(),
    }


def format_distribution(targets: np.ndarray, class_names: list[str]) -> dict[str, dict[str, float]]:
    total = int(len(targets))
    if total == 0:
        return {name: {"count": 0, "pct": 0.0} for name in class_names}
    counts = np.bincount(targets.astype(np.int64), minlength=len(class_names))
    return {
        class_name: {"count": int(counts[idx]), "pct": float(counts[idx] / total)}
        for idx, class_name in enumerate(class_names)
    }


def warn_on_small_classes(y_train: np.ndarray, class_names: list[str], model_name: str) -> None:
    counts = np.bincount(y_train.astype(np.int64), minlength=len(class_names))
    for idx, count in enumerate(counts):
        if int(count) < 5:
            print(
                f"[warning] {model_name}: class {class_names[idx]} has only {int(count)} training samples "
                "(<5) after walk-forward split."
            )


def train_lightgbm_multiclass(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: list[str],
    num_class: int,
) -> Any:
    require_lightgbm()
    params = dict(BASE_MULTICLASS_PARAMS)
    params["num_class"] = num_class
    sample_weight = compute_balanced_sample_weights(y_train)

    train_set = lgb.Dataset(
        X_train,
        label=y_train,
        weight=sample_weight,
        feature_name=feature_names,
    )
    valid_set = lgb.Dataset(
        X_test,
        label=y_test,
        feature_name=feature_names,
        reference=train_set,
    )
    return lgb.train(
        params=params,
        train_set=train_set,
        num_boost_round=200,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(20, verbose=False), lgb.log_evaluation(-1)],
    )


def coerce_multiclass_probabilities(probabilities: np.ndarray, rows: int, num_class: int) -> np.ndarray:
    probabilities = np.asarray(probabilities, dtype=np.float64)
    if probabilities.ndim == 1:
        if probabilities.size != rows * num_class:
            raise ValueError(
                f"Unexpected multiclass probability shape {probabilities.shape} for rows={rows}, num_class={num_class}."
            )
        return probabilities.reshape(rows, num_class)
    if probabilities.ndim == 2 and probabilities.shape[1] == num_class:
        return probabilities
    raise ValueError(
        f"Unexpected multiclass probability shape {probabilities.shape} for rows={rows}, num_class={num_class}."
    )


def build_metrics(model: Any, X_test: np.ndarray, y_test: np.ndarray, class_names: list[str]) -> dict[str, Any]:
    probability_rows = coerce_multiclass_probabilities(model.predict(X_test), len(X_test), len(class_names))
    y_pred = np.argmax(probability_rows, axis=1).astype(np.int8)
    report = classification_report(
        y_test,
        y_pred,
        labels=list(range(len(class_names))),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    feature_importance_gain = model.feature_importance(importance_type="gain")
    feature_importance_split = model.feature_importance(importance_type="split")
    return {
        "f1": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        "weighted_f1": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        "precision": float(precision_score(y_test, y_pred, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=list(range(len(class_names)))).tolist(),
        "per_class": {
            class_name: {
                "precision": float(report[class_name]["precision"]),
                "recall": float(report[class_name]["recall"]),
                "f1": float(report[class_name]["f1-score"]),
                "support": int(report[class_name]["support"]),
            }
            for class_name in class_names
        },
        "feature_importance": {
            name: float(value)
            for name, value in zip(CAUSAL_FEATURE_NAMES, feature_importance_gain, strict=False)
        },
        "feature_importance_split": {
            name: int(value)
            for name, value in zip(CAUSAL_FEATURE_NAMES, feature_importance_split, strict=False)
        },
    }


def print_model_report(model_name: str, metrics: dict[str, Any], class_names: list[str]) -> None:
    print(f"\n[{model_name}] Metrics")
    print(f"  weighted_f1: {metrics['weighted_f1']:.4f}")
    print(f"  precision:   {metrics['precision']:.4f}")
    print(f"  recall:      {metrics['recall']:.4f}")
    print(f"  accuracy:    {metrics['accuracy']:.4f}")
    print("  confusion_matrix:")
    for row in metrics["confusion_matrix"]:
        print(f"    {row}")
    print("  per_class:")
    for class_name in class_names:
        values = metrics["per_class"][class_name]
        print(
            f"    {class_name}: precision={values['precision']:.4f} recall={values['recall']:.4f} "
            f"f1={values['f1']:.4f} support={values['support']}"
        )
    print("  top_10_feature_importance:")
    for rank, (feature_name, importance) in enumerate(top_feature_importance(metrics, top_n=10), start=1):
        print(f"    {rank:02d}. {feature_name}: {importance:.6f}")


def top_feature_importance(metrics: dict[str, Any], top_n: int) -> list[tuple[str, float]]:
    items = list(metrics["feature_importance"].items())
    items.sort(key=lambda item: item[1], reverse=True)
    return items[:top_n]


def print_class_distribution(model_name: str, y_train: np.ndarray, y_test: np.ndarray, class_names: list[str]) -> None:
    train_dist = format_distribution(y_train, class_names)
    test_dist = format_distribution(y_test, class_names)
    print(f"\n[{model_name}] Class distribution")
    for class_name in class_names:
        train_values = train_dist[class_name]
        test_values = test_dist[class_name]
        print(
            f"  {class_name}: train={train_values['count']} ({train_values['pct']:.2%}) "
            f"test={test_values['count']} ({test_values['pct']:.2%})"
        )


def print_leakage_audit(model_name: str, metrics: dict[str, Any]) -> None:
    print(f"\n[{model_name}] Leakage audit")
    ranked = sorted(metrics["feature_importance"].items(), key=lambda item: item[1], reverse=True)
    total_importance = float(sum(value for _, value in ranked))
    for rank, (feature_name, importance) in enumerate(ranked, start=1):
        share = float(importance / total_importance) if total_importance > 0 else 0.0
        flag = " INVESTIGATE" if share > 0.30 else ""
        print(f"  {rank:02d}. {feature_name}: importance={importance:.6f} share={share:.2%}{flag}")


def print_summary(
    episodes_df: pd.DataFrame,
    snapshots_df: pd.DataFrame,
    touches_df: pd.DataFrame,
    labeled_touches_df: pd.DataFrame,
) -> None:
    print("\n[summary] Data volume")
    print(f"  episodes:  {len(episodes_df)}")
    print(f"  snapshots: {len(snapshots_df)}")
    print(f"  touches:   {len(touches_df)}")
    if "episode_id" in episodes_df.columns:
        print(f"  unique_episode_ids: {episodes_df['episode_id'].nunique()}")

    if "intent_label" in episodes_df.columns:
        print("\n[summary] Intent distribution")
        intent_counts = episodes_df["intent_label"].fillna("<NULL>").astype(str).value_counts(dropna=False)
        for label, count in intent_counts.items():
            print(f"  {label}: {int(count)}")

    print("\n[summary] Touch outcome distribution")
    if labeled_touches_df.empty:
        print("  No labeled touch outcomes available.")
    else:
        touch_counts = labeled_touches_df["outcome"].astype(str).value_counts(dropna=False)
        for label, count in touch_counts.items():
            print(f"  {label}: {int(count)}")


def train_intent_classifier(
    episodes_df: pd.DataFrame,
    snapshots_df: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Any]:
    ensure_required_columns(episodes_df, ["episode_id", "intent_label"], "episodes_df")
    ensure_required_columns(snapshots_df, ["episode_id", "timestamp"], "snapshots_df")

    episode_labels = episodes_df.loc[:, ["episode_id", "intent_label"]].copy()
    episode_labels["intent_label"] = episode_labels["intent_label"].astype(str).str.upper()
    episode_labels = episode_labels.drop_duplicates(subset="episode_id", keep="last")
    training_frame = snapshots_df.merge(episode_labels, on="episode_id", how="left", validate="many_to_one")
    training_frame = training_frame[training_frame["intent_label"].isin(INTENT_LABEL_TO_ID)].copy()
    if training_frame.empty:
        raise ValueError("No snapshot rows could be joined to a valid intent_label.")

    split = split_walk_forward(
        frame=training_frame,
        timestamp_col="timestamp",
        label_col="intent_label",
        label_to_id=INTENT_LABEL_TO_ID,
        frame_name="intent training frame",
    )
    warn_on_small_classes(split["y_train"], INTENT_CLASS_NAMES, "intent_classifier_v4")
    model = train_lightgbm_multiclass(
        split["X_train"],
        split["y_train"],
        split["X_test"],
        split["y_test"],
        list(CAUSAL_FEATURE_NAMES),
        num_class=len(INTENT_CLASS_NAMES),
    )
    metrics = build_metrics(model, split["X_test"], split["y_test"], INTENT_CLASS_NAMES)
    metrics["train_class_distribution"] = format_distribution(split["y_train"], INTENT_CLASS_NAMES)
    metrics["test_class_distribution"] = format_distribution(split["y_test"], INTENT_CLASS_NAMES)
    metrics["train_rows"] = int(len(split["X_train"]))
    metrics["test_rows"] = int(len(split["X_test"]))

    payload = {
        "model": model,
        "mode": "multiclass",
        "class_names": list(INTENT_CLASS_NAMES),
        "feature_names": list(CAUSAL_FEATURE_NAMES),
        "training_metrics": metrics,
        "version": "v4",
    }
    output_path = output_dir / "intent_classifier_v4.joblib"
    joblib.dump(payload, output_path)

    print_model_report("intent_classifier_v4", metrics, INTENT_CLASS_NAMES)
    print_class_distribution("intent_classifier_v4", split["y_train"], split["y_test"], INTENT_CLASS_NAMES)
    print_leakage_audit("intent_classifier_v4", metrics)
    return {"path": output_path, "metrics": metrics}


def train_interaction_predictor(touches_df: pd.DataFrame, output_dir: Path) -> dict[str, Any] | None:
    ensure_required_columns(touches_df, ["timestamp", "outcome"], "touches_df")
    training_frame = touches_df.copy()
    training_frame["outcome"] = training_frame["outcome"].where(training_frame["outcome"].notna(), None)
    training_frame = training_frame[training_frame["outcome"].notna()].copy()
    training_frame["outcome"] = training_frame["outcome"].astype(str).str.upper()
    training_frame = training_frame[training_frame["outcome"].isin(INTERACTION_LABEL_TO_ID)].copy()

    if training_frame.empty:
        print("[warning] touches_df has no labeled outcomes. Skipping interaction predictor training.")
        return None

    split = split_walk_forward(
        frame=training_frame,
        timestamp_col="timestamp",
        label_col="outcome",
        label_to_id=INTERACTION_LABEL_TO_ID,
        frame_name="interaction training frame",
    )
    warn_on_small_classes(split["y_train"], INTERACTION_CLASS_NAMES, "interaction_predictor_v4")
    model = train_lightgbm_multiclass(
        split["X_train"],
        split["y_train"],
        split["X_test"],
        split["y_test"],
        list(CAUSAL_FEATURE_NAMES),
        num_class=len(INTERACTION_CLASS_NAMES),
    )
    metrics = build_metrics(model, split["X_test"], split["y_test"], INTERACTION_CLASS_NAMES)
    metrics["train_class_distribution"] = format_distribution(split["y_train"], INTERACTION_CLASS_NAMES)
    metrics["test_class_distribution"] = format_distribution(split["y_test"], INTERACTION_CLASS_NAMES)
    metrics["train_rows"] = int(len(split["X_train"]))
    metrics["test_rows"] = int(len(split["X_test"]))

    payload = {
        "model": model,
        "mode": "multiclass",
        "class_names": list(INTERACTION_CLASS_NAMES),
        "feature_names": list(CAUSAL_FEATURE_NAMES),
        "training_metrics": metrics,
        "version": "v4",
    }
    output_path = output_dir / "interaction_predictor_v4.joblib"
    joblib.dump(payload, output_path)

    print_model_report("interaction_predictor_v4", metrics, INTERACTION_CLASS_NAMES)
    print_class_distribution("interaction_predictor_v4", split["y_train"], split["y_test"], INTERACTION_CLASS_NAMES)
    print_leakage_audit("interaction_predictor_v4", metrics)
    return {"path": output_path, "metrics": metrics}


def copy_to_production(model_path: Path, production_path: Path) -> None:
    production_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, production_path)
    print(f"[copy] {model_path} -> {production_path}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()

    try:
        episodes_df, snapshots_df, touches_df = load_or_label_data(args)
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[error] Stage 1 failed: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1

    if snapshots_df.empty:
        print("[error] snapshots_df is empty after labeling/loading. Cannot train v4 models.", file=sys.stderr)
        return 1

    print_summary(
        episodes_df=episodes_df,
        snapshots_df=snapshots_df,
        touches_df=touches_df,
        labeled_touches_df=touches_df[touches_df["outcome"].notna()].copy() if "outcome" in touches_df.columns else touches_df.iloc[0:0].copy(),
    )

    if args.label_only:
        print("[label] --label-only set. Exiting after Stage 1.")
        return 0

    try:
        print("\n[train] Stage 2: intent classifier")
        intent_result = train_intent_classifier(episodes_df, snapshots_df, output_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] Stage 2 failed: {exc}", file=sys.stderr)
        return 1

    interaction_result: dict[str, Any] | None = None
    try:
        if touches_df.empty:
            print("[warning] touches_df is empty. Skipping interaction predictor training.")
        else:
            print("\n[train] Stage 3: interaction predictor")
            interaction_result = train_interaction_predictor(touches_df, output_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] Stage 3 failed: {exc}", file=sys.stderr)
        return 1

    print("\n[validate] Stage 4 complete")

    try:
        print("\n[copy] Stage 5: production copy")
        copy_to_production(intent_result["path"], Path("deep6/models/intent_classifier_v4.joblib").resolve())
        if interaction_result is not None:
            copy_to_production(
                interaction_result["path"],
                Path("deep6/models/interaction_predictor_v4.joblib").resolve(),
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[error] Stage 5 failed: {exc}", file=sys.stderr)
        return 1

    print("\n[done] DepthRadar v4 training pipeline completed successfully.")
    print(f"  output_dir: {output_dir}")
    print(f"  intent_model: {intent_result['path']}")
    if interaction_result is not None:
        print(f"  interaction_model: {interaction_result['path']}")
    else:
        print("  interaction_model: skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
