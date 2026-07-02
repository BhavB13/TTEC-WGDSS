from abc import ABC, abstractmethod

from app.schemas.grid import GenerationUnitResponse, GridStatusResponse


class GridProvider(ABC):
    """
    Abstract interface for grid and generation data providers.

    Implementations may use mock data, SCADA systems,
    historians, or other operational data sources.
    """

    @abstractmethod
    async def get_generation_status(self) -> list[GenerationUnitResponse]:
        """
        Retrieve generation unit status information.
        """
        pass

    @abstractmethod
    async def get_grid_status(self) -> GridStatusResponse:
        """
        Retrieve overall grid status information.
        """
        pass
