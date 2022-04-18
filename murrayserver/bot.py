
from asyncio import create_task
from asyncio import sleep
from asyncio import wait

import math
import json
from random import randint

from .stream import ProgressStream
from collections import namedtuple
from itertools import islice

Message = namedtuple('Message', 'data')


class WS(ProgressStream):
    async def send_str(self, content):
        pass

class Bot:

    def __init__(self, pretend_to_be_human):
        self._pretend_to_be_human = pretend_to_be_human
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

        self._player_id = self._game.add_player()
        self._run_task = create_task(self._run())
        self._run_task.add_done_callback(lambda t: t.result())

    def _send(self, data):
        content = json.dumps(data)
        self._stream.write(Message(content))

    async def _run(self):

        complete = create_task(self._game.join(self._player_id, self._stream))

        while not complete.done():

            if self._state['status'] == 'reading':
                if self._state['players'][self._player_id]['status'] != 'ready':
                    if self._pretend_to_be_human:
                        other_player = '1' if self._player_id == '0' else '0'
                        # always have the player wait for the bot
                        if self._state['players'][other_player]['status'] == 'ready':
                            await sleep(randint(1, 6))
                            self._send({'status':'ready'})
                    else:
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

    def determinePositionWeights(self, balls):

        # construct 80 bins, with each bin representing a position the paddle can move to.

        width = self._bounds['right'] - self._bounds['left']
        nBins = 80
        binWidth = width / (nBins - 1)
        weights = [None] * nBins


        # each bin is assigned an x, and a t ... x is the x coord, t is the
        # preference for moving to that location. the bin with
        # the highest t is where the bot will move the paddle

        for i in range(nBins):
            x = self._bounds['left'] + (i + 0.5) / nBins * width
            # here we provide a slight bias towards the center of the screen
            t = 1 - abs(x - (width / 2)) / (width / 2)
            weights[i] = { 'x': x, 't': t }

        # here we iterate over each ball
        for ball in balls:
            # calculating when/where it will intersect the paddle line
            # note that from dumbing it down, it will only consider intersections
            # less than 1.2 seconds into the future
            intercept = self.determinePaddleIntercept(ball['x'], ball['y'], ball['speed'], ball['angle'])
            if intercept is None:
                continue

            for weight in weights:
                # calculate the x distance between the intersect and the bin
                distance = abs(intercept['x'] - weight['x'])
                # convert that to a
                proximity = 1 - (distance / width);

                # proximity, 1 = close, 0 = distant
                # intercept['p'] is 'temporal proximity', 1 = intersection soon, 0 = distant

                # these are examples of how you can weight the weights
                # using a 1 -> 0 interval is nice because we can raise it to
                # different powers to tune the behaviour:
                #
                # weight['t'] += pow(proximity, 3) * pow(intercept['p'], 5) * 100
                # weight['t'] += pow(proximity, 1) * pow(intercept['p'], 1) * 100

                # but in the process of dumbing the whole thing down, this is
                # what i ened up with

                weight['t'] += pow(proximity, 1) * 100

                # in fact i could simplify this to just
                #   weight['t'] += proximity
                # but whatevs


        return weights

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

        weights = self.determinePositionWeights(balls)

        max_weight = { 'x': 400, 't': 0 };

        for weight in weights:
            if weight['t'] > max_weight['t']:
                max_weight = weight

        return max_weight['x']

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


class Bot2(Bot):

    def determinePositionWeights(self, balls):

        # calculate the weights
        weights = super().determinePositionWeights(balls)

        block_type = self._state['block']['block_type']
        if block_type == 'col':
            other_player = '0' if self._player_id == '1' else '1'
            paddle_left = self._state['players'][other_player]['pos']
            paddle_right = paddle_left + self._dim['pWidth']

            for weight in weights:

                # if the bin falls within 100 pixels of the opponents paddle,
                # set the weight to 0.
                if weight['x'] >= paddle_left - 100 and weight['x'] <= paddle_right + 100:
                    weight['t'] = 0

        return weights
