"""Tool definitions and handlers for the orchestrator agent."""

import json

from atproto import Client

from . import atproto as ap
from . import geo
from .config import Config

# ── Tool schemas (Claude API format) ────────────────────────────────────────

TOOLS = [
    {
        "name": "get_my_location",
        "description": (
            "Return the user's current location: H3 cell ID, resolution, "
            "and lat/lng centroid."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "post_geo_message",
        "description": (
            "Publish a text message anchored to the user's current location "
            "as a community.athere.geo.post record on AT Protocol."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message text (max 300 graphemes).",
                },
                "langs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional BCP-47 language tags, e.g. ['en'].",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_nearby_posts",
        "description": (
            "Fetch geo posts near the user's current location. "
            "rings=0 returns only the exact cell; rings=1 includes the 6 "
            "neighboring cells (default); rings=2 expands further."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rings": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 4,
                    "description": "H3 k-ring radius.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max posts to return per cell query.",
                },
                "res": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 15,
                    "description": "H3 resolution override. Defaults to ATHERE_H3_RES.",
                },
            },
            "required": [],
        },
    },
]


# ── Tool handlers ────────────────────────────────────────────────────────────

class ToolHandler:
    def __init__(self, config: Config, client: Client):
        self.config = config
        self.client = client

    def dispatch(self, name: str, inputs: dict) -> str:
        """Route a tool call and return a JSON string result."""
        match name:
            case "get_my_location":
                return json.dumps(self._get_my_location())
            case "post_geo_message":
                return json.dumps(self._post_geo_message(**inputs))
            case "get_nearby_posts":
                return json.dumps(self._get_nearby_posts(**inputs))
            case _:
                return json.dumps({"error": f"Unknown tool: {name}"})

    def _get_my_location(self) -> dict:
        cell = geo.latlng_to_cell(self.config.lat, self.config.lng, self.config.h3_res)
        lat, lng = geo.cell_to_latlng(cell)
        return {
            "h3Cell": cell,
            "h3Res": self.config.h3_res,
            "lat": lat,
            "lng": lng,
        }

    def _post_geo_message(self, text: str, langs: list[str] | None = None) -> dict:
        cell = geo.latlng_to_cell(self.config.lat, self.config.lng, self.config.h3_res)
        return ap.create_geo_post(self.client, text, cell, langs)

    def _get_nearby_posts(self, rings: int = 1, limit: int = 50, res: int | None = None) -> dict:
        effective_res = res if res is not None else self.config.h3_res
        cell = geo.latlng_to_cell(self.config.lat, self.config.lng, effective_res)
        cells = geo.cell_neighbors(cell, k=rings)

        all_posts: list[dict] = []
        for c in cells:
            # TODO: replace with a proper spatial index query when available
            # For now, query the authenticated user's own posts as a v0 stub
            posts, _ = ap.list_geo_posts(self.client, self.client.me.did, limit=limit)
            matching = [p for p in posts if p.get("location", {}).get("value") == c]
            all_posts.extend(matching)

        return {"h3Res": effective_res, "cells_searched": len(cells), "posts": all_posts}
