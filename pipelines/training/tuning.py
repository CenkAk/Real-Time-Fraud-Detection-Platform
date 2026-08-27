from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import numpy as np
import optuna
import pandas as pd
from numpy.typing import NDArray
from sklearn.ensemble import RandomForestClassifier

TrialLogger = Callable[[str, int, dict[str, object], dict[str, float]], None]


def _random_forest(params: dict[str, object]) -> RandomForestClassifier:
    return RandomForestClassifier(
        **params,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=42,
    )


def _xgboost(params: dict[str, object], imbalance: float) -> Any:
    from xgboost import XGBClassifier

    return XGBClassifier(
        **params,
        scale_pos_weight=imbalance,
        eval_metric="aucpr",
        random_state=42,
        n_jobs=-1,
    )


def tune_tree_models(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_selection: pd.DataFrame,
    trials: int,
    evaluate: Callable[[NDArray[np.float64]], dict[str, float]],
    log_trial: TrialLogger,
) -> tuple[dict[str, Any], dict[str, dict[str, object]]]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    imbalance = max(float((y_train == 0).sum() / max((y_train == 1).sum(), 1)), 1.0)
    models: dict[str, Any] = {}
    summaries: dict[str, dict[str, object]] = {}

    def tune(
        name: str,
        objective_factory: Callable[[optuna.Trial], tuple[Any, dict[str, object]]],
    ) -> None:
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(directions=["minimize", "maximize"], sampler=sampler)

        def objective(trial: optuna.Trial) -> tuple[float, float]:
            model, params = objective_factory(trial)
            model.fit(x_train, y_train)
            probabilities = model.predict_proba(x_selection)[:, 1]
            result = evaluate(probabilities)
            log_trial(name, trial.number, params, result)
            return result["expected_cost"], result["pr_auc"]

        study.optimize(objective, n_trials=trials, show_progress_bar=False)
        completed = [trial for trial in study.trials if trial.values is not None]
        if not completed:
            raise RuntimeError(f"{name} tuning produced no completed trials")
        best = min(completed, key=lambda trial: (trial.values[0], -trial.values[1]))
        # FrozenTrial implements the same suggest API by replaying stored parameters.
        best_model, best_params = objective_factory(cast(optuna.Trial, best))
        best_model.fit(x_train, y_train)
        models[name] = best_model
        summaries[name] = {
            "best_trial": best.number,
            "best_params": best_params,
            "selection_expected_cost": best.values[0],
            "selection_pr_auc": best.values[1],
            "trial_count": len(completed),
        }

    def random_forest_factory(trial: optuna.Trial) -> tuple[Any, dict[str, object]]:
        params: dict[str, object] = {
            "n_estimators": trial.suggest_int("n_estimators", 150, 500, step=50),
            "max_depth": trial.suggest_int("max_depth", 6, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 12),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", 0.7]),
        }
        return _random_forest(params), params

    def xgboost_factory(trial: optuna.Trial) -> tuple[Any, dict[str, object]]:
        params: dict[str, object] = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 600, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 12.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-5, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        return _xgboost(params, imbalance), params

    tune("random_forest", random_forest_factory)
    tune("xgboost", xgboost_factory)
    return models, summaries
