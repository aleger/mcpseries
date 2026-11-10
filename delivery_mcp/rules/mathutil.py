import math


def round_half_up(value: float, digits: int = 0) -> float:
    scale = 10**digits
    return math.floor(value * scale + 0.5) / scale
