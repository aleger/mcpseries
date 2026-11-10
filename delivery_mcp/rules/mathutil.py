import math


def round_half_up(value: float, digits: int = 0) -> float:
    """Round like JavaScript's Math.round (halves go up), not Python's banker's rounding."""
    scale = 10**digits
    return math.floor(value * scale + 0.5) / scale
