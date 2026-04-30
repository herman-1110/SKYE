from typing import List, Tuple, Optional
import numpy as np


def least_squares_position(
    ap_positions: List[Tuple[float, float]],
    distances: List[float],
) -> Optional[Tuple[float, float]]:
    """
    Estimate (x, y) from N >= 3 AP positions and distances via Least Squares.

    Linearises the system by subtracting the last AP's equation from all others,
    which eliminates quadratic position terms.  All N APs are used simultaneously
    so more APs reduce position error (per LR1 Ramires et al., LR2 Ainul et al.).
    """
    if len(ap_positions) < 3 or len(ap_positions) != len(distances):
        return None

    x_ref, y_ref = ap_positions[-1]
    d_ref = distances[-1]

    A_rows: List[List[float]] = []
    b_rows: List[float] = []

    for i in range(len(ap_positions) - 1):
        xi, yi = ap_positions[i]
        di = distances[i]
        # Linearised equation: 2(xi-xr)*x + 2(yi-yr)*y = xi²-xr² + yi²-yr² - di²+dr²
        A_rows.append([2.0 * (xi - x_ref), 2.0 * (yi - y_ref)])
        b_rows.append(
            xi**2 - x_ref**2 + yi**2 - y_ref**2 - di**2 + d_ref**2
        )

    A = np.array(A_rows, dtype=float)
    b = np.array(b_rows, dtype=float)
    result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    return float(result[0]), float(result[1])
