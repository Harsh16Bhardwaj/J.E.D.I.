import asyncio

import uvicorn


async def main() -> None:
    config = uvicorn.Config("backend.main:app", host="127.0.0.1", port=8000)
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
