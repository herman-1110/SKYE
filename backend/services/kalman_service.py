import numpy as np
from filterpy.kalman import KalmanFilter
from typing import Tuple


class KalmanService:
    """
    2D Kalman Filter for indoor position smoothing.
    State vector: [x, y, vx, vy] — position + velocity.
    Per LR2 (Ainul et al.) this reduces position error to within 1.2 m.
    """

    def __init__(
        self,
        dt: float = 1.0,
        process_noise: float = 0.1,
        measurement_noise: float = 2.0,
    ) -> None:
        self._dt = dt
        self._kf = self._build(dt, process_noise, measurement_noise)
        self._initialised = False

    def _build(self, dt: float, q: float, r: float) -> KalmanFilter:
        kf = KalmanFilter(dim_x=4, dim_z=2)
        kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1,  0, dt],
            [0, 0,  1,  0],
            [0, 0,  0,  1],
        ], dtype=float)
        kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        kf.R = np.eye(2) * r
        kf.Q = np.eye(4) * q
        kf.P = np.eye(4) * 10.0
        return kf

    def update(self, x: float, y: float) -> Tuple[float, float]:
        """Apply a new (x, y) measurement and return the Kalman-smoothed position."""
        z = np.array([[x], [y]], dtype=float)
        if not self._initialised:
            self._kf.x = np.array([[x], [y], [0.0], [0.0]], dtype=float)
            self._initialised = True
        self._kf.predict()
        self._kf.update(z)
        return float(self._kf.x[0, 0]), float(self._kf.x[1, 0])

    def predict_ahead(self, seconds: float = 3.0) -> Tuple[float, float]:
        """Project current state forward by `seconds` for pre-emptive collision alerting (FR4)."""
        steps = max(1, round(seconds / self._dt))
        x_state = self._kf.x.copy()
        for _ in range(steps):
            x_state = self._kf.F @ x_state
        return float(x_state[0, 0]), float(x_state[1, 0])
