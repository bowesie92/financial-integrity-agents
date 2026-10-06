"""Benford helpers used by the generator tests and reports."""
import math
from collections import Counter


def first_digit(x):
    s = f"{abs(float(x)):.2f}".lstrip("0.")
    return int(s[0]) if s else 0


def first_digit_mad(amounts):
    amounts = [a for a in amounts if float(a) >= 1.0]
    n = len(amounts)
    counts = Counter(first_digit(a) for a in amounts)
    return sum(abs(counts.get(d, 0) / n - math.log10(1 + 1 / d)) for d in range(1, 10)) / 9, n
