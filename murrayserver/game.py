
import json
from asyncio import Event
from asyncio import create_task
from asyncio import wait
from asyncio import wait_for
from asyncio import FIRST_COMPLETED
from asyncio import sleep
from asyncio import TimeoutError

from collections import OrderedDict
from datetime import datetime
from random import randint
from random import shuffle
from time import time
from os import environ
from os import path
import math
import sys

from .stream import ProgressStream

import logging


async def run_later(coro, delay):
    await sleep(delay)
    return await coro


class Game:
    def __init__(self, game_no):
        self._game_no = game_no
        self._joined = { '0': False, '1': False }
        self._conns = { '0': None, '1': None }
        self._send_update = OrderedDict({ '0': Event(), '1': Event() })
        self._receive_update = Event()
        self._ready = Event()
        self._ended = False
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

        block_orders = [
           ["nonCol","col","com"],
           ["nonCol","com","col"],
           ["col","nonCol","com"],
           ["col","com","nonCol"],
           ["com","nonCol","col"],
           ["com","col","nonCol"]
           ]

        block_types = block_orders[self._game_no % len(block_orders)]
        n_balls = [1, 1, 1, 3, 3, 3, 6, 6, 6, 9, 9, 9]

        shuffle(n_balls)

        for block_type in block_types:
            for n in n_balls:
                self._blocks.append({ 'block_type': block_type, 'n_balls': n })

        self._state = {
            'player_id': None,
            'status': 'waiting',
            'timestamp': time(),
            'block': self._blocks[0],
            'blockNo': 0,
            'players': {
                '0': {
                    'pos': self._dim['p1Start'],
                    'status': 'notReady',
                    'hand': [],
                    'trialStart': 0,
                    'hits': 0,
                    'miss': 0,
                    'rt': 0,
                    'fa': 0,
                    'score': 0,
                    },
                '1': {
                    'pos': self._dim['p2Start'],
                    'status': 'notReady',
                    'hand': [],
                    'trialStart': 0,
                    'hits': 0,
                    'miss': 0,
                    'rt': 0,
                    'fa': 0,
                    'score': 0
                    },
            },
            'balls': [ ],
            'drt': {
                'onset': [], ## change trial duration as necessary
                'dispTime': [],
                'window': [],
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

        print(f'{ self._game_no } player { player_id } connected')

        if not self._joined[player_id]:
            self._joined[player_id] = True
            if self._joined['0'] and self._joined['1']:
                self._ready.set()

        async def send(obj, delay=None):
            if delay is not None:
                t = create_task(run_later(send(obj), delay))
                t.add_done_callback(lambda f: f.result())
            else:
                await ws.send_str(obj)

        async def read():
            try:
                async for msg in ws:
                    if msg.data == 'ping':
                        await ws.send_str('pong')
                    else:
                        self._log.info(f'{{ "received": { msg.data }, "player": { player_id } }}')
                        data = json.loads(msg.data)
                        self._state['players'][player_id].update(data)
                        self._receive_update.set()
            finally:
                if not self._ready.is_set():
                    self._joined[player_id] = False
                if self._state['status'] == 'ending':
                    self._joined[player_id] = False
                    if self._joined[0] is False and self._joined[1] is False:
                        self._ended = True

        async def write():
            send_event = self._send_update[player_id]
            send_event.set()
            while self._ended is False:
                await send_event.wait()
                send_event.clear()
                self._state['player_id'] = player_id
                state = json.dumps(self._state)
                delay = None
                # delay = time() % 4
                # if delay > 2:
                #     delay = 4 - delay
                # delay /= 2
                await send(state, delay)


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

        log_state = True

        try:
            timeout = None
            if self._state['status'] == 'playing':
                timeout = 0.02
            else:
                timeout = 3
            await wait_for(self._receive_update.wait(), timeout)
            self._receive_update.clear()
        except TimeoutError:
            log_state = False  # prevent logs from filling up with junk

        now = time()
        last_time = self._state['timestamp']
        self._state['timestamp'] = now
        elapsed = now - last_time

        if self._state['status'] == 'playing' and self._last_status == 'playing':
            for ball in self._state['balls']:

                x = ball['x'] + ball['speed'] * math.cos(ball['angle']) * elapsed / 0.02
                y = ball['y'] + ball['speed'] * math.sin(ball['angle']) * elapsed / 0.02
                angle = ball['angle']

                right = self._dim['frameRight'] - self._dim['ballR']
                left = self._dim['frameLeft'] + self._dim['ballR']
                top = self._dim['frameTop'] + self._dim['ballR']
                bottom = self._dim['frameBottom'] - 0.5 * self._dim['ballR']

                if x > right:
                    x = right - (x - right)
                    angle = math.pi - angle
                if x < left:
                    x = left + (left - x)
                    angle = math.pi - angle
                if y > bottom:
                    y -= (bottom - top)
                    if self._state['block']['block_type'] == 'nonCol':
                        if ball['id'] < 9:
                            self._state['players']['0']['miss'] += 1
                        else:
                            self._state['players']['1']['miss'] += 1
                    else:
                        self._state['players']['0']['miss'] += 1
                        self._state['players']['1']['miss'] += 1
                if y < top:
                    y = top + (top - y)
                    angle = -angle

                # If a player is in the right spot at the right ?time?
                if self._state['block']['block_type'] == 'nonCol':
                    if self._state['player_id'] == "0" and ball['id'] < 9:
                        if y + self._dim['ballR'] > self._dim['paddleY'] and y < self._dim['paddleY']+self._dim['ballR']:
                            if x + self._dim['ballR'] > self._state['players']['0']['pos'] and x < self._state['players']['0']['pos'] + self._dim['pWidth'] + self._dim['ballR']: ## approx paddle width - much to account for here.
                                impact = (x + self._dim['ballR']/2) - (self._state['players']['0']['pos']+ (self._dim['pWidth']/2))
                                offset = impact/(self._dim['pWidth']/2)/2
                                if (-angle + offset) <= -math.radians(155) or (-angle + offset >= -math.radians(35)):
                                    angle = -angle
                                else:
                                    angle = -angle + offset
                                y = self._dim['paddleY'] - (self._dim['paddleY'] - y) - self._dim['ballR']
                                self._state['players']['0']['hits'] += 1
                                self._state['players']['0']['score'] += 1

                    if self._state['player_id'] == "1" and ball['id'] >= 9:
                        if y + self._dim['ballR'] > self._dim['paddleY'] and y < self._dim['paddleY']+self._dim['ballR']:
                            if x + self._dim['ballR'] > self._state['players']['1']['pos'] and x < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']: ## approx paddle width - much to account for here.
                                impact = (x + self._dim['ballR']/2) - (self._state['players']['1']['pos']+ (self._dim['pWidth']/2))
                                offset = impact/(self._dim['pWidth']/2)/2
                                if (-angle + offset) <= -math.radians(155) or (-angle + offset >= -math.radians(35)):
                                    angle = -angle
                                else:
                                    angle = -angle + offset
                                y = self._dim['paddleY'] - (self._dim['paddleY'] - y) - self._dim['ballR']
                                self._state['players']['1']['hits'] += 1
                                self._state['players']['1']['score'] += 1
                else:
                    if y + self._dim['ballR'] > self._dim['paddleY'] and y < self._dim['paddleY']+self._dim['ballR']:
                        if x + self._dim['ballR'] > self._state['players']['0']['pos'] and x < self._state['players']['0']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                            impact = (x + self._dim['ballR']/2) - (self._state['players']['0']['pos']+ (self._dim['pWidth']/2))
                            offset = impact/(self._dim['pWidth']/2)/2
                            if (-angle + offset) <= -math.radians(155) or (-angle + offset >= -math.radians(35)):
                                angle = -angle
                            else:
                                angle = -angle + offset
                            y = self._dim['paddleY'] - (self._dim['paddleY'] - y) - self._dim['ballR']
                            if x + self._dim['ballR'] > self._state['players']['1']['pos'] and x < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                                    self._state['players']['0']['hits'] += 0.5
                                    self._state['players']['1']['hits'] += 0.5
                                    self._state['players']['0']['score'] += 0.5
                                    self._state['players']['1']['score'] += 0.5
                            else:
                                self._state['players']['0']['hits'] += 1
                                self._state['players']['0']['score'] += 1

                        elif x + self._dim['ballR'] > self._state['players']['1']['pos'] and x < self._state['players']['1']['pos'] + self._dim['pWidth'] + self._dim['ballR']:
                            impact = (x + self._dim['ballR']/2) - (self._state['players']['1']['pos']+ (self._dim['pWidth']/2))
                            offset = impact/(self._dim['pWidth']/2)/2
                            if (-angle + offset) <= -math.radians(155) or (-angle + offset >= -math.radians(35)):
                                angle = -angle
                            else:
                                angle = -angle + offset
                            y = self._dim['paddleY'] - (self._dim['paddleY'] - y) - self._dim['ballR']
                            self._state['players']['1']['hits'] += 1
                            self._state['players']['1']['score'] += 1

                ball['x'] = x
                ball['y'] = y
                ball['angle'] = angle

        if log_state:
            self._log.info(json.dumps(self._state))
        self._last_status = self._state['status']

    async def run(self):

        self._log = logging.getLogger(f'game-{ self._game_no }')
        self._log.setLevel(logging.INFO)

        time_string = datetime.now().isoformat(timespec='seconds').replace(':', '')

        log_path = environ.get('MURRAYSERVER_LOG_PATH', '')
        log_path = path.join(log_path, f'game-{ time_string }-{ self._game_no }.txt')

        self._logHandler = logging.FileHandler(log_path, mode='w')
        self._logHandler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        self._logHandler.setFormatter(formatter)
        self._log.addHandler(self._logHandler)

        try:
            await self._ready.wait()

            print(f'{ self._game_no } ready!')

            def resetVars():
                self._state['players']['0']['hits'] = 0
                self._state['players']['1']['hits'] = 0
                self._state['players']['0']['miss'] = 0
                self._state['players']['1']['miss'] = 0
                self._state['players']['0']['rt'] = 0
                self._state['players']['1']['rt'] = 0
                self._state['players']['0']['fa'] = 0
                self._state['players']['1']['fa'] = 0
                self._state['players']['0']['score'] = 0
                self._state['players']['1']['score'] = 0

            for block_no, block in enumerate(self._blocks):
                self._state['status'] = 'reading'
                self._state['players']['0']['status'] = 'notReady'
                self._state['players']['1']['status'] = 'notReady'
                self._state['block'] = block
                self._state['blockNo'] = int(block_no / 36 * 3)  # change 12 to 36 when time - it just needs to be the number of trials per block
                self._state['trialNo'] = block_no%(len(self._blocks) / 3)
                self._state['maxTrials'] = len(self._blocks) / 3 # trials per block

                resetVars()

                balls = [None] * block['n_balls'] * 2 # n_balls represents the number of balls per player, so should be doubled.
                angles = [0-math.radians(randint(45,135)) for angle in balls]
                speed = 4
                for i, _ in enumerate(balls):
                    if self._state['block']['block_type'] == "nonCol":
                        if i >= len(balls)/2:
                            balls[i] = {
                                'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                                'y': self._dim['ballY'],
                                'angle': angles[i],
                                'speed': speed,
                                'id': int(9 - ((len(balls)/2) - i)),
                            }
                        else:
                            balls[i] = {
                            'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                            'y': self._dim['ballY'],
                            'angle': angles[i],
                            'speed': speed,
                            'id': i,
                            }
                    else:
                        balls[i] = {
                        'x': self._dim['ballX'][i%len(self._dim['ballX'])],
                        'y': self._dim['ballY'],
                        'angle': angles[i],
                        'speed': speed,
                        'id': i,
                        }
                self._state['balls'] = balls

                ## DRT
                self._state['drt']['onset'] = [15 - (randint(3000,5000)/1000)] ## change trial duration as necessary
                # determine trial presentation intervals, display times, and response windows.
                while self._state['drt']['onset'][-1] > 5:
                    self._state['drt']['onset'].append(self._state['drt']['onset'][-1] - (randint(3000,5000)/1000))

                self._state['drt']['dispTime'] = [stim-1 for stim in self._state['drt']['onset']]
                self._state['drt']['window'] = [stim-2.5 for stim in self._state['drt']['onset']]
                if self._state['drt']['window'][-1] <= 0:  ## remove the last stimulus time if it's too close to the end of the trial.
                    self._state['drt']['onset'], self._state['drt']['dispTime'], self._state['drt']['window'] = self._state['drt']['onset'][0:-1], self._state['drt']['dispTime'][0:-1], self._state['drt']['window'][0:-1]

                self.send()

                self._log.info(json.dumps(self._state))

                print(f'{ self._game_no } block { block_no }, awaiting players')
                while True:
                    await self.update()
                    print(f'{ self._game_no } player 0 { self._state["players"]["0"]["status"] }')
                    print(f'{ self._game_no } player 1 { self._state["players"]["1"]["status"] }')

                    if (self._state['players']['0']['status'] == 'ready'
                            and self._state['players']['1']['status'] == 'ready'):
                        break
                    if (self._state['players']['0']['status'] == 'ready'
                            or self._state['players']['1']['status'] == 'ready'):
                        self.send()

                self._state['players']['0']['pos'] = self._dim['p1Start']
                self._state['players']['1']['pos'] = self._dim['p2Start']
                self._state['status'] = 'playing'
                self.send()

                self._log.info(json.dumps(self._state))

                print(f'{ self._game_no } block { block_no }, begun!')

                async def play():
                    while True:
                        await self.update()
                        self.send()

                try:
                    await wait_for(play(), 10) # set to trial duration
                except TimeoutError:
                    pass

                print(f'{ self._game_no } block { block_no }, complete!')
                self._logHandler.flush()

            self._state['status'] = 'ending'
            while not self._ended:
                await self.update()
                self.send()

        except BaseException as e:
            self._log.exception(e)
            raise e
        finally:
            self._log.removeHandler(self._logHandler)
            self._logHandler.flush()
            self._logHandler.close()
            del self._logHandler
            del self._log
