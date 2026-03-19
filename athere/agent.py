"""Orchestrator agent: chat loop using Claude with geo tools."""

import anthropic

from .config import Config
from .tools import TOOLS, ToolHandler

MODEL = "claude-sonnet-4-6"

SYSTEM = """\
You are athere, a location-aware assistant that helps users post and discover \
geo-located messages on AT Protocol.

The user's location is encoded as an H3 hexagonal cell. You have tools to:
- Check the user's current H3 cell and coordinates
- Post a text message anchored to their location
- Read nearby posts from their current cell

Keep responses concise. When posting or reading, confirm what you did. \
If the user's message is ambiguous about intent (post vs. browse), ask briefly.
"""


def run(config: Config) -> None:
    """Start the interactive chat loop."""
    from . import atproto as ap

    client = ap.get_client(config)
    handler = ToolHandler(config, client)
    ai = anthropic.Anthropic(api_key=config.anthropic_api_key)  # key is guaranteed non-None by __main__

    messages: list[dict] = []
    print(f"athere — logged in as {config.handle}")
    print(f"Location: {config.lat}, {config.lng}  (H3 res {config.h3_res})")
    print("Type your message. Ctrl-C or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("you: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye.")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("bye.")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        # Agentic loop: keep calling until no more tool use
        while True:
            response = ai.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
            )

            # Collect assistant turn (may be mixed text + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Print the final text response
                for block in response.content:
                    if block.type == "text":
                        print(f"athere: {block.text}")
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = handler.dispatch(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            break
