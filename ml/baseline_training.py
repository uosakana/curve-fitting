from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

from ml.model_registry import DEFAULT_MODEL_DIR
from ml.training_tasks import TASK_DEFS


def _available_columns(columns: tuple[str, ...], frame) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _clean_target(series) -> Any:
    cleaned = series.fillna("").astype(str).str.strip()
    cleaned = cleaned.replace({"": None, "nan": None, "None": None})
    return cleaned


def _one_hot_encoder():
    from sklearn.preprocessing import OneHotEncoder

    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def _split_data(frame, target: str):
    from sklearn.model_selection import train_test_split

    if "dataset_split" in frame.columns:
        train = frame[frame["dataset_split"].astype(str).str.lower() == "train"]
        eval_frame = frame[frame["dataset_split"].astype(str).str.lower().isin({"val", "test"})]
        if len(train) >= 2 and len(eval_frame) >= 1 and train[target].nunique() >= 2:
            return train, eval_frame, "dataset_split"

    stratify = frame[target] if frame[target].value_counts().min() >= 2 else None
    train, eval_frame = train_test_split(
        frame,
        test_size=0.25,
        random_state=42,
        stratify=stratify,
    )
    return train, eval_frame, "random_stratified" if stratify is not None else "random"


def _feature_importance(pipeline, limit: int = 25) -> list[dict[str, Any]]:
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    try:
        feature_names = list(preprocessor.get_feature_names_out())
    except Exception:
        return []
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return []
    pairs = sorted(zip(feature_names, importances), key=lambda item: float(item[1]), reverse=True)
    return [
        {"feature": str(feature), "importance": float(importance)}
        for feature, importance in pairs[:limit]
    ]


def train_random_forest_baseline(
    dataset_path: str | Path,
    task_name: str,
    output_dir: str | Path = DEFAULT_MODEL_DIR,
    *,
    n_estimators: int = 300,
    min_samples_leaf: int = 2,
    random_state: int = 42,
) -> tuple[Path, Path, dict[str, Any]]:
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
    from sklearn.pipeline import Pipeline

    if task_name not in TASK_DEFS:
        raise ValueError(f"Unknown task {task_name!r}. Expected one of: {', '.join(TASK_DEFS)}")

    task = TASK_DEFS[task_name]
    dataset = Path(dataset_path)
    frame = pd.read_csv(dataset)
    if task.target not in frame.columns:
        raise ValueError(f"Dataset does not contain target column {task.target!r}.")

    frame = frame.copy()
    frame[task.target] = _clean_target(frame[task.target])
    frame = frame[frame[task.target].notna()]
    if len(frame) < 10:
        raise ValueError(f"Need at least 10 labeled rows for task {task.name}; got {len(frame)}.")
    if frame[task.target].nunique() < 2:
        raise ValueError(f"Need at least two target classes for task {task.name}.")

    numeric_features = _available_columns(task.numeric_features, frame)
    categorical_features = _available_columns(task.categorical_features, frame)
    if not numeric_features and not categorical_features:
        raise ValueError("No usable feature columns are available in the dataset.")

    train, eval_frame, split_method = _split_data(frame, task.target)
    if train[task.target].nunique() < 2:
        raise ValueError("Training split contains fewer than two target classes.")

    numeric_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", _one_hot_encoder()),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric_features),
            ("cat", categorical_pipe, categorical_features),
        ],
        remainder="drop",
    )
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        min_samples_leaf=min_samples_leaf,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    pipeline = Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("model", model),
        ]
    )

    x_train = train[numeric_features + categorical_features]
    y_train = train[task.target].astype(str)
    x_eval = eval_frame[numeric_features + categorical_features]
    y_eval = eval_frame[task.target].astype(str)
    pipeline.fit(x_train, y_train)
    prediction = pipeline.predict(x_eval)

    labels = sorted(frame[task.target].astype(str).unique().tolist())
    metrics = {
        "task": task.name,
        "target": task.target,
        "description": task.description,
        "dataset_path": str(dataset),
        "split_method": split_method,
        "train_count": int(len(train)),
        "eval_count": int(len(eval_frame)),
        "class_counts": {str(k): int(v) for k, v in frame[task.target].value_counts().to_dict().items()},
        "accuracy": float(accuracy_score(y_eval, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y_eval, prediction)),
        "labels": labels,
        "classification_report": classification_report(y_eval, prediction, labels=labels, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y_eval, prediction, labels=labels).tolist(),
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "feature_importance": _feature_importance(pipeline),
        "model_type": "RandomForestClassifier",
        "model_params": {
            "n_estimators": int(n_estimators),
            "min_samples_leaf": int(min_samples_leaf),
            "class_weight": "balanced",
            "random_state": int(random_state),
        },
    }

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = output / f"{task.name}_random_forest_{timestamp}.pkl"
    metrics_path = output / f"{task.name}_random_forest_{timestamp}_metrics.json"
    artifact = {
        "task": task.name,
        "target": task.target,
        "pipeline": pipeline,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "labels": labels,
        "metrics": metrics,
    }
    with model_path.open("wb") as handle:
        pickle.dump(artifact, handle)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return model_path, metrics_path, metrics
