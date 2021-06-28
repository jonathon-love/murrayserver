
from aiohttp.web import Application
from aiohttp.web import static
from aiohttp.web import get
from aiohttp.web import run_app
from aiohttp.web import WebSocketResponse
from aiohttp import WSMsgType

from os import path


class Server:

    def __init__(self):
        self._app = Application()
        self._app.add_routes([
            get('/coms', self._ws_handler),
            static('/', path.join(path.dirname(__file__), 'www')),
        ])

    async def _ws_handler(self, request):
        print('Websocket connection starting')
        ws = WebSocketResponse()
        await ws.prepare(request)
        print('Websocket connection ready')

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                print(msg.data)
                await ws.send_str(msg.data + '/answer')

        print('Websocket connection closed')
        return ws

    def run(self):
        run_app(self._app)
