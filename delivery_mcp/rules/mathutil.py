import math


def round_half_up(value: float, digits: int = 0) -> float:
    """Round with halves going up (2.5 -> 3). Python's round() sends halves to the nearest even number."""
    scale = 10**digits
    return math.floor(value * scale + 0.5) / scale
