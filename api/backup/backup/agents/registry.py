# api/agents/registry.py
"""
Minimal agent registry for managing and executing agents.
"""
from typing import Callable, Dict, Optional, List

# Global registry to store agent functions
REGISTRY: Dict[str, Callable] = {}


def register(name: str, fn: Callable) -> None:
    """
    Register an agent function with a given name.
    
    Args:
        name: The agent name/identifier (e.g., "search.latest_from")
        fn: The agent function to register
    """
    REGISTRY[name] = fn


def get(name: str) -> Optional[Callable]:
    """
    Get an agent function by name.
    
    Args:
        name: The agent name/identifier
        
    Returns:
        The agent function if found, None otherwise
    """
    return REGISTRY.get(name)


def list_agents() -> List[str]:
    """
    Get list of all registered agent names.
    
    Returns:
        List of agent names
    """
    return list(REGISTRY.keys())


def get_all_agents() -> Dict[str, Callable]:
    """
    Get all registered agents.
    
    Returns:
        Dictionary of all registered agents
    """
    return REGISTRY.copy()
