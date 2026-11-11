"""Sign in through the spike server (browser opens) and call read_mob_210. Prints no tokens."""

import asyncio
import json

from fastmcp import Client


async def main() -> None:
    async with Client("http://localhost:8000/mcp", auth="oauth") as client:
        result = await client.call_tool("read_mob_210", {}, raise_on_error=False)
        print("is_error:", result.is_error)
        print(json.dumps(result.structured_content or [c.text for c in result.content], indent=2))


asyncio.run(main())
