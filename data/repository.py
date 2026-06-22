"""data.repository — facade re-exporting land catalog data.

Provides:
    - lands_catalog_global: the in-memory land catalog dict
    - LandRepository: thin wrapper class around the catalog
    - get_repository(): factory returning a singleton LandRepository
    - get_land_by_id, list_lands: convenience functions
"""

from typing import Any, Dict, List, Optional

from api.routes.account_store import lands_catalog_global  # noqa: F401


class LandRepository:
    """Thin repository wrapper over the in-memory land catalog.

    Provides a stable interface for the map_service / rag_service
    layers that expect a repository with CRUD-like methods.
    """

    def __init__(self, catalog: Optional[Dict[str, Dict[str, Any]]] = None):
        self._catalog: Dict[str, Dict[str, Any]] = (
            catalog if catalog is not None else lands_catalog_global
        )

    def all_lands(self) -> List[Dict[str, Any]]:
        return list(self._catalog.values())

    def get(self, land_id: str) -> Optional[Dict[str, Any]]:
        return self._catalog.get(land_id)

    def add(self, land_id: str, data: Dict[str, Any]) -> None:
        self._catalog[land_id] = data

    def update(self, land_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        land = self._catalog.get(land_id)
        if land is None:
            return None
        land.update(patch)
        return land

    def delete(self, land_id: str) -> bool:
        return self._catalog.pop(land_id, None) is not None

    def count(self) -> int:
        return len(self._catalog)

    def filter(self, predicate) -> List[Dict[str, Any]]:
        return [l for l in self._catalog.values() if predicate(l)]


_repo_singleton: Optional[LandRepository] = None


def get_repository() -> LandRepository:
    """Return a shared LandRepository singleton."""
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = LandRepository()
    return _repo_singleton


def get_land_by_id(land_id: str) -> Optional[Dict[str, Any]]:
    return lands_catalog_global.get(land_id)


def list_lands(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    items = list(lands_catalog_global.values())
    return items[offset : offset + limit]


__all__ = [
    "lands_catalog_global",
    "LandRepository",
    "get_repository",
    "get_land_by_id",
    "list_lands",
]
