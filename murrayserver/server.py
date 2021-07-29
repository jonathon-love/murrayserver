
from aiohttp.web import Application
from aiohttp.web import static
from aiohttp.web import get
from aiohttp.web import run_app
from aiohttp.web import WebSocketResponse
from aiohttp.web import Response
from aiohttp.web import HTTPFound
from aiohttp.web import AppRunner
from aiohttp.web import TCPSite
from aiohttp import WSMsgType

import json
from asyncio import create_task
from asyncio import sleep
from uuid import uuid4
from functools import partial
import mimetypes

from os import path

from .game import Game


class Server:

    def __init__(self):
        self._app = Application()
        self._app.add_routes([
            get('/', self._enter),
            get(r'/{game_id}/{player_id}/coms', self._ws_handler),
            get(r'/{game_id}/{player_id}/{path}', self._get_assets),
        ])
        self._runner = AppRunner(self._app)

        game = Game()
        game.add_player()
        game.add_player()
        self._start_game(game)
        self._games = { '0': game }

        self._current_game_no = 1;
        self._current_game = None

    async def _enter(self, request):
        if self._current_game is None:
            self._current_game = Game()
            self._start_game(self._current_game)
            self._games[str(self._current_game_no)] = self._current_game
        game_id = self._current_game_no
        player_id = self._current_game.add_player()
        if self._current_game.ready():
            self._current_game = None
            self._current_game_no += 1

        return HTTPFound(f'/{ game_id }/{ player_id }/paddleGame.html')

    async def _get_assets(self, request):
        asset_path = request.match_info.get('path')
        asset_path = path.join(path.dirname(__file__), 'www', asset_path)

        try:
            with open(asset_path) as file:
                blob = file.read()

            content_type = 'application/octet-stream'
            mt = mimetypes.guess_type(asset_path)
            if mt[0] is not None:
                content_type = mt[0]

            return Response(body=blob, content_type=content_type)
        except:
            return Response(status='404', text='404')

    def _start_game(self, game):
        game_task = create_task(game.run())
        callback = partial(self._game_complete, game)
        game_task.add_done_callback(callback)

    def _game_complete(self, game, result):
        for key, value in self._games.items():
            if value == game:
                del self._games[key]
                break
        result.result()  # throw exception if necessary

    async def _ws_handler(self, request):

        game_id = request.match_info.get('game_id')
        player_id = request.match_info.get('player_id')
        game = self._games[game_id]

        ws = WebSocketResponse()
        await ws.prepare(request)
        await game.join(player_id, ws)

        return ws


    async def start(self):
        await self._runner.setup()
        site = TCPSite(self._runner, '0.0.0.0', 8080)
        await site.start()
