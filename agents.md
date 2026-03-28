# athere — Agents

## Purpose

Publish and read geo-located text content on the AT Protocol using H3 hexagonal cell IDs for efficient spatial indexing and neighbor queries. Records are stored in the user's existing Bluesky PDS under a custom lexicon namespace — invisible to the Bluesky social app layer.

---

## Implementation Status

| Area | Status | Notes |
|---|---|---|
| Lexicon definition | ✅ Done | `lexicons/community/athere/geo/post.json` — location field uses `community.lexicon.location.hthree` |
| H3 geo utilities | ✅ Done | `athere/geo.py` |
| AT Protocol client | ✅ Done | `athere/atproto.py` — create, list, delete |
| Tool definitions | ✅ Done | `athere/tools.py` — 3 tools wired |
| Orchestrator agent | ✅ Done | `athere/agent.py` — Claude chat loop |
| Config / env loading | ✅ Done | `athere/config.py` |
| Entry point | ✅ Done | `python -m athere` |
| Nearby posts (own) | ⚠️ Stub | Queries own repo only, H3 filter client-side |
| Nearby posts (community) | ❌ Planned | Requires Indexer + AppView |
| Nominatim geocoding | ❌ Planned | Location via env vars at v0 |

---

## Lexicon Namespace

**Base NSID:** `community.athere.geo`

