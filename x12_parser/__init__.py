"""
X12-to-JSON Healthcare Parser Package.

Supports EDI X12 5010 transactions (270, 271, 278, 837, 835, 277, 275)
and embedded C-CDA XML clinical document integration.
"""

from .engine.base_parser import X12Parser
from .clinical_parsers.ccda_parser import CCDAParser

__version__ = "1.0.0"
__all__ = ["X12Parser", "CCDAParser"]
