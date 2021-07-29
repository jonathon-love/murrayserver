
import json
from asyncio import Event
from asyncio import create_task
from asyncio import wait
from asyncio import FIRST_COMPLETED

from collections import OrderedDict

from .stream import ProgressStream


class Game:
    def __init__(self):
        self._n_players = 0
        self._conns = { '0': None, '1': None }
        self._send_update = OrderedDict({ '0': Event(), '1': Event() })
        self._receive_update = Event()
        self._ready = Event()
        self._blocks = [ 'nonCol', 'col', 'com' ]
        self._state = {
            'player_id': None,
            'status': None,
            'block_type': None,
            'players': {
                '1': { 'pos': 200, 'status': 'notReady' },
                '2': { 'pos': 100, 'status': 'notReady' },
            },
            'balls': [

            ]
        }


    def add_player(self):
        player_id = self._n_players
        self._n_players += 1
        if self._n_players == 2:
            self._ready.set()
        return player_id

    async def join(self, player_id, ws):

        print(f'player { player_id } connected')

        async def read():
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    self._state[player_id] = data
                    self._receive_update.set()

        async def write():
            send_event = self._send_update[player_id]
            while True:
                await send_event.wait()
                send_event.clear()
                state['player_id'] = player_id
                state = json.dumps(state)
                await ws.send_str(state)


        write_task = create_task(write())
        read_task = create_task(read())

        done, pending = await wait({ read_task, write_task }, return_when=FIRST_COMPLETED)

        for p in pending:
            p.cancel()

        for d in done:
            d.result()

    def ready(self):
        return self._n_players >= 2

    def send(self):
        for player_id, event in self._send_update.items():
            event.set()
        self._send_update.move_to_end(player_id, last=False)

    async def receive(self):
        await self._receive_update.wait()
        self._receive_update.clear()

    async def run(self):

        print('running!')

        await self._ready.wait()
        state = self._state

        print('ready!')

        for block_no, block in enumerate(self._blocks):
            state['status'] = 'waiting'  # instructions
            state['players']['1']['status'] = 'notReady'
            state['players']['2']['status'] = 'notReady'

            print(f'block { block_no }, awaiting players')

            while True:
                await self.receive()
                if (state['players']['1']['status'] == 'ready'
                        and state['players']['2']['status'] == 'ready'):
                    break

            state['status'] = 'playing'
            self.send()

            print(f'block { block_no }, begun!')