**Location types:** [`community.lexicon.location`](https://lexicon.garden/browse/community.lexicon.location) — shared community lexicon for AT Protocol location data. athere uses `community.lexicon.location.hthree` as its primary location type.

### `community.athere.geo.post`

A text post anchored to an H3 cell. Stored on the user's Bluesky PDS. Does not appear on the Bluesky social network.

The `location` field is a union typed against the [`community.lexicon.location`](https://lexicon.garden/browse/community.lexicon.location) namespace. `community.lexicon.location.hthree` is the preferred type — the H3 cell resolution is implicit in the cell ID itself and does not need to be stored as a separate field.

```json
{
  "lexicon": 1,
  "id": "community.athere.geo.post",
  "defs": {
    "main": {
      "type": "record",
      "key": "tid",
      "record": {
        "type": "object",
        "required": ["text", "location", "createdAt"],
        "properties": {
          "text": {
            "type": "string",
            "maxGraphemes": 300,
            "maxLength": 3000
          },
          "location": {
            "type": "union",
            "refs": [
              "community.lexicon.location.hthree",
              "community.lexicon.location.geo"
            ],
            "description": "Geographic location of the post. Preferred: community.lexicon.location.hthree"
          },
          "createdAt": { "type": "string", "format": "datetime" },
          "langs":     { "type": "array", "items": { "type": "string", "format": "language" }, "maxLength": 3 }
        }
      }
    }
  }
}
```

#### `community.lexicon.location.hthree` (embedded type)

| Field | Type | Required | Description |
|---|---|---|---|
| `value` | string | ✅ | H3 cell ID (hex string, e.g. `87283082effffff`) |
| `name` | string | — | Human-readable location name |

Resolution guidance (H3 resolution is encoded in the cell ID):
- **res 5** (~250 km²) — city-region
- **res 7** (~5 km²) — neighborhood ← default
- **res 9** (~0.1 km²) — block
- **res 11** (~10 m²) — precise

Example PDS record payload:

```json
{
  "$type": "community.athere.geo.post",
  "text": "Hello from here",
  "location": {
    "$type": "community.lexicon.location.hthree",
    "value": "87283082effffff",
    "name": "Hayes Valley, San Francisco"
  },
  "createdAt": "2026-03-27T12:00:00Z",
  "langs": ["en"]
}
```

---

## Architecture

### v0 (current)

Single orchestrator agent with tools. No sub-agents. Claude interprets user intent and dispatches directly to tool handlers.

```
User (text chat)
      │
      ▼
┌─────────────────────────────────┐
│   Orchestrator (agent.py)       │  Claude API — claude-sonnet-4-6
│   natural language → tool calls │
└──────┬──────────────────────────┘
       │
       ├── get_my_location()         reads ATHERE_LAT/LNG → H3 cell
       ├── post_geo_message(text)    geo.py → atproto.py → Bluesky PDS
       └── get_nearby_posts(rings)   own repo only (v0 stub)
```

### Planned (community)

```
AT Protocol Relay (firehose)
        │  com.atproto.sync.subscribeRepos
        ▼
┌───────────────────┐
│  athere Indexer   │  filters community.athere.geo.post commits
│  (server process) │  verifies repo signatures
└────────┬──────────┘
         │  upsert { did, uri, cid, location.value, text, createdAt }
         ▼
┌───────────────────┐
│  Spatial DB       │  H3 cell → records index
│  (SQLite / pg)    │  k-ring queries: WHERE h3Cell IN (...)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  athere AppView   │  HTTP API consumed by get_nearby_posts tool
│  /posts?cell=&k=  │  paginated records by H3 proximity
└───────────────────┘
```

When the AppView is live, `get_nearby_posts` in `tools.py` swaps from querying the user's own repo to hitting the AppView API. No agent logic changes required.

---

## Agents

### Orchestrator

**Role:** Single top-level agent. Parses user intent, decides which tool(s) to call, composes the final response.

**Powered by:** Anthropic Claude API (`ANTHROPIC_API_KEY`). Without this the system is raw utility functions only — all three underlying modules (`geo.py`, `atproto.py`, `tools.py`) have no Anthropic dependency and can be called directly.

**Tools exposed:**

| Tool | What it does |
|---|---|
| `get_my_location` | Returns current H3 cell + lat/lng centroid from env config |
| `post_geo_message` | Encodes location → H3, wraps as `community.lexicon.location.hthree`, publishes to Bluesky PDS |
| `get_nearby_posts` | Fetches geo posts near current location (own repo at v0) |

**Notes:**
- Agentic loop continues until `stop_reason == "end_turn"` — handles multi-tool turns correctly.
- No sub-agents at v0; GeoEncoder and Publisher logic is inlined as tools.

---

### GeoEncoder (tools.py / geo.py)

**Role:** Resolves location to H3 cells and back.

**Functions:**

| Function | Inputs | Output |
|---|---|---|
| `latlng_to_cell` | `lat, lng, res` | H3 cell ID |
| `cell_to_latlng` | `cell_id` | `(lat, lng)` centroid |
| `cell_neighbors` | `cell_id, k` | list of cell IDs (k-ring) |
| `cell_boundary_geojson` | `cell_id` | GeoJSON Feature |

**Location at v0:** `ATHERE_LAT` / `ATHERE_LNG` env vars. No geocoding service required.
**Planned:** Nominatim integration for address → lat/lng (`resolve_address` tool).

**Library:** `h3 >= 4.0` (h3-py)

---

### Publisher (atproto.py)

**Role:** Authenticates to AT Protocol and writes / deletes `community.athere.geo.post` records.

**Functions:**

| Function | Inputs | Output |
|---|---|---|
| `get_client` | `config` | authenticated `atproto.Client` |
| `create_geo_post` | `client, text, h3_cell, name?, langs?` | `{uri, cid}` |
| `list_geo_posts` | `client, did, limit, cursor?` | `([records], next_cursor)` |
| `delete_geo_post` | `client, uri` | — |

**Notes:**
- Sync client used at v0 for simplicity. Switch to `AsyncClient` if concurrency becomes needed.
- `app_password` and `handle` from env only — never from chat input.
- Custom lexicon records sent as raw dicts (atproto SDK only generates models for `app.bsky.*`).
- **Publishing does not create any Bluesky social post.** Records are stored in the user's PDS repo under the `community.athere.geo.post` collection and are invisible to Bluesky's AppView.
- The `location` field is sent as a `community.lexicon.location.hthree` object with `$type` set explicitly. The H3 resolution is implicit in the cell ID value; `h3_res` no longer needs to be stored as a separate record field.

**Library:** `atproto >= 0.0.55` (atproto.blue)

---

### Reader (tools.py — stub)

**Role:** Queries for geo posts by spatial proximity.

**v0 behaviour:** Calls `com.atproto.repo.listRecords` on the authed user's own DID, then filters client-side by H3 cell membership. Returns only the user's own posts.

**Planned behaviour:** Queries the athere AppView HTTP API with `?cell=<h3>&rings=<k>`. Supports cross-user community discovery.

---

## Planned: Indexer + AppView

The AT Protocol Relay broadcasts every PDS commit via firehose. Bluesky's AppView ignores non-`app.bsky.*` records. Community discovery requires a dedicated indexer.

### Indexer responsibilities

- Subscribe to `com.atproto.sync.subscribeRepos` via WebSocket
- Filter ops where `collection == "community.athere.geo.post"`
- Handle `create`, `update`, `delete` commit ops
- Verify AT Protocol repo signatures (MST root)
- Upsert into spatial index keyed by `location.value` (the `community.lexicon.location.hthree` cell ID)

### AppView API

| Endpoint | Params | Returns |
|---|---|---|
| `GET /posts` | `cell, rings=1, limit=50, cursor?` | posts in k-ring |
| `GET /posts/{did}` | `limit, cursor?` | posts by author |

### Notes

- **No extra server needed to publish.** Records write to the user's existing Bluesky PDS.
- Indexer is only required for community discovery across users.
- SQLite + H3 `grid_disk` cell list is sufficient for low-to-mid volume. PostGIS optional for scale.
- Indexer deployment: single long-running process that hosts both the firehose subscriber and the AppView HTTP API is simplest for early deployment.

---

## Dependencies

```toml
anthropic = ">=0.40"       # Claude API — orchestrator only; not required for geo/atproto modules
atproto = ">=0.0.55"       # AT Protocol client
h3 = ">=4.0"               # H3 geospatial indexing
python-dotenv = ">=1.0"    # env var loading
```

Use `uv` to manage dependencies (not `pip`):

```sh
uv add anthropic
uv run python -m athere
```

---

## Environment Variables

```env
ATHERE_HANDLE=yourhandle.bsky.social   # AT Protocol handle
ATHERE_APP_PASSWORD=xxxx-xxxx-xxxx     # Bluesky App Password (not account password)
ANTHROPIC_API_KEY=sk-ant-...           # Claude API — orchestrator chat loop only
ATHERE_LAT=0.0                         # Current latitude (v0: set manually)
ATHERE_LNG=0.0                         # Current longitude (v0: set manually)
ATHERE_H3_RES=7                        # H3 resolution (default: 7, neighborhood scale)
```

---

## Open Questions

- [ ] **Lexicon namespace ownership** — `community.athere.geo` works for prototyping but a production namespace should resolve to a domain the project controls.
- [ ] **Multi-resolution posting** — now that `community.lexicon.location.hthree` encodes resolution implicitly in the cell ID, store a single `hthree` location per post or store multiple `hthree` entries (e.g., res 7 + res 9) to support queries at different zoom levels without re-encoding?
- [ ] **Indexer deployment** — single process (firehose subscriber + AppView HTTP API together) vs. separate services. Single process preferred for early deployment.
- [ ] **Nominatim** — self-hosted vs. public instance. Self-hosted preferred for production to avoid rate limits and data-sharing concerns.
- [ ] **Claude API optional** — decide whether the orchestrator chat loop is in scope for v0 or whether a direct CLI interface ships first.
