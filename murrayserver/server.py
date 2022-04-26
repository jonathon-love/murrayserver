
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
from time import time

from .game import Game
from .bot import Bot
from .bot import Bot2
from .bot import BotQ

class Server:

    def __init__(self):
        self._app = Application()
        self._app.add_routes([
            get('/', self._enter),
            get('/{game_id}/', self._enter_game),
            get(r'/{game_id}/{player_id}/coms', self._ws_handler),
            get(r'/{game_id}/{player_id}/{path}', self._get_assets),
        ])
        self._runner = AppRunner(self._app)

        self._games = { }

        self._current_game_no = 0
        self._current_game = None

    async def _enter(self, request):
        if self._current_game is None:
            self._current_game = Game(self._current_game_no)
            self._start_game(self._current_game)
            self._games[str(self._current_game_no)] = self._current_game

        game_id = self._current_game_no
        player_id = self._current_game.add_player()

        # if we state that a bot should be used then set up to use the bot. Otherwise, play HvH
        against_bot = request.query.get('b','0') == '1'

        if against_bot:
            bot_types = ['d','d','c','c','q','q']
            pretend_to_be_humans = [False, True, False, True, False, True]

            bot_type = bot_types[game_id % len(bot_types)]
            pretend_to_be_human = pretend_to_be_humans[game_id % len(pretend_to_be_humans)]

            print(f'bot type is {bot_type} and human status is {pretend_to_be_human}')

        if bot_type == 'd':
            self._bot = Bot(pretend_to_be_human, bot_type)
            self._bot.start(self._current_game)
        elif bot_type == 'c':
            self._bot = Bot2(pretend_to_be_human, bot_type)
            self._bot.start(self._current_game)
        elif bot_type == 's':
            #self._bot = BotSmart(pretend_to_be_human)
            #self._bot.start(self._current_game)
            pass
        elif bot_type == 'q':
            self._bot = BotQ(pretend_to_be_human, bot_type)
            self._bot.start(self._current_game)

        if self._current_game.ready():
            self._current_game = None
            self._current_game_no += 1

        return HTTPFound(f'/{ game_id }/{ player_id }/paddleGame.html?{ request.query_string }')

    async def _enter_game(self, request):
        game_id = request.match_info.get('game_id')
        game = self._games.get(game_id)
        if not game:
            game = Game(game_id)
            self._start_game(game)
            self._games[game_id] = game
        player_id = game.add_player()

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
