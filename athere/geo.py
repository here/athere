"""H3 geospatial utilities."""

import h3


def latlng_to_cell(lat: float, lng: float, res: int) -> str:
    return h3.latlng_to_cell(lat, lng, res)


def cell_to_latlng(cell: str) -> tuple[float, float]:
    return h3.cell_to_latlng(cell)


def cell_resolution(cell: str) -> int:
    return h3.get_resolution(cell)


def cell_neighbors(cell: str, k: int = 1) -> list[str]:
    """Return all cells within k rings (includes the center cell)."""
    return list(h3.grid_disk(cell, k))


def cell_boundary_geojson(cell: str) -> dict:
    boundary = h3.cell_to_boundary(cell)  # list of (lat, lng)
    coords = [[lng, lat] for lat, lng in boundary]
    coords.append(coords[0])  # close ring
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {"h3Cell": cell, "h3Res": cell_resolution(cell)},
    }
