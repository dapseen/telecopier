"""MT5 utilities module.

This module handles MetaTrader5 availability and imports.
"""

import platform
import structlog

logger = structlog.get_logger(__name__)

# Try to import MetaTrader5, handle platform-specific cases
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    if platform.system() == "Windows" or (platform.system() == "Darwin" and platform.machine() == "x86_64"):
        print("\nMetaTrader5 package is not installed. Please install it manually:")
        print("pip install MetaTrader5==5.0.45")
    else:
        print("\nMetaTrader5 is not available on this platform.")
        print("This is expected on non-Windows platforms or non-x86_64 Mac systems.")
    print("The application will run in simulation mode.\n")

def get_mt5():
    """Get MetaTrader5 module if available.
    
    Returns:
        Optional[ModuleType]: MetaTrader5 module if available, None otherwise
    """
    if MT5_AVAILABLE:
        return mt5
    return None

def is_mt5_available() -> bool:
    """Check if MetaTrader5 is available.
    
    Returns:
        bool: True if MetaTrader5 is available, False otherwise
    """
    return MT5_AVAILABLE

def is_platform_supported() -> bool:
    """Check if current platform supports MetaTrader5.
    
    Returns:
        bool: True if platform is supported, False otherwise
    """
    return platform.system() == "Windows" or (platform.system() == "Darwin" and platform.machine() == "x86_64") 