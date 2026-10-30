"""
Packet aggregation strategies for TinyFlow.
"""

from tinyflow.strategies.base import BaseAggregationStrategy
from tinyflow.strategies.immediate import ImmediateStrategy
from tinyflow.strategies.fixed import FixedIntervalBatchingStrategy
from tinyflow.strategies.adaptive import AdaptiveAggregationStrategy

__all__ = [
    "BaseAggregationStrategy",
    "ImmediateStrategy",
    "FixedIntervalBatchingStrategy",
    "AdaptiveAggregationStrategy",
]
