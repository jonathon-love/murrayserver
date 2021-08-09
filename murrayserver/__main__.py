
from .server import Server

from asyncio import get_event_loop


async def start():
    server = Server()
    await server.start()


if __name__ == '__main__':
    try:
        loop = get_event_loop()
        loop.run_until_complete(start())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
