from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import geopandas as gpd


def map_stations_to_nearest_nodes(
    stations_gdf: "gpd.GeoDataFrame",
    nodes_gdf: "gpd.GeoDataFrame",
    node_id_col: str = "node_id",
    metric_crs: str = "EPSG:3857",
) -> "gpd.GeoDataFrame":
    """Map charging station geometries to nearest road nodes.

    Parameters
    ----------
    stations_gdf:
        GeoDataFrame containing station geometries.
    nodes_gdf:
        GeoDataFrame containing road node geometries and node id column.
    """
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError(
            "geopandas is required for station-node mapping. "
            "Install in conda env, e.g. conda install -c conda-forge geopandas"
        ) from exc

    if stations_gdf.empty:
        cols = list(stations_gdf.columns) + [node_id_col, "nn_distance_m"]
        return gpd.GeoDataFrame(columns=cols, geometry="geometry", crs=stations_gdf.crs)

    if node_id_col not in nodes_gdf.columns:
        raise ValueError(f"nodes_gdf missing required column '{node_id_col}'")

    if stations_gdf.crs is None:
        stations_gdf = stations_gdf.set_crs("EPSG:4326", allow_override=True)
    if nodes_gdf.crs is None:
        nodes_gdf = nodes_gdf.set_crs("EPSG:4326", allow_override=True)

    stations_metric = stations_gdf.to_crs(metric_crs)
    nodes_metric = nodes_gdf[[node_id_col, "geometry"]].to_crs(metric_crs)

    joined = gpd.sjoin_nearest(
        stations_metric,
        nodes_metric,
        how="left",
        distance_col="nn_distance_m",
    )

    # Remove helper join column created by sjoin_nearest.
    if "index_right" in joined.columns:
        joined = joined.drop(columns=["index_right"])

    return joined.to_crs(stations_gdf.crs)
