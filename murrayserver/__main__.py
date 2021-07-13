
from .server import Server

from asyncio import get_event_loop


async def run():
    server = Server()
    await server.start()


if __name__ == '__main__':
    loop = get_event_loop()
    loop.run_until_complete(run())
    loop.run_forever()
