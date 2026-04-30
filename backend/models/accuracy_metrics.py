from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AccuracyMetricsRecord:
    metrics_id: str
    run_id: str
    shift_id: str
    recorded_at: str            # ISO 8601
    mean_position_error_m: float
    rmse_m: float
    alert_precision: float
    alert_recall: float
    kalman_improvement_pct: float
    ap_count: int
    extra: Dict[str, Any] = field(default_factory=dict)
