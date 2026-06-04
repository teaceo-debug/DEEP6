#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, _tree

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/signal_events.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_JSON = OUT_DIR / "absorption_feature_ml_results.json"

FEATURES = [
    "strength",
    "bar_volume",
    "abs_delta",
    "delta_pct",
    "bar_range",
    "score_final",
    "hour",
    "minute_of_day",
    "dow",
    "is_type_a",
    "is_type_b",
    "volume_rank",
    "range_rank",
]
TARGETS = ["profitable_5b", "profitable_15b"]
ET_TZ = "America/New_York"


@dataclass
class ModelSummary:
    name: str
    accuracy_mean: float
    accuracy_std: float
    auc_mean: float
    auc_std: float
    top_features: list[dict[str, float]]


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, low_memory=False)
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce")

    numeric_cols = [
        "strength",
        "score_final",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_5b",
        "fwd_close_15b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["direction_num"] = pd.to_numeric(df["direction"], errors="coerce")

    unique_bars = (
        df[["session_date", "bar_index", "bar_volume", "bar_high", "bar_low", "bar_ts"]]
        .drop_duplicates(subset=["session_date", "bar_index"])
        .copy()
    )
    unique_bars["bar_range"] = (unique_bars["bar_high"] - unique_bars["bar_low"]) / 0.25
    unique_bars["volume_rank"] = unique_bars.groupby("session_date")["bar_volume"].rank(pct=True, method="average")
    unique_bars["range_rank"] = unique_bars.groupby("session_date")["bar_range"].rank(pct=True, method="average")

    absorption = df[df["category"] == "absorption"].copy()
    absorption = absorption.merge(
        unique_bars[["session_date", "bar_index", "volume_rank", "range_rank"]],
        on=["session_date", "bar_index"],
        how="left",
    )

    ts_et = absorption["bar_ts"].dt.tz_convert(ET_TZ)
    absorption["abs_delta"] = absorption["bar_delta"].abs()
    absorption["delta_pct"] = np.where(absorption["bar_volume"] != 0, absorption["bar_delta"] / absorption["bar_volume"], 0.0)
    absorption["bar_range"] = (absorption["bar_high"] - absorption["bar_low"]) / 0.25
    absorption["hour"] = ts_et.dt.hour
    absorption["minute_of_day"] = (ts_et.dt.hour * 60 + ts_et.dt.minute) - (9 * 60 + 30)
    absorption["dow"] = ts_et.dt.dayofweek
    absorption["is_type_a"] = (absorption["score_tier"] == "TYPE_A").astype(int)
    absorption["is_type_b"] = (absorption["score_tier"] == "TYPE_B").astype(int)
    absorption["profitable_5b"] = (((absorption["fwd_close_5b"] - absorption["bar_close"]) * absorption["direction_num"]) > 0).astype(int)
    absorption["profitable_15b"] = (((absorption["fwd_close_15b"] - absorption["bar_close"]) * absorption["direction_num"]) > 0).astype(int)

    absorption = absorption.dropna(subset=FEATURES + TARGETS)
    return absorption.reset_index(drop=True)


def build_models() -> dict[str, Pipeline | RandomForestClassifier]:
    logreg = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, solver="liblinear", random_state=42)),
        ]
    )
    rf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=100,
                    max_depth=5,
                    random_state=42,
                    min_samples_leaf=10,
                    class_weight="balanced_subsample",
                    n_jobs=-1,
                ),
            ),
        ]
    )
    return {"random_forest": rf, "logistic_regression": logreg}


def cross_validated_summary(X: pd.DataFrame, y: pd.Series, pipeline: Pipeline, feature_names: list[str], *, logistic: bool) -> ModelSummary:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    accuracies: list[float] = []
    aucs: list[float] = []
    importances: list[np.ndarray] = []

    for train_idx, test_idx in cv.split(X, y):
        X_train = X.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]

        pipeline.fit(X_train, y_train)
        preds = pipeline.predict(X_test)
        probs = pipeline.predict_proba(X_test)[:, 1]

        accuracies.append(accuracy_score(y_test, preds))
        aucs.append(roc_auc_score(y_test, probs))

        model = pipeline.named_steps["model"]
        if logistic:
            importances.append(np.abs(model.coef_[0]))
        else:
            importances.append(model.feature_importances_)

    mean_importance = np.mean(np.vstack(importances), axis=0)
    ranking = sorted(
        ({"feature": feature, "importance": float(importance)} for feature, importance in zip(feature_names, mean_importance)),
        key=lambda item: item["importance"],
        reverse=True,
    )

    return ModelSummary(
        name="logistic_regression" if logistic else "random_forest",
        accuracy_mean=float(np.mean(accuracies)),
        accuracy_std=float(np.std(accuracies, ddof=1)),
        auc_mean=float(np.mean(aucs)),
        auc_std=float(np.std(aucs, ddof=1)),
        top_features=ranking[:5],
    )


