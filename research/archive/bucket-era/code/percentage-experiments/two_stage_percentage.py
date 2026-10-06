"""Two-stage CatBoost estimator for 0-100 suggestion coverage."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.base import BaseEstimator, RegressorMixin


ZERO_REGIME = 0
INTERMEDIATE_REGIME = 1
HUNDRED_REGIME = 2


class PercentageModelBlend(RegressorMixin, BaseEstimator):
    """Blend two fitted percentage estimators into one bounded prediction."""

    def __init__(self, baseline_model: Any, specialist_model: Any, specialist_weight: float) -> None:
        if not 0.0 <= specialist_weight <= 1.0:
            raise ValueError("specialist_weight must be within [0, 1]")
        self.baseline_model = baseline_model
        self.specialist_model = specialist_model
        self.specialist_weight = specialist_weight

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        baseline_predictions = np.asarray(self.baseline_model.predict(features), dtype=float)
        specialist_predictions = np.asarray(self.specialist_model.predict(features), dtype=float)
        predictions = (
            (1.0 - self.specialist_weight) * baseline_predictions
            + self.specialist_weight * specialist_predictions
        )
        return np.clip(predictions, 0, 100)


class WeightedPercentageEnsemble(RegressorMixin, BaseEstimator):
    """Combine fitted percentage estimators with an optional fallback model."""

    def __init__(
        self,
        models: Sequence[Any],
        weights: Sequence[float],
        fallback_model_index: int | None = None,
        disagreement_threshold: float | None = None,
    ) -> None:
        if not models or len(models) != len(weights):
            raise ValueError("models and weights must be non-empty and have equal length")
        numeric_weights = np.asarray(weights, dtype=float)
        if np.any(numeric_weights < 0) or numeric_weights.sum() <= 0:
            raise ValueError("weights must be non-negative with a positive sum")
        if (fallback_model_index is None) != (disagreement_threshold is None):
            raise ValueError("fallback_model_index and disagreement_threshold must be set together")
        self.models = models
        self.weights = weights
        self.fallback_model_index = fallback_model_index
        self.disagreement_threshold = disagreement_threshold

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        component_predictions = np.column_stack(
            [np.asarray(model.predict(features), dtype=float) for model in self.models]
        )
        normalized_weights = np.asarray(self.weights, dtype=float)
        normalized_weights /= normalized_weights.sum()
        predictions = component_predictions @ normalized_weights
        if self.disagreement_threshold is not None:
            fallback_predictions = component_predictions[:, self.fallback_model_index]
            use_fallback = np.abs(predictions - fallback_predictions) > self.disagreement_threshold
            predictions = np.where(use_fallback, fallback_predictions, predictions)
        return np.clip(predictions, 0, 100)


class StackedPercentageEnsemble(RegressorMixin, BaseEstimator):
    """Apply a fitted meta-regressor to component percentage predictions."""

    def __init__(self, models: Sequence[Any], meta_model: Any) -> None:
        if not models:
            raise ValueError("models must be non-empty")
        self.models = models
        self.meta_model = meta_model

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        component_predictions = np.column_stack(
            [np.asarray(model.predict(features), dtype=float) for model in self.models]
        )
        return np.clip(np.asarray(self.meta_model.predict(component_predictions), dtype=float), 0, 100)


class TwoStageCatBoostRegressor(RegressorMixin, BaseEstimator):
    """Classify endpoint regimes, then regress intermediate percentages."""

    def __init__(
        self,
        categorical_features: Sequence[str] = (),
        iterations: int = 300,
        depth: int = 6,
        learning_rate: float = 0.04,
        l2_leaf_reg: float = 5.0,
        endpoint_threshold: float = 0.7,
        auto_class_weights: str | None = None,
        random_state: int = 42,
        thread_count: int = -1,
    ) -> None:
        self.categorical_features = categorical_features
        self.iterations = iterations
        self.depth = depth
        self.learning_rate = learning_rate
        self.l2_leaf_reg = l2_leaf_reg
        self.endpoint_threshold = endpoint_threshold
        self.auto_class_weights = auto_class_weights
        self.random_state = random_state
        self.thread_count = thread_count

    def fit(
        self,
        features: pd.DataFrame,
        target: Sequence[float],
        sample_weight: Sequence[float] | None = None,
    ) -> TwoStageCatBoostRegressor:
        frame = self._prepare_fit_features(features)
        percentages = np.asarray(target, dtype=float)
        if len(frame) != len(percentages):
            raise ValueError("features and target must have the same number of rows")
        if np.any((percentages < 0) | (percentages > 100)):
            raise ValueError("target percentages must be within [0, 100]")

        weights = None if sample_weight is None else np.asarray(sample_weight, dtype=float)
        if weights is not None and len(weights) != len(percentages):
            raise ValueError("sample_weight and target must have the same number of rows")

        regimes = np.where(
            percentages <= 0,
            ZERO_REGIME,
            np.where(percentages >= 100, HUNDRED_REGIME, INTERMEDIATE_REGIME),
        )
        unique_regimes = np.unique(regimes)
        self.constant_regime_ = int(unique_regimes[0]) if len(unique_regimes) == 1 else None
        self.classifier_ = None
        if self.constant_regime_ is None:
            self.classifier_ = CatBoostClassifier(
                iterations=self.iterations,
                depth=self.depth,
                learning_rate=self.learning_rate,
                l2_leaf_reg=self.l2_leaf_reg,
                loss_function="MultiClass",
                auto_class_weights=self.auto_class_weights,
                random_seed=self.random_state,
                thread_count=self.thread_count,
                verbose=False,
                allow_writing_files=False,
            )
            self.classifier_.fit(
                frame,
                regimes,
                cat_features=list(self.categorical_features),
                sample_weight=weights,
            )

        intermediate = regimes == INTERMEDIATE_REGIME
        intermediate_values = percentages[intermediate]
        intermediate_weights = None if weights is None else weights[intermediate]
        self.intermediate_default_ = self._weighted_average(intermediate_values, intermediate_weights, default=50.0)
        self.regressor_ = None
        if len(intermediate_values) >= 2:
            self.regressor_ = CatBoostRegressor(
                iterations=self.iterations,
                depth=self.depth,
                learning_rate=self.learning_rate,
                l2_leaf_reg=self.l2_leaf_reg,
                loss_function="MAE",
                eval_metric="MAE",
                random_seed=self.random_state,
                thread_count=self.thread_count,
                verbose=False,
                allow_writing_files=False,
            )
            self.regressor_.fit(
                frame.loc[intermediate],
                intermediate_values,
                cat_features=list(self.categorical_features),
                sample_weight=intermediate_weights,
            )
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return continuous percentage predictions bounded to 0-100."""
        return self.predict_with_threshold(features, self.endpoint_threshold)

    def predict_with_threshold(self, features: pd.DataFrame, endpoint_threshold: float) -> np.ndarray:
        """Predict with a configurable confidence threshold for exact endpoints."""
        if not 0.5 <= endpoint_threshold <= 1.0:
            raise ValueError("endpoint_threshold must be within [0.5, 1.0]")
        frame = self._prepare_predict_features(features)
        probabilities = self._regime_probabilities(frame)
        if self.regressor_ is None:
            intermediate_predictions = np.full(len(frame), self.intermediate_default_, dtype=float)
        else:
            intermediate_predictions = np.asarray(self.regressor_.predict(frame), dtype=float)
        intermediate_predictions = np.clip(intermediate_predictions, 1, 99)

        predictions = (
            probabilities[:, INTERMEDIATE_REGIME] * intermediate_predictions
            + probabilities[:, HUNDRED_REGIME] * 100.0
        )
        predictions = np.where(probabilities[:, ZERO_REGIME] >= endpoint_threshold, 0.0, predictions)
        predictions = np.where(probabilities[:, HUNDRED_REGIME] >= endpoint_threshold, 100.0, predictions)
        return np.clip(predictions, 0, 100)

    def _prepare_fit_features(self, features: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(features, pd.DataFrame):
            raise TypeError("TwoStageCatBoostRegressor requires a pandas DataFrame")
        self.feature_names_in_ = np.asarray(features.columns, dtype=object)
        return self._normalize_categories(features)

    def _prepare_predict_features(self, features: pd.DataFrame) -> pd.DataFrame:
        if not hasattr(self, "feature_names_in_"):
            raise RuntimeError("estimator must be fitted before prediction")
        if not isinstance(features, pd.DataFrame):
            raise TypeError("TwoStageCatBoostRegressor requires a pandas DataFrame")
        missing = [column for column in self.feature_names_in_ if column not in features.columns]
        if missing:
            raise ValueError(f"missing model features: {missing}")
        return self._normalize_categories(features.loc[:, self.feature_names_in_])

    def _normalize_categories(self, features: pd.DataFrame) -> pd.DataFrame:
        frame = features.copy()
        for column in self.categorical_features:
            if column not in frame.columns:
                raise ValueError(f"missing categorical feature: {column}")
            frame[column] = frame[column].fillna("none").astype(str)
        return frame

    def _regime_probabilities(self, features: pd.DataFrame) -> np.ndarray:
        probabilities = np.zeros((len(features), 3), dtype=float)
        if self.classifier_ is None:
            probabilities[:, self.constant_regime_] = 1.0
            return probabilities
        raw_probabilities = np.asarray(self.classifier_.predict_proba(features), dtype=float)
        for source_index, regime in enumerate(self.classifier_.classes_):
            probabilities[:, int(regime)] = raw_probabilities[:, source_index]
        return probabilities

    @staticmethod
    def _weighted_average(values: np.ndarray, weights: np.ndarray | None, default: float) -> float:
        if len(values) == 0:
            return default
        if weights is None or np.sum(weights) <= 0:
            return float(np.mean(values))
        return float(np.average(values, weights=weights))
