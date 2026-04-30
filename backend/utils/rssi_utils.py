def rssi_to_distance(rssi: float, tx_power: float, path_loss_exponent: float) -> float:
    """Convert RSSI (dBm) to metres using LDPL: d = 10^((TxPower - RSSI) / (10 * n))."""
    return 10.0 ** ((tx_power - rssi) / (10.0 * path_loss_exponent))


def distance_to_rssi(distance: float, tx_power: float, path_loss_exponent: float) -> float:
    """Inverse LDPL — back-calculate the theoretical RSSI at a given distance."""
    import math
    distance = max(distance, 0.01)
    return tx_power - 10.0 * path_loss_exponent * math.log10(distance)
