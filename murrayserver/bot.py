
from asyncio import create_task
from asyncio import sleep
from asyncio import wait

import math
import json
from random import randint
import pickle
import numpy as np

from .stream import ProgressStream
from collections import namedtuple
from itertools import islice

Message = namedtuple('Message', 'data')

q_table = None
with open('murrayserver/Q_experiment.pickle',"rb") as f:
    q_table = pickle.load(f)

class WS(ProgressStream):
    async def send_str(self, content):
        pass

class Bot:

    def __init__(self, pretend_to_be_human, bot_type):
        self._pretend_to_be_human = pretend_to_be_human
        self._state = None
        self._run_task = None
        self._stream = WS()
        self._player_id = None
        self.q_table = q_table
        self._bot_type = bot_type
        self._score_multiplier = 5

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
        self._state['players'][self._player_id]['hand'] = f"{self._bot_type}-{self._pretend_to_be_human}"
        
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
                # if the bin falls within 100 pixels of the opponents paddle, # set the weight to 0.
                if weight['x'] >= paddle_left - 100 and weight['x'] <= paddle_right + 100:
                    weight['t'] = 0
        return weights

class BotQ(Bot):
    def getPos(self, ball):
        env_size = 60
        pWidth_half = 36
        bx = int(round(ball['x']/13.5))
        px = int(round( (self._state['players']['1']['pos'] + pWidth_half) / 13.5))
        # py = int(round(self._dim['paddleY'] / 10.))
        by = int(round( (ball['y'] + self._dim['ballR']) /10.))
        # return [bx-px, py-by]
        return [bx-px, env_size-by]
        
    
    def make_action(self, balls):
        obs = np.ones((1,2,self._state['block']['n_balls'] * 2)) * -999
        other_obs = np.ones((1,2,self._state['block']['n_balls'] * 2)) * -999
        
        b_counter = -1
        for ball in balls:
            b_counter += 1

            if self._state['block']['block_type'] == 'nonCol':
                if ball['dir'] == 0:
                    if ball['id'] < 9 and self._player_id == '0':
                        obs[0,:,b_counter] = self.getPos(ball)
                    elif ball['id'] >= 9 and self._player_id == '1':
                        obs[0,:,b_counter] = self.getPos(ball)
                if np.max(obs) == -999:
                    # action = 1
                    new_pos = self.move('stop')
                    return new_pos
    
            # collaborative and competitive
            else:
                if ball['dir'] == 0:
                    if ball['id'] < 9:
                        if self._player_id == '0':
                            obs[0,:, b_counter] = self.getPos(ball)
                        else:
                            other_obs[0, :, b_counter] = self.getPos(ball)
                    else:
                        if self._player_id == '1':
                            obs[0,:, b_counter] = self.getPos(ball)
                        else:
                            other_obs[0, :, b_counter] = self.getPos(ball)
                # stop if no balls moving down-screen
                if np.max(obs) == -999 and np.max(other_obs) == -999:
                    new_pos = self.move('stop')
                    return new_pos

        # convert ball x, y positions to q_table location, get q values, then determine best action from q values
        all_x = self.process_obs(obs[0,0,:])
        all_y = self.process_obs(obs[0,1,:])
        all_qs = self.get_qs(all_x, all_y)
        mean_qs = self.qs_to_action(all_qs, multiplier = 1)

        # repeat for the other ball locations
        if self._state['block']['block_type'] == 'nonCol':
            other_x = self.process_obs(other_obs[0, 0, :])
            other_y = self.process_obs(other_obs[0, 1, :])
            other_qs = self.get_qs(other_x, other_y)
            mean_qs = mean_qs + self.qs_to_action(other_qs, multiplier = self._score_multiplier)

        action = np.argmax(mean_qs)
        # best_action = np.argmax(all_mean_actions)
        # return best_action
        # action the paddle
        if action == 0:
            new_pos = self.move('left')
        elif action == 1:
            new_pos = self.move('stop')
        else:
            new_pos = self.move('right')
        return new_pos


    def move(self, direction):
        if direction == 'left':
            new_pos = self._state['players'][self._player_id]['pos'] - 13.5 # self._dim['pSpeed']
            if new_pos <= self._dim['frameLeft']:
                new_pos = self._dim['frameLeft']
        elif direction == 'right':
            new_pos = self._state['players'][self._player_id]['pos'] + 13.5 # self._dim['pSpeed']
            if new_pos >= self._dim['frameRight'] - self._dim['pWidth']:
                new_pos = self._dim['frameRight'] - self._dim['pWidth']
        else:
            new_pos = self._state['players'][self._player_id]['pos']
        return new_pos

    
    def get_qs(self, xs, ys):
        all_qs = []
        for q in range(0,len(xs)):
            all_qs.append([self.q_table[(xs[q],ys[q])]])
        return all_qs

    
    def process_obs(self, ball_obs):
        ball_obs = ball_obs[ball_obs != -999]
        ball_obs = [int(obs) for obs in ball_obs]
        return ball_obs

    
    def qs_to_action(self, qs, multiplier = 1):
        all_best_actions = [-1]
        all_best_qs = [-1]
        all_mean_actions = np.zeros((1,3))
        left, stop, right = [0], [0], [0]
        
        # for act in range(0,len(qs)):
        for i, values in enumerate(qs):
            best_action = np.argmax(values)
            best_action_q = np.amax(values)
            all_best_actions.append(best_action)
            all_best_qs.append(best_action_q)
            
            if best_action == 0:
                left.append(best_action_q)
            elif best_action == 1:
                stop.append(best_action_q)
            else:
                right.append(best_action_q)
        all_mean_actions[0,0] = np.mean(left) * multiplier
        all_mean_actions[0,1] = np.mean(stop) * multiplier
        all_mean_actions[0,2] = np.mean(right) * multiplier
        return all_mean_actions
        ## take the most common suggested action - mode
        # vals, counts = np.unique(all_best_actions[1:], return_counts=True)
        # index = np.argmax(counts)
        ## Move based on the most common score - tends to stick to the middle
        # action = vals[index]
        
        # Move based on the best average score - can get dragged to a side but makes some nice intuitive action when something is close (obvs being overweighted by the mean)
        # best_action = np.argmax(all_mean_actions)
        # return best_action
        
    
    async def _run(self):
        complete = create_task(self._game.join(self._player_id, self._stream))
        self._state['players'][self._player_id]['hand'] = f"{self._bot_type}-{self._pretend_to_be_human}"
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
                self._state['players'][self._player_id]['pos'] = self.make_action(balls)

            await wait({ complete }, timeout=.05)
