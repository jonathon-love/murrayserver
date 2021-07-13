
from aiohttp.web import Application
from aiohttp.web import static
from aiohttp.web import get
from aiohttp.web import run_app
from aiohttp.web import WebSocketResponse
from aiohttp.web import AppRunner
from aiohttp.web import TCPSite
from aiohttp import WSMsgType

import json
from asyncio import create_task
from asyncio import sleep

from os import path


class Server:

    def __init__(self):
        self._app = Application()
        self._app.add_routes([
            get('/coms', self._ws_handler),
            static('/', path.join(path.dirname(__file__), 'www')),
        ])
        self._runner = AppRunner(self._app)

        self._connections = [ ];

        self._state = {
            'status': 'waiting',
            'paddles': [
                { 'pos': 200, 'vel': 0 },
                { 'pos': 100, 'vel': 0 },
            ],
        }

    async def _run_loop(self):
        while True:
            state = json.dumps(self._state)
            for conn in self._connections:
                await conn.send_str(state)
            if self._state['status'] == 'waiting':
                await sleep(.5)
            else:
                await sleep(.1)

    async def _ws_handler(self, request):

        ws = WebSocketResponse()
        await ws.prepare(request)

        print('player connected')

        player_num = len(self._connections)
        self._connections.append(ws)

        if player_num == 1:  # two players
            self._state['status'] = 'playing'

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                self._state['paddles'][player_num] = data['paddle']
                print(f'received from player { player_num } the data { data }')

        return ws

    async def start(self):
        self._run_task = create_task(self._run_loop())

        # raise exception if _run_loop() throws
        self._run_task.add_done_callback(lambda t: t.result())

        await self._runner.setup()
        site = TCPSite(self._runner, '0.0.0.0', 8080)
        await site.start()
