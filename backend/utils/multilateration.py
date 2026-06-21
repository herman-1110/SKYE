from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares as scipy_least_squares


def least_squares_position(
    ap_positions: List[Tuple[float, float]],
    distances: List[float],
    bounds: Optional[Tuple[float, float, float, float]] = None,  # (x_min, x_max, y_min, y_max)
) -> Optional[Tuple[float, float]]:
    """
    Estimate (x, y) from N >= 3 AP positions and distances via weighted nonlinear
    least-squares. Inverse-square-distance weighting lets strong (near) APs dominate
    and downweights obstructed far APs. Optional floor bounds keep the estimate on-map.
    """
    if len(ap_positions) < 3 or len(ap_positions) != len(distances):
        return None

    aps = np.array(ap_positions, dtype=float)
    d = np.array(distances, dtype=float)

    # Inverse-square weights; clip distances to 0.1 m to avoid division by zero
    w = 1.0 / np.clip(d, 0.1, None) ** 2
    w /= w.sum()

    # Weighted centroid as initial guess
    p0 = (aps * w[:, None]).sum(axis=0)

    def residuals(p: np.ndarray) -> np.ndarray:
        diff = aps - p
        dist_est = np.sqrt((diff ** 2).sum(axis=1))
        return np.sqrt(w) * (dist_est - d)

    try:
        if bounds is not None:
            x_min, x_max, y_min, y_max = bounds
            sol = scipy_least_squares(
                residuals,
                p0,
                method="trf",
                bounds=([x_min, y_min], [x_max, y_max]),
            )
        else:
            sol = scipy_least_squares(residuals, p0, method="lm")
    except Exception:
        return None

    return float(sol.x[0]), float(sol.x[1])
