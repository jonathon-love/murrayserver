
import json
from asyncio import Event
from asyncio import create_task
from asyncio import wait
from asyncio import wait_for
from asyncio import FIRST_COMPLETED
from asyncio import sleep
from asyncio import TimeoutError

from collections import OrderedDict
from random import randint
from random import shuffle
import math

from .stream import ProgressStream


class Game:
    def __init__(self):
        self._joined = { '0': False, '1': False }
        self._conns = { '0': None, '1': None }
        self._send_update = OrderedDict({ '0': Event(), '1': Event() })
        self._receive_update = Event()
        self._ready = Event()
        self._blocks = [ ]
        
        drtWidth = 800
        width  = drtWidth * 0.9
        height = 600
        pWidth = width * 0.10
        pHeight= pWidth* 0.12
        bRad   = pHeight*0.90

        self._dim = {
            ## for 800x600
            'frameWidth': width, # The DRT rect is the full screen and the game frame is drawn over the top of it.
            'frameHeight': height,
            'frameLeft': drtWidth*0.05,
            'frameRight': drtWidth*0.95,
            'frameTop': 0,
            'frameBottom': height,
            'paddleY': height - pHeight*3,
            'p1Start': drtWidth*0.33 - (pWidth/2),
            'p2Start': drtWidth*0.67 + (pWidth/2),
            'ballX': [drtWidth/2 - bRad*4, drtWidth/2, drtWidth/2 + bRad*4],
            'ballY': (height - pHeight*3) - bRad,
            'pWidth': pWidth,
            'pHeight': pHeight,
            'ballR': bRad,
        }

        # block_types = [ 'nonCol', 'col', 'com' ]
        block_types = ['nonCol', 'nonCol', 'nonCol']
        n_balls = [
            1, 1, 1, 1,\
                3, 3, 3, 3,\
                    6, 6, 6, 6,\
                        9, 9, 9, 9\
                            ]

        shuffle(block_types)
        shuffle(n_balls)

        for block_type in block_types:
            for n in n_balls:
                self._blocks.append({ 'block_type': block_type, 'n_balls': n })

        self._state = {
            'player_id': None,
            'status': 'waiting',
            'block': self._blocks[0],
            'players': {
                '0': {
                    'pos': self._dim['p1Start'], 
                    'status': 'notReady', 
                    'drtResp': False,
                    'hits': 0,
                    'miss': 0,
                    },
                '1': {
                    'pos': self._dim['p2Start'],
                    'status': 'notReady',
                    'drtResp': False,
                    'hits': 0,
                    'miss': 0,
                    },
            },
            'balls': [ ],
            'drt': {
                'onset': [], ## change trial duration as necessary
                'dispTime': [],
                'window': [],
                'resp1': False, ## you've got this in 'players', too. Take (some) care w redundancy
                'resp2': False,
                },
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

    async def update(self):
        try:
            timeout = None
            if self._state['status'] == 'playing':
                timeout = .02
            await wait_for(self._receive_update.wait(), timeout)
            self._receive_update.clear()
        except TimeoutError:
            pass

        if self._state['status'] == 'playing':
            ## Currently using the times set by the state earlier and the timer in the client to show the stim but I feel like that is not correct.
            ## if trialtime <= drt['onset'][drt['progress']] and >= drt['dispTime'][drt['progress']] and (not drt['resp1'] and not drt['resp2'] -- both need to be false for it to show)
                ## drt['status'] = True

            for ball in self._state['balls']:
                ball['x'] += ball['speed'] * math.cos(ball['angle'])
                ball['y'] += ball['speed'] * math.sin(ball['angle'])
                if ball['x'] <= self._dim['frameLeft']+self._dim['ballR'] or ball['x'] >= self._dim['frameRight']-self._dim['ballR']:
                    ball['angle'] = math.pi -ball['angle']
                if ball['y'] - self._dim['ballR'] <= self._dim['frameTop']:
                    ball['angle'] = -ball['angle']
                if ball['y'] >= self._dim['frameBottom'] - 0.5*self._dim['ballR']:
                    ball['y'] = self._dim['frameTop'] + self._dim['ballR']
                    if self._state['block']['block_type'] == 'nonCol':
                        if ball['id'] < 9:
                            self._state['players']['0']['miss'] += 1
                        else:
                            self._state['players']['1']['miss'] += 1
                    else:
                        self._state['players']['0']['miss'] += 1
                        self._state['players']['1']['miss'] += 1

                # If a player is in the right spot at the right ?time?
                if self._state['block']['block_type'] == 'nonCol':
                    if self._state['player_id'] == "0" and ball['id'] < 9:
                        if ball['y']+self._dim['ballR'] > self._dim['paddleY'] and ball['y'] < self._dim['paddleY']+self._dim['ballR']: 
                            if ball['x'] + self._dim['ballR'] > self._state['players']['0']['pos'] and ball['x'] < self._state['players']['0']['pos'] + self._dim['pWidth'] + self._dim['ballR']: ## approx paddle width - much to account for here.
                                impact = (ball['x'] + self._dim['ballR']/2) - (self._state['players']['0']['pos']+ (self._dim['pWidth']/2))
                                offset = impact/(self._dim['pWidth']/2)/2
                                if (-ball['angle']+offset) <= -math.radians(155) or (-ball['angle'] + offset >= -math.radians(35)):
                                    ball['angle'] = -ball['angle']
                                else:
                                    ball['angle'] = -ball['angle']+offset
                                ball['y'] = self._dim['paddleY']-self._dim['ballR']
                                self._state['players']['0']['hits'] += 1

                    if self._state['player_id'] == "1" and ball['id'] >= 9:
                        if ball['y']+self._dim['ballR'] > self._dim['paddleY'] and ball['y'] < self._dim['paddleY']+self._dim['ballR']: 
                            if ball['x'] + self._dim['ballR'] > self._state['players']['1']['pos'] and ball['x'] < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']: ## approx paddle width - much to account for here.
                                impact = (ball['x'] + self._dim['ballR']/2) - (self._state['players']['1']['pos']+ (self._dim['pWidth']/2))
                                offset = impact/(self._dim['pWidth']/2)/2
                                if (-ball['angle']+offset) <= -math.radians(155) or (-ball['angle'] + offset >= -math.radians(35)):
                                    ball['angle'] = -ball['angle']
                                else:
                                    ball['angle'] = -ball['angle']+offset
                                ball['y'] = self._dim['paddleY']-self._dim['ballR']
                                self._state['players']['1']['hits'] += 1
                else:
                    # for player in self._state['players']:
                    if ball['y']+self._dim['ballR'] > self._dim['paddleY'] and ball['y'] < self._dim['paddleY']+self._dim['ballR']: 
                        if ball['x'] + self._dim['ballR'] > self._state['players']['0']['pos'] and ball['x'] < self._state['players']['0']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                            impact = (ball['x'] + self._dim['ballR']/2) - (self._state['players']['0']['pos']+ (self._dim['pWidth']/2))
                            offset = impact/(self._dim['pWidth']/2)/2
                            if (-ball['angle']+offset) <= -math.radians(155) or (-ball['angle'] + offset >= -math.radians(35)):
                                ball['angle'] = -ball['angle']
                            else:
                                ball['angle'] = -ball['angle']+offset
                            ball['y'] = self._dim['paddleY']-self._dim['ballR']
                            if ball['x'] + self._dim['ballR'] > self._state['players']['1']['pos'] and ball['x'] < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                                    self._state['players']['0']['hits'] += 0.5
                                    self._state['players']['1']['hits'] += 0.5
                            else:
                                self._state['players']['0']['hits'] += 1

                        elif ball['x'] + self._dim['ballR'] > self._state['players']['1']['pos'] and ball['x'] < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                            impact = (ball['x'] + self._dim['ballR']/2) - (self._state['players']['1']['pos']+ (self._dim['pWidth']/2))
                            offset = impact/(self._dim['pWidth']/2)/2
                            if (-ball['angle']+offset) <= -math.radians(155) or (-ball['angle'] + offset >= -math.radians(35)):
                                ball['angle'] = -ball['angle']
                            else:
                                ball['angle'] = -ball['angle']+offset
                            ball['y'] = self._dim['paddleY']-self._dim['ballR']
                            self._state['players']['1']['hits'] += 1
                                
    async def run(self):

        await self._ready.wait()
        state = self._state

        print('ready!')

        for block_no, block in enumerate(self._blocks):
            state['status'] = 'reading'
            state['players']['0']['status'] = 'notReady'
            state['players']['1']['status'] = 'notReady'
            state['block'] = block
            state['trialNo'] = block_no%(len(self._blocks) / 3)
            state['maxTrials'] = len(self._blocks) / 3# trials per block

            # print(f"p1H: {self._state['players']['0']['hits']}, p1M: {self._state['players']['0']['miss']}")
            # print(f"p2H: {self._state['players']['1']['hits']}, p2M: {self._state['players']['1']['miss']}")

            self._state['players']['0']['hits'] = 0
            self._state['players']['1']['hits'] = 0
            self._state['players']['0']['miss'] = 0
            self._state['players']['1']['miss'] = 0

            balls = [None] * block['n_balls'] * 2 # n_balls represents the number of balls per player, so should be doubled.
            angles = [0-math.radians(randint(45,135)) for angle in balls]
            speed = 4
            for i, _ in enumerate(balls):
                if state['block']['block_type'] == "nonCol":
                    if i >= len(balls)/2:
                        balls[i] = {
                            'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                            'y': self._dim['ballY'],
                            'angle': angles[i],
                            'speed': speed,
                            'id': int(9 - ((len(balls)/2) - i))
                        }
                    else:
                        balls[i] = {
                        'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                        'y': self._dim['ballY'],
                        'angle': angles[i],
                        'speed': speed,
                        'id': i
                        }
                else:
                    balls[i] = {
                    'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                    'y': self._dim['ballY'],
                    'angle': angles[i],
                    'speed': speed,
                    'id': i
                    }
            state['balls'] = balls

            ## DRT
            state['drt']['onset'] = [20 - (randint(3000,5000)/1000)] ## change trial duration as necessary
            # determine trial presentation intervals, display times, and response windows.
            while state['drt']['onset'][-1] > 5:
                state['drt']['onset'].append(state['drt']['onset'][-1] - (randint(3000,5000)/1000))

            state['drt']['dispStim'] = [stim-1 for stim in state['drt']['onset']]
            state['drt']['window'] = [stim-2.5 for stim in state['drt']['onset']]
            if state['drt']['window'][-1] <= 0:  ## remove the last stimulus time if it's too close to the end of the trial.
                state['drt']['onset'], state['drt']['dispStim'], state['drt']['window'] = state['drt']['onset'][0:-1], state['drt']['dispStim'][0:-1], state['drt']['window'][0:-1]

            self.send()

            print(f'block { block_no }, awaiting players')
            while True:
                await self.update()

                print(f'player 0 { state["players"]["0"]["status"] }')
                print(f'player 1 { state["players"]["1"]["status"] }')

                if (state['players']['0']['status'] == 'ready'
                        and state['players']['1']['status'] == 'ready'):
                    break

            state['players']['0']['pos'] = self._dim['p1Start']
            state['players']['1']['pos'] = self._dim['p2Start']
            state['status'] = 'playing'
            self.send()

            print(f'block { block_no }, begun!')

            async def play():
                while True:
                    await self.update()
                    self.send()

            try:
                await wait_for(play(), 20)
            except TimeoutError:
                pass

            print(f'block { block_no }, complete!')