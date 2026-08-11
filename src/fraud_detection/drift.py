from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp


def population_stability_index(
    reference: NDArray[np.float64], current: NDArray[np.float64], bins: int = 10
) -> float:
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    reference_counts, _ = np.histogram(reference, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)
    reference_ratio = np.clip(reference_counts / max(reference_counts.sum(), 1), 1e-6, None)
    current_ratio = np.clip(current_counts / max(current_counts.sum(), 1), 1e-6, None)
    return float(
        np.sum((current_ratio - reference_ratio) * np.log(current_ratio / reference_ratio))
    )


def numeric_drift(reference: NDArray[np.float64], current: NDArray[np.float64]) -> dict[str, float]:
    statistic, p_value = ks_2samp(reference, current)
    return {
        "psi": population_stability_index(reference, current),
        "ks": float(statistic),
        "ks_p_value": float(p_value),
    }


def categorical_drift(reference: list[str], current: list[str]) -> float:
    categories = sorted(set(reference) | set(current))
    reference_counts = np.array([reference.count(item) for item in categories], dtype=float)
    current_counts = np.array([current.count(item) for item in categories], dtype=float)
    return float(
        jensenshannon(
            reference_counts / reference_counts.sum(), current_counts / current_counts.sum()
        )
        ** 2
    )
