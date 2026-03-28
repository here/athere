"""AT Protocol client and record helpers."""

from datetime import datetime, timezone

from atproto import Client

from .config import Config

COLLECTION = "community.athere.geo.post"


def get_client(config: Config) -> Client:
    client = Client()
    client.login(config.handle, config.app_password)
    return client


def create_geo_post(
    client: Client,
    text: str,
    h3_cell: str,
    langs: list[str] | None = None,
) -> dict:
    """Publish a community.athere.geo.post record. Returns {uri, cid}."""
    record: dict = {
        "$type": COLLECTION,
        "text": text,
        "location": {"$type": "community.lexicon.location.hthree", "value": h3_cell},
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if langs:
        record["langs"] = langs

    resp = client.com.atproto.repo.create_record(
        {
            "repo": client.me.did,
            "collection": COLLECTION,
            "record": record,
        }
    )
    return {"uri": resp.uri, "cid": resp.cid}


def list_geo_posts(
    client: Client,
    did: str,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    """List geo posts for a DID. Returns (records, next_cursor)."""
    params: dict = {"repo": did, "collection": COLLECTION, "limit": limit}
    if cursor:
        params["cursor"] = cursor

    resp = client.com.atproto.repo.list_records(params)
    records = [{"uri": r.uri, "cid": r.cid, **r.value} for r in resp.records]
    return records, getattr(resp, "cursor", None)


def delete_geo_post(client: Client, uri: str) -> None:
    """Delete a geo post by record URI (at://did/collection/rkey)."""
    parts = uri.removeprefix("at://").split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid AT-URI: {uri}")
    _did, collection, rkey = parts
    client.com.atproto.repo.delete_record(
        {"repo": client.me.did, "collection": collection, "rkey": rkey}
    )
