
from asyncio import create_task
from asyncio import sleep
from asyncio import wait

import math
import json

from .stream import ProgressStream
from collections import namedtuple
from itertools import islice

Message = namedtuple('Message', 'data')


class WS(ProgressStream):
    async def send_str(self, content):
        pass

class Bot:

    def __init__(self):
        self._state = None
        self._run_task = None
        self._stream = WS()
        self._player_id = None

    def start(self, game):
        self._game = game
        self._state = game._state
        self._dim = game._dim

        self._bounds = {
            'left': self._dim['frameLeft'] + self._dim['ballR'],
            'top': self._dim['ballR'],
            'right': self._dim['frameRight'] - self._dim['ballR'],
            'bottom': self._dim['frameHeight'] - self._dim['ballR'],
            'paddle': self._dim['paddleY'] - self._dim['ballR'],
        }

        self._run_task = create_task(self._run())
        self._run_task.add_done_callback(lambda t: t.result())

    def _send(self, data):
        content = json.dumps(data)
        self._stream.write(Message(content))

    async def _run(self):

        self._player_id = self._game.add_player()
        complete = create_task(self._game.join(self._player_id, self._stream))

        while not complete.done():

            if self._state['status'] == 'reading':
                if self._state['players'][self._player_id]['status'] != 'ready':
                    self._send({'status':'ready'})
            else:
                balls = self._state['balls']
                optimal_pos = self.determineOptimalPosition(balls) - self._dim['pWidth'] / 2
                if optimal_pos < self._dim['frameLeft']:
                    optimal_pos = self._dim['frameLeft']
                elif optimal_pos > self._dim['frameRight'] - self._dim['pWidth']:
                    optimal_pos = self._dim['frameRight'] - self._dim['pWidth']

                if self._state['players'][self._player_id]['pos'] < optimal_pos:
                    if self._state['players'][self._player_id]['pos'] + 13.5 < optimal_pos:
                        self._state['players'][self._player_id]['pos'] += 13.5
                    else:
                        self._state['players'][self._player_id]['pos'] = optimal_pos
                elif self._state['players'][self._player_id]['pos'] > optimal_pos:
                    if self._state['players'][self._player_id]['pos'] - 13.5 > optimal_pos:
                        self._state['players'][self._player_id]['pos'] -= 13.5
                    else:
                        self._state['players'][self._player_id]['pos'] = optimal_pos

            await wait({ complete }, timeout=.05)

    def determineOptimalPosition(self, balls):

        block_type = self._state['block']['block_type']

        if block_type == 'nonCol':
            if self._player_id == '0':
                start = 0
                stop = len(balls) // 2
            else:
                start = len(balls) // 2
                stop = None
            balls = islice(balls, start, stop)

        width = self._bounds['right'] - self._bounds['left']
        nBins = 80
        binWidth = width / (nBins - 1)
        bins = [None] * nBins

        for i in range(nBins):
            bins[i] = { 'x': self._bounds['left'] + (i + 0.5) / nBins * width, 't': 0 }

        for ball in balls:
            intercept = self.determinePaddleIntercept(ball['x'], ball['y'], ball['speed'], ball['angle'])
            if intercept is None:
                continue
            for bin in bins:
                distance = abs(intercept['x'] - bin['x'])
                proximity = 1 - (distance / width);
                #bin['t'] += pow(proximity, 3) * pow(intercept['p'], 5) * 100
                #bin['t'] += pow(proximity, 1) * pow(intercept['p'], 1) * 100
                bin['t'] += pow(proximity, 1) * 100

        max_t = { 'x': 400, 't': 0 };

        for bin in bins:
            if bin['t'] > max_t['t']:
                max_t = bin

        return max_t['x']

    def calc_pos(self, x, y, speed, angle, elapsed):
        xe = x + speed * math.cos(angle) * elapsed / 1000 / 0.02
        ye = y + speed * math.sin(angle) * elapsed / 1000 / 0.02
        return { 'x': xe, 'y': ye }

    def determinePaddleIntercept(self, x, y, speed, angle):

        elapsed = 1200

        while True:
            collisions = [
                self.determineLeftCollision(x, y, speed, angle, elapsed),
                self.determineRightCollision(x, y, speed, angle, elapsed),
                self.determineTopCollision(x, y, speed, angle, elapsed),
                self.determineBottomCollision(x, y, speed, angle, elapsed),
                self.determinePaddleLineCrossing(x, y, speed, angle, elapsed),
            ]

            earliest = None
            for collision in collisions:
                if earliest is not None:
                    if collision is not None and collision['elapsed'] < earliest['elapsed']:
                        earliest = collision
                else:
                    earliest = collision

            if earliest:
                x = earliest['x']
                y = earliest['y']
                angle = earliest['angle']
                elapsed = elapsed - earliest['elapsed']

                if earliest['y'] is None:
                    return { 'x': earliest['x'], 'p': elapsed / 1200 }
            else:
                return None

    def determinePaddleLineCrossing(self, x, y, speed, angle, elapsed):

        end = self.calc_pos(x, y, speed, angle, elapsed)

        if y > self._bounds['paddle'] or end['y'] < self._bounds['paddle']:
            # did not pass through paddle line
            return None

        prop = (self._bounds['paddle'] - y) / (end['y'] - y)
        xAtCrossing = (end['x'] - x) * prop + x
        elapsed = elapsed * prop
        return { 'x': xAtCrossing, 'elapsed': elapsed, 'y': None, 'angle': None }

    def determineResultantAngle(self, crossing, angle, paddleX):
        if paddleX is None:
            return None
        if crossing['x'] < paddleX - self._dim['ballR'] or crossing['x'] > paddleX + self._dim['pWidth'] + self._dim['ballR']:
            return

        impact = (crossing['x'] + self._dim['ballR'] / 2) - (paddleX + self._dim['pWidth'] / 2)
        offset = impact / (self._dim['pWidth'] / 2) / 2
        newAngle = -angle + offset

        if (newAngle <= -math.radians(155) or newAngle >= -math.radians(35)):
            return -angle
        else:
            return newAngle

    def determineLeftCollision(self, x, y, speed, angle, elapsed):
        end = self.calc_pos(x, y, speed, angle, elapsed)
        if end['x'] < self._bounds['left']:
            prop = (x - self._bounds['left']) / (x - end['x'])
            x = self._bounds['left']
            y = (end['y'] - y) * prop + y
            elapsed = elapsed * prop
            angle = math.radians(180) - angle
            return { 'x': x, 'y': y, 'speed': speed, 'angle': angle, 'elapsed': elapsed }

    def determineRightCollision(self, x, y, speed, angle, elapsed):
        end = self.calc_pos(x, y, speed, angle, elapsed)
        if end['x'] > self._bounds['right']:
            prop = (self._bounds['right'] - x) / (end['x'] - x)
            x = self._bounds['right']
            y = (end['y'] - y) * prop + y
            elapsed = elapsed * prop
            angle = math.radians(180) - angle
            return { 'x': x, 'y': y, 'speed': speed, 'angle': angle, 'elapsed': elapsed }

    def determineTopCollision(self, x, y, speed, angle, elapsed):
        end = self.calc_pos(x, y, speed, angle, elapsed)
        if end['y'] < self._bounds['top']:
            prop = (y - self._bounds['top']) / (y - end['y'])
            y = self._bounds['top']
            x = (end['x'] - x) * prop + x
            elapsed = elapsed * prop
            angle = -angle
            return { 'x': x, 'y': y, 'speed': speed, 'angle': angle, 'elapsed': elapsed }

    def determineBottomCollision(self, x, y, speed, angle, elapsed):
        end = self.calc_pos(x, y, speed, angle, elapsed)
        if end['y'] > self._bounds['bottom']:
            prop = (self._bounds['bottom'] - y) / (end['y'] - y)
            x = (end['x'] - x) * prop + x
            y = self._bounds['top']
            elapsed = elapsed * prop
            return { 'x': x, 'y': y, 'speed': speed, 'angle': angle, 'elapsed': elapsed }
        else:
            return None
