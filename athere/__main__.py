import sys

from .config import Config
from . import atproto as ap
from .tools import ToolHandler


def main() -> None:
    config = Config()
    client = ap.get_client(config)
    handler = ToolHandler(config, client)

    # Direct subcommands — no agent required
    if len(sys.argv) >= 3 and sys.argv[1] == "post":
        text = " ".join(sys.argv[2:])
        result = handler.dispatch("post_geo_message", {"text": text})
        print(result)
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "location":
        print(handler.dispatch("get_my_location", {}))
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "nearby":
        print(handler.dispatch("get_nearby_posts", {}))
        return

    # Agent mode (requires valid ANTHROPIC_API_KEY)
    if not config.anthropic_api_key:
        print("Usage: python -m athere post <text>")
        print("       python -m athere location")
        print("       python -m athere nearby")
        print("Set ANTHROPIC_API_KEY to enable the interactive chat agent.")
        return

    from .agent import run
    run(config)


if __name__ == "__main__":
    main()
