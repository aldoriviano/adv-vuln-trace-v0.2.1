"""Small statistics helpers for the experimental grader (no third-party deps)."""
import math


def wilson(successes, n, z=1.96):
    """Wilson score interval for a binomial proportion; returns (low, high) or None."""
    if not n:
        return None
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))
