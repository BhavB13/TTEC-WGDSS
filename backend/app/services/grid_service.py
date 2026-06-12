from app.providers.grid_provider import GridProvider


class GridService:
    """
    Service layer for grid and generation operations.
    """

    def __init__(self, provider: GridProvider):
        self.provider = provider

    async def get_generation_status(self):
        return await self.provider.get_generation_status()

    async def get_grid_status(self):
        return await self.provider.get_grid_status()
    