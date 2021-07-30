
import json
from asyncio import Event
from asyncio import create_task
from asyncio import wait
from asyncio import wait_for
from asyncio import FIRST_COMPLETED
from asyncio import sleep
from asyncio import TimeoutError

from collections import OrderedDict

from .stream import ProgressStream


class Game:
    def __init__(self):
        self._joined = { '0': False, '1': False }
        self._conns = { '0': None, '1': None }
        self._send_update = OrderedDict({ '0': Event(), '1': Event() })
        self._receive_update = Event()
        self._ready = Event()
        self._blocks = [ 'nonCol', 'col', 'com' ]
        self._state = {
            'player_id': None,
            'status': 'waiting',
            'block_type': None,
            'players': {
                '0': { 'pos': 200, 'status': 'notReady' },
                '1': { 'pos': 100, 'status': 'notReady' },
            },
            'balls': [

            ]
        }


    def add_player(self):
        player_id = None
        if not self._joined['0']:
            self._joined['0'] = True
            player_id = '0'
        else:
            self._joined['1'] = True
            player_id = '1'
        if self._joined['0'] and self._joined['1']:
            self._ready.set()
        return player_id

    async def join(self, player_id, ws):

        print(f'player { player_id } connected')

        if not self._joined[player_id]:
            self._joined[player_id] = True
            if self._joined['0'] and self._joined['1']:
                self._ready.set()

        async def read():
            async for msg in ws:
                #if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                self._state['players'][player_id].update(data)
                self._receive_update.set()

        async def write():
            send_event = self._send_update[player_id]
            send_event.set()

            while True:
                await send_event.wait()
                send_event.clear()
                self._state['player_id'] = player_id
                state = json.dumps(self._state)
                await ws.send_str(state)


        write_task = create_task(write())
        read_task = create_task(read())

        done, pending = await wait({ read_task, write_task }, return_when=FIRST_COMPLETED)

        for p in pending:
            p.cancel()

        for d in done:
            d.result()

    def ready(self):
        return self._ready.is_set()

    def send(self):
        for player_id, event in self._send_update.items():
            event.set()
        self._send_update.move_to_end(player_id, last=False)

    async def receive(self):
        await self._receive_update.wait()
        self._receive_update.clear()

    async def run(self):

        await self._ready.wait()
        state = self._state

        print('ready!')

        for block_no, block in enumerate(self._blocks):
            state['status'] = 'reading'  # instructions
            state['players']['0']['status'] = 'notReady'
            state['players']['1']['status'] = 'notReady'
            state['block_type'] = block

            self.send()

            print(f'block { block_no }, awaiting players')

            while True:
                await self.receive()

                print(f'player 0 { state["players"]["0"]["status"] }')
                print(f'player 1 { state["players"]["1"]["status"] }')

                if (state['players']['0']['status'] == 'ready'
                        and state['players']['1']['status'] == 'ready'):
                    break

            state['players']['0']['pos'] = 300
            state['players']['1']['pos'] = 300
            state['status'] = 'playing'
            self.send()

            print(f'block { block_no }, begun!')

            async def play():
                while True:
                    await self.receive()
                    self.send()

            try:
                await wait_for(play(), 20)
            except TimeoutError:
                pass

            print(f'block { block_no }, complete!')
