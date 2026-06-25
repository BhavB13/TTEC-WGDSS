from abc import ABC, abstractmethod
from typing import Any


class GridProvider(ABC):
    """
    Abstract interface for grid and generation data providers.

    Implementations may use mock data, SCADA systems,
    historians, or other operational data sources.
    """

    @abstractmethod
    async def get_generation_status(self) -> list[dict[str, Any]]:
        """
        Retrieve generation unit status information.
        """
        pass

    @abstractmethod
    async def get_grid_status(self) -> dict[str, Any]:
        """
        Retrieve overall grid status information.
        """
        pass