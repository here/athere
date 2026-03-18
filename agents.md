# athere — Agents

## Purpose

Publish and read geo-located text content on the AT Protocol using a new PDS lexicon namespace. Location is encoded as H3 hexagonal cell IDs rather than raw coordinates, enabling efficient spatial indexing and neighbor queries.

---

## Lexicon Namespace

**Base NSID:** `community.athere.geo`

### `community.athere.geo.post`

A text post anchored to an H3 cell.

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
        "required": ["text", "h3Cell", "h3Res", "createdAt"],
        "properties": {
          "text":      { "type": "string", "maxLength": 3000 },
          "h3Cell":    { "type": "string", "description": "H3 cell ID (hex string)" },
          "h3Res":     { "type": "integer", "minimum": 0, "maximum": 15 },
          "createdAt": { "type": "string", "format": "datetime" },
          "langs":     { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  }
}
```

Resolution guidance:
- **res 5** (~250 km²) — city-region
- **res 7** (~5 km²) — neighborhood
- **res 9** (~0.1 km²) — block
- **res 11** (~10 m²) — precise

---

## Architecture

```
User (text chat)
      │
      ▼
┌─────────────────────┐
│   Orchestrator      │  ← Claude Agent SDK top-level agent
│   (chat interface)  │
└──────┬──────────────┘
       │ routes intent
       ├──────────────────────────────────┐
       ▼                                  ▼
┌──────────────┐                 ┌─────────────────┐
│  GeoEncoder  │                 │    Publisher     │
│  Agent       │                 │    Agent         │
└──────┬───────┘                 └────────┬─────────┘
       │ h3_cell, h3_res                  │ creates record
       │                                  ▼
       │                         ┌─────────────────┐
       │                         │  atproto PDS    │
       │                         │  (atproto.blue) │
       │                         └────────┬─────────┘
       │                                  │
       └─────────────────────────────────►│
                                          ▼
                                 ┌─────────────────┐
                                 │   Reader Agent  │
                                 │   (spatial      │
                                 │    queries)     │
                                 └─────────────────┘
```

---

## Agents

### Orchestrator

**Role:** Top-level chat agent. Parses user intent from text, delegates to sub-agents, returns responses.

**Capabilities:**
- Parse location references from natural language ("near downtown Portland", "at 45.5,-122.6")
- Route to GeoEncoder → Publisher for posting
- Route to GeoEncoder → Reader for browsing posts near a location
- Handle clarifying questions when location is ambiguous

**SDK pattern:** Main `Agent` with tools that invoke sub-agents as functions.

---

### GeoEncoder Agent

**Role:** Resolves location inputs to H3 cells and back.

**Tools:**

| Tool | Inputs | Output |
|------|--------|--------|
| `latlng_to_cell` | `lat, lng, res` | H3 cell ID |
| `cell_to_latlng` | `cell_id` | `(lat, lng)` centroid |
| `cell_neighbors` | `cell_id, k_rings` | list of cell IDs |
| `cell_to_boundary` | `cell_id` | GeoJSON polygon |
| `resolve_address` | `address: str` | `(lat, lng)` via geocoding |

**Notes:**
- Default resolution: 7 (neighborhood scale)
- For publishing, cell is stored at the resolution the user intends; readers can traverse rings for broader queries.
- **v0**: User's current location supplied via `ATHERE_LAT` / `ATHERE_LNG` env vars at startup. The orchestrator calls `get_my_location()` as a tool; no geocoding needed.
- **Planned**: Nominatim integration for address → lat/lng resolution.

**Library:** `h3` (h3-py, `pip install h3`)

---

### Publisher Agent

**Role:** Authenticates to AT Protocol and writes `community.athere.geo.post` records.

**Tools:**

| Tool | Inputs | Output |
|------|--------|--------|
| `atproto_login` | `handle, app_password` | session client |
| `create_geo_post` | `text, h3_cell, h3_res, langs?` | record URI + CID |
| `delete_geo_post` | `record_uri` | confirmation |

**Notes:**
- Use `atproto` async client (`AsyncClient`) to avoid blocking.
- `app_password` loaded from env (`ATHERE_APP_PASSWORD`), never from user chat input.
- Handle is loaded from env (`ATHERE_HANDLE`).
- Record `createdAt` is set server-side at publish time.

**Library:** `atproto` (atproto.blue, `pip install atproto`)

---

### Reader Agent

**Role:** Queries the PDS for geo posts by spatial proximity.

**Tools:**

| Tool | Inputs | Output |
|------|--------|--------|
| `get_posts_by_cell` | `h3_cell, include_rings=0` | list of records |
| `get_posts_by_latlng` | `lat, lng, res, include_rings=0` | list of records |
| `get_posts_by_author` | `did, limit` | list of records |

**Notes:**
- Querying by H3 cell uses `com.atproto.repo.listRecords` filtered by lexicon + post-query cell matching (no server-side spatial index at v0).
- `include_rings=1` expands to the 7-cell neighborhood (cell + 6 neighbors); `include_rings=2` gives 19 cells, etc.
- Pagination handled via cursor.

---

## Dependencies

```toml
[dependencies]
python = ">=3.11"
h3 = ">=4.0"
atproto = ">=0.0.55"
anthropic = ">=0.40"          # Claude Agent SDK
python-dotenv = ">=1.0"
```

---

## Environment Variables

```env
ATHERE_HANDLE=yourhandle.bsky.social
ATHERE_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Planned: Indexer + AppView

The AT Protocol Relay broadcasts every PDS commit to subscribers via the firehose (`com.atproto.sync.subscribeRepos`). Bluesky's own AppView ignores non-`app.bsky.*` records, so community cross-user discovery requires a dedicated indexer.

### Data flow

```
AT Protocol Relay (firehose)
        │
        │  com.atproto.sync.subscribeRepos
        ▼
┌───────────────────┐
│  athere Indexer   │  filters community.athere.geo.post commits
│  (server process) │  verifies repo signatures
└────────┬──────────┘
         │  upsert { did, uri, cid, h3Cell, h3Res, text, createdAt }
         ▼
┌───────────────────┐
│  Spatial DB       │  H3 cell → records index
│  (SQLite / pg)    │  supports k-ring queries: WHERE h3Cell IN (...)
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  athere AppView   │  HTTP API consumed by Reader Agent
│  /posts?cell=&k=  │  returns paginated records by H3 proximity
└───────────────────┘
```

### Indexer responsibilities

- Subscribe to firehose via WebSocket
- Filter ops where `collection == "community.athere.geo.post"`
- Handle `create`, `update`, `delete` commit ops
- Verify AT Protocol repo signature (MST root)
- Upsert into spatial index keyed by `h3Cell`

### AppView API (planned)

| Endpoint | Params | Returns |
|---|---|---|
| `GET /posts` | `cell, rings=1, limit=50, cursor?` | posts in k-ring |
| `GET /posts/{did}` | `limit, cursor?` | posts by author |

### Impact on Reader Agent

At v0, `get_nearby_posts` queries only the authed user's own repo (client-side H3 filter). Once the AppView is available, the tool swaps to hitting the AppView API — no agent logic changes required, only the tool implementation.

### Notes

- **No extra server needed to publish** — records write to the user's existing Bluesky PDS and are invisible to the Bluesky social app layer.
- The indexer is only required for community discovery across users.
- SQLite + H3's `grid_disk` cell list is sufficient for low-to-mid volume; PostGIS optional for scale.

---

## Open Questions

- [ ] Should the lexicon namespace be `community.athere.geo` or use a custom domain (requires owning the domain for DID resolution)?
- [ ] Address geocoding: rely on user-supplied lat/lng at v0, or integrate a geocoding service (Nominatim/OSM is free and self-hostable)?
- [ ] Multi-resolution posting: store a single resolution per post, or store multiple (e.g., res 7 + res 9) to support range queries?
- [ ] Indexer deployment: long-running process alongside AppView, or separate services?