def majority_baseline(y: pd.Series) -> float:
    return float(max(y.mean(), 1.0 - y.mean()))


def best_leaf_rule(df: pd.DataFrame, target: str, top_features: list[str]) -> dict[str, float | int | str | list[str]]:
    X = df[top_features]
    y = df[target]
    tree = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("model", DecisionTreeClassifier(max_depth=3, min_samples_leaf=25, random_state=42)),
        ]
    )
    tree.fit(X, y)

    imputer = tree.named_steps["imputer"]
    model = tree.named_steps["model"]
    X_imp = imputer.transform(X)
    leaf_ids = model.apply(X_imp)

    best_leaf = None
    best_wr = -1.0
    for leaf_id in np.unique(leaf_ids):
        mask = leaf_ids == leaf_id
        support = int(mask.sum())
        if support < 25:
            continue
        wr = float(y[mask].mean())
        if wr > best_wr:
            best_wr = wr
            best_leaf = int(leaf_id)

    if best_leaf is None:
        return {"rule": "No stable leaf rule found", "win_rate": float(y.mean()), "support": int(len(y)), "features": top_features}

    paths: list[str] = []

    def walk(node: int, clauses: list[str]) -> bool:
        if model.tree_.feature[node] == _tree.TREE_UNDEFINED:
            if node == best_leaf:
                paths.extend(clauses)
                return True
            return False

        feature = top_features[model.tree_.feature[node]]
        threshold = float(model.tree_.threshold[node])
        left_clause = f"{feature} <= {threshold:.3f}"
        right_clause = f"{feature} > {threshold:.3f}"
        return walk(model.tree_.children_left[node], clauses + [left_clause]) or walk(model.tree_.children_right[node], clauses + [right_clause])

    walk(0, [])
    support = int((leaf_ids == best_leaf).sum())
    wr = float(y[leaf_ids == best_leaf].mean())
    return {
        "rule": " AND ".join(paths),
        "win_rate": wr,
        "support": support,
        "features": top_features,
    }


def run_analysis() -> dict:
    df = load_dataset()
    X = df[FEATURES]

    results: dict[str, object] = {
        "n_absorption": int(len(df)),
        "feature_names": FEATURES,
        "targets": {},
    }
    models = build_models()

    for target in TARGETS:
        y = df[target]
        target_results: dict[str, object] = {
            "majority_baseline_accuracy": majority_baseline(y),
            "positive_rate": float(y.mean()),
            "models": {},
        }

        rf_summary = cross_validated_summary(X, y, models["random_forest"], FEATURES, logistic=False)
        log_summary = cross_validated_summary(X, y, models["logistic_regression"], FEATURES, logistic=True)

        target_results["models"][rf_summary.name] = rf_summary.__dict__
        target_results["models"][log_summary.name] = log_summary.__dict__

        top_rule_features = [item["feature"] for item in rf_summary.top_features[:3]]
        target_results["decision_rule"] = best_leaf_rule(df, target, top_rule_features)
        results["targets"][target] = target_results

    return results


def print_report(results: dict) -> None:
    print(f"Absorption rows analyzed: {results['n_absorption']}")
    print(f"Features: {', '.join(results['feature_names'])}")
    print()

    for target, target_results in results["targets"].items():
        print(f"=== {target} ===")
        print(
            f"Baseline accuracy (majority class): {target_results['majority_baseline_accuracy']:.3f} | "
            f"positive rate: {target_results['positive_rate']:.3f}"
        )
        for model_name, model_results in target_results["models"].items():
            print(
                f"{model_name}: accuracy={model_results['accuracy_mean']:.3f} ± {model_results['accuracy_std']:.3f}, "
                f"auc={model_results['auc_mean']:.3f} ± {model_results['auc_std']:.3f}"
            )
            print("  top features:")
            for item in model_results["top_features"]:
                print(f"    - {item['feature']}: {item['importance']:.4f}")
        rule = target_results["decision_rule"]
        print(
            f"Decision rule: {rule['rule']} -> win rate {rule['win_rate']:.3f} "
            f"on n={rule['support']}"
        )
        print()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = run_analysis()
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print_report(results)
    print(f"Saved JSON report to {OUT_JSON}")


if __name__ == "__main__":
    main()
