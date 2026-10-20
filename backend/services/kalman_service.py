import time
from typing import Optional, Tuple

import numpy as np
from filterpy.kalman import KalmanFilter

# Consecutive outlier rejections after which the filter gives up on its own
# estimate and re-initialises from the latest measurement (Prompt 136,
# COR-02). Without it, a person who really did move more than the outlier
# threshold (or a floor recalibration that shifts every solve) was rejected
# forever: the output stayed frozen at the old position.
_REJECTS_BEFORE_RESET = 3


class KalmanService:
    """
    2D Kalman Filter for indoor position smoothing.
    State vector: [x, y, vx, vy] — position + velocity.

    Time-aware: dt is the real wall-clock interval between successive update()
    calls (time.monotonic). F and the process-noise matrix Q are rebuilt every
    step so covariance growth and velocity projection track the true ~2 s
    telemetry cadence instead of a fixed dt=1.0.
    """

    # Bound measured dt so a long gap or a burst can't destabilise the filter.
    _DT_MIN_S = 0.05
    _DT_MAX_S = 5.0

    def __init__(
        self,
        dt: float = 1.0,                 # accepted for backward-compat; IGNORED (filter is time-aware)
        process_noise: float = 0.5,      # Q — lower = smoother steady motion (white-noise-accel var)
        measurement_noise: float = 6.0,  # R — higher = smoother + laggier
    ) -> None:
        # dt intentionally unused — real elapsed dt is measured per update().
        self._q = float(process_noise)
        self._r = float(measurement_noise)
        self._kf = self._build(self._r)
        self._initialised = False
        self._last_mono: Optional[float] = None
        self._rejected_in_a_row = 0
        # False when the last update() rejected its measurement as an outlier,
        # True when it accepted it or initialised from it. positioning_service
        # only counts a beacon as seen for an accepted measurement.
        self.last_update_accepted = True

    def _build(self, r: float) -> KalmanFilter:
        kf = KalmanFilter(dim_x=4, dim_z=2)
        kf.F = np.eye(4, dtype=float)            # set per-step in _apply_dt()
        kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        kf.R = np.eye(2) * r
        kf.Q = np.eye(4) * self._q               # placeholder; overwritten per-step
        kf.P = np.eye(4) * 10.0
        return kf

    def _apply_dt(self, dt: float) -> None:
        """Rebuild F (constant-velocity) and Q (discrete white-noise accel) for this dt."""
        self._kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1,  0],
            [0, 0, 0,  1],
        ], dtype=float)
        q = self._q
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        # White-noise acceleration model, state order [x, y, vx, vy].
        self._kf.Q = q * np.array([
            [dt4 / 4, 0,       dt3 / 2, 0],
            [0,       dt4 / 4, 0,       dt3 / 2],
            [dt3 / 2, 0,       dt2,     0],
            [0,       dt3 / 2, 0,       dt2],
        ], dtype=float)

    def update(
        self,
        x: float,
        y: float,
        outlier_threshold_m: float = 8.0,
    ) -> Tuple[float, float]:
        """
        Apply a new (x, y) measurement and return the Kalman-smoothed position.
        Measurements further than outlier_threshold_m from the current estimate
        are rejected to prevent noisy multilateration from corrupting the filter.
        The _REJECTS_BEFORE_RESET-th rejection in a row resets the filter and
        initialises it from that measurement instead.
        """
        z = np.array([[x], [y]], dtype=float)
        now = time.monotonic()

        if not self._initialised:
            self._kf.x = np.array([[x], [y], [0.0], [0.0]], dtype=float)
            self._initialised = True
            self._last_mono = now
            self._rejected_in_a_row = 0
            self.last_update_accepted = True
            self._apply_dt(1.0)   # nominal seed step; velocity starts at 0
            self._kf.predict()
            self._kf.update(z)
            return float(self._kf.x[0, 0]), float(self._kf.x[1, 0])

        dt = now - (self._last_mono or now)
        dt = float(min(max(dt, self._DT_MIN_S), self._DT_MAX_S))
        self._last_mono = now
        self._apply_dt(dt)

        # Outlier rejection — compare against current smoothed position
        est_x = float(self._kf.x[0, 0])
        est_y = float(self._kf.x[1, 0])
        dist = float(np.sqrt((x - est_x) ** 2 + (y - est_y) ** 2))
        if dist > outlier_threshold_m:
            self._rejected_in_a_row += 1
            if self._rejected_in_a_row >= _REJECTS_BEFORE_RESET:
                # Consistently far from the estimate: the estimate is what's
                # wrong. Start again from this measurement.
                self.reset()
                return self.update(x, y, outlier_threshold_m)
            # Bad measurement — run predict only, do not corrupt state
            self._kf.predict()
            self.last_update_accepted = False
            return est_x, est_y

        self._rejected_in_a_row = 0
        self.last_update_accepted = True
        self._kf.predict()
        self._kf.update(z)
        return float(self._kf.x[0, 0]), float(self._kf.x[1, 0])

    def clamp_state(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
    ) -> None:
        """
        Clamp the Kalman filter's internal position state to floor bounds.
        Must be called after update() to prevent out-of-bounds values from
        propagating into future predictions via _kf.x.
        """
        if not self._initialised:
            return
        self._kf.x[0, 0] = float(np.clip(self._kf.x[0, 0], x_min, x_max))
        self._kf.x[1, 0] = float(np.clip(self._kf.x[1, 0], y_min, y_max))

    def reset(self) -> None:
        """Clear internal state so the next measurement re-initialises the filter
        from scratch. Call this when a beacon reappears after a long gap."""
        self._initialised = False
        self._last_mono = None
        self._rejected_in_a_row = 0
        self._kf.P = np.eye(4) * 10.0
        self._kf.x = np.zeros((4, 1), dtype=float)

    def predict_ahead(self, seconds: float = 3.0) -> Tuple[float, float]:
        """Project current state forward by `seconds` for pre-emptive collision alerting (FR4).
        Single-shot projection (F is linear for this CV model, so F(seconds) == looping)."""
        F = np.array([
            [1, 0, seconds, 0],
            [0, 1, 0, seconds],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=float)
        x_ahead = F @ self._kf.x
        return float(x_ahead[0, 0]), float(x_ahead[1, 0])
