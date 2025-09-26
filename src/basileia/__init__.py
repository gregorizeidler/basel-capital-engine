"""Basel Capital Engine - Comprehensive regulatory capital calculation framework."""

# Core engine and components
from .core.engine import BaselEngine
from .core.capital import Capital, CapitalComponents
from .core.exposure import Exposure, ExposureType
from .core.buffers import RegulatoryBuffers, BufferBreach

# Metrics and ratios
from .metrics.ratios import CapitalRatios, LeverageRatio

# Portfolio simulation
from .simulator.portfolio import PortfolioGenerator

# IFRS 9 Expected Credit Loss
from .accounting.ifrs9 import IFRS9Calculator, ECLResult

# Liquidity risk management
from .liquidity.lcr import LCRCalculator, LCRResult

# ICAAP and Pillar 2
from .icaap.processor import ICAAProcessor, ICAAResult

# Regulatory reporting
from .reporting.corep import COREPGenerator, COREPReport

__version__ = "0.1.0"
__author__ = "Basel Capital Engine Contributors"

__all__ = [
    # Core components
    "BaselEngine",
    "Capital",
    "CapitalComponents", 
    "Exposure",
    "ExposureType",
    "RegulatoryBuffers",
    "BufferBreach",
    
    # Metrics
    "CapitalRatios",
    "LeverageRatio",
    
    # Simulation
    "PortfolioGenerator",
    
    # IFRS 9 Accounting
    "IFRS9Calculator",
    "ECLResult",
    
    # Liquidity Risk
    "LCRCalculator", 
    "LCRResult",
    
    # ICAAP
    "ICAAProcessor",
    "ICAAResult",
    
    # Regulatory Reporting
    "COREPGenerator",
    "COREPReport",
]
