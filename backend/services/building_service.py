from typing import Any, Dict, List, Optional

from repositories.building_repository import building_repository
from repositories.floor_repository import floor_repository
from services.floor_service import floor_service
from models.building import BuildingRecord


class BuildingService:

    def get_all(self) -> List[Dict[str, Any]]:
        return building_repository.get_all()

    def create(self, user_id: str, name: str, description: str) -> BuildingRecord:
        return building_repository.create(user_id, name, description)

    def rename(self, building_id: str, name: str) -> None:
        building_repository.update(building_id, {"name": name})

    def delete(self, building_id: str) -> None:
        # Delete all floors (and their zones and floorplan images via floor_service)
        floors = floor_repository.get_all(building_id)
        for floor in floors:
            floor_service.delete(building_id, floor.id)
        building_repository.delete(building_id)


building_service = BuildingService()
