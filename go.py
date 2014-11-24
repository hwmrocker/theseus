import asyncio
import msgpack
import time
import sys
from collections import namedtuple

import logging

# create logger with 'spam_application'
logger = logging.getLogger('Theseus')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('debug.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


directions = {
    # direction: (left, top)
    "w": (0, -1),
    "a": (-1, 0),
    "s": (0, 1),
    "d": (1, 0),
}


def now():
    return time.time()


_Bomb = namedtuple("Bomb", ["position", "fuse_time"])


class Bomb(_Bomb):
    pass


class Pathfinder:

    # def __init__(self):
    #     self.map = [
    #         [g, g, W, W, g, W, g],
    #         [g, M, g, M, g, M, g],
    #         [W, W, g, W, g, g, g],
    #         [W, M, W, M, W, M, g],
    #         [W, W, g, W, g, g, g],
    #         [g, M, g, g, g, M, g],
    #         [W, W, g, W, g, g, g],
    #     ]
    #     self.position = (0, 0)

    def get_tile(self, pos):
        x, y = pos
        assert self.valid_map_pos(pos)
        return self.map[y][x]

    def valid_map_pos(self, pos):
        x, y = pos
        return 0 <= y < len(self.map) and 0 <= x < len(self.map[y])

    def get_tile_info(self, pos, info=None, direction=None):
        bombscore = self._get_bomb_score(pos)
        min_hide_distance, hide_path = self._get_min_hide_distance(pos)
        (nd, nmint, nmaxt, path) = self.distance_counter(pos, info, direction)
        ninfo = (nd, nmint, nmaxt, path, bombscore, min_hide_distance, hide_path)
        return ninfo

    def distance_counter(self, pos, info=None, direction=None):
        if info is None:
            return (0, 0., 0., [])
        nd = info[0] + 1
        nmint = info[1] + 0.1
        nmaxt = info[2] + 0.2
        path = []
        if info:
            path = info[3][:]
            if direction:
                path.append(direction)
        ninfo = (nd, nmint, nmaxt, path)
        return ninfo

    def _get_bomb_score(self, pos, distance=10):
        score = 0
        x, y = pos
        for direction, (dx, dy) in directions.items():
            for i in range(1, distance):
                nx = x + i * dx
                ny = y + i * dy
                npos = (nx, ny)
                if not self.valid_map_pos(npos):
                    break

                tile = self.get_tile(npos)
                if tile == "W":
                    score += 1
                    break
                elif tile == "M":
                    break
        return score

    def _get_min_hide_distance(self, pos):
        nb_tiles = self.get_neighbour_tiles(walkable=True, start_position=pos, additional_info=self.distance_counter)
        distance = 100000
        path = []
        for npos, info in nb_tiles:
            if self._is_safe(npos, additional_bombs=[Bomb(pos, now())]):
                distance = info[0]
                path = info[3][:]
                break
        return distance, path

    def _is_safe(self, pos, info=None, additional_bombs=None, distance=10):
        bombs = self.known_bombs[:]
        if additional_bombs is not None:
            # additional_bombs = []
            bombs += additional_bombs
        danger_zone = []
        for (x, y), fuse_time in bombs:
            if (x, y) == pos:
                return False
            for direction, (dx, dy) in directions.items():
                for i in range(1, distance + 1):
                    nx = x + i * dx
                    ny = y + i * dy
                    npos = (nx, ny)
                    if not self.valid_map_pos(npos):
                        break

                    tile = self.get_tile(npos)
                    if tile == "W":
                        break
                    elif tile == "M":
                        break
                    danger_zone.append(npos)
                    if pos == npos:
                        return False
        return True

    def get_neighbour_tiles(self, walkable=False, start_position=None, additional_info=None):
        if start_position is None:
            start_position = self.position
        if additional_info is None:
            additional_info = self.get_tile_info
        visited = set([])
        to_visit = [(start_position, additional_info(start_position))]
        while to_visit:
            pos, info = to_visit.pop(0)
            x, y = pos
            visited.add(pos)
            if not self._is_safe(pos, info):
                continue
            yield pos, info

            for direction, (dx, dy) in directions.items():
                nx = x + dx
                ny = y + dy
                npos = (nx, ny)
                if not self.valid_map_pos(npos):
                    continue
                tile = self.get_tile(npos)
                if npos in visited:
                    continue
                if walkable and not tile.islower():
                    continue
                ninfo = additional_info(npos, info, direction)
                to_visit.append((npos, ninfo))

    def get_best_move(self, max_depth=15):
        def score(distance, mint, maxt, path, score, hide_distance, hide_path):
            if hide_path:
                return (score * 10) - maxt - (hide_distance * 0.2)
            return (score * 10) - maxt - (hide_distance * 0.2) - 100000

        paths = self.get_neighbour_tiles(walkable=True)
        _, info = next(paths)
        best_score = score(*info)
        best_info = info
        for _, info in paths:
            if info[0] > max_depth:
                break
            _score = score(*info)
            # logger.debug(" s{}: {}".format(_score, info))
            if _score > best_score:
                best_score = _score
                best_info = info
                # logger.debug("new highscore")
            # logger.debug("  s{} {}".format(best_score, best_info))

        logger.debug("ret s{} {}".format(best_score, best_info))
        return best_info


class NetworkClient(Pathfinder):

    reader = None
    writer = None
    sockname = None

    def __init__(self, host='127.0.0.1', port=8001):
        super().__init__()
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    def send_msg(self, msg):
        logger.debug("send: {}".format(msg))
        pack = msgpack.packb(msg)
        self.writer.write(pack)

    def close(self):
        if self.writer:
            self.writer.write_eof()

    def inform(self, *msg):
        logger.debug(msg)

    @asyncio.coroutine
    def connect(self):
        logger.debug('Connecting...')
        try:
            reader, writer = yield from asyncio.open_connection(self.host, self.port)
            # asyncio.async(self.create_input())
            self.reader = reader
            self.writer = writer
            self.connection_established()
            self.sockname = writer.get_extra_info('sockname')
            unpacker = msgpack.Unpacker(encoding='utf-8')
            while not reader.at_eof():
                pack = yield from reader.read(1024)
                unpacker.feed(pack)
                for msg in unpacker:
                    self.inform(*msg)
            logger.debug('The server closed the connection')
            self.writer = None
        except ConnectionRefusedError as e:
            logger.debug('Connection refused: {}'.format(e))
            self.close()


class HWM(NetworkClient):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.map = []
        self._ignore_list = []  # ignores unknown callbacks
        self._known_bombs = []
        self.map_data_consistent = False
        self.position_data_consistent = False
        self.ai_running = False
        loop.call_later(1, self.update_bombs)

    @property
    def known_bombs(self):
        return self._known_bombs

    @known_bombs.setter
    def known_bombs(self, value):
        # if there is a bomb missing or fuse_time more than a second later
        # we need to check the mapdata again
        logger.debug("old {} | new {}".format(self._known_bombs, value))
        for b in self._known_bombs:
            found_match = False
            for _b in value:
                # TODO check this condition again
                if b.position == _b.position and (b.fuse_time - 1) < _b.fuse_time < (b.fuse_time + 1):
                    found_match = True
                    break
            if not found_match:
                self.map_data_consistent = False
                # TODO ask for mapupdate
                # asyncio.async()
                loop.call_soon(self.update_internal_state)
                break
        self._known_bombs = value

    @property
    def data_consitent(self):
        return self.map_data_consistent and self.position_data_consistent

    def inform(self, msg_type, data):
        try:
            handler = getattr(self, "handle_{}".format(msg_type))
            ret = handler(data)
            logger.debug("{}: {}".format(msg_type, ret))

        except AttributeError:
            if msg_type not in self._ignore_list:
                self._ignore_list.append(msg_type)
                logger.debug("No handler for {}".format(msg_type))

    def handle_MAP(self, mapstr):
        self.map = []
        for line in mapstr.splitlines():
            self.map.append([c for c in line])
        # logger.debug(mapstr)
        self.map_data_consistent = True
        asyncio.async(self.update_ai())

    def handle_WHOAMI(self, data):
        self.position = (round(data[3] / 10), round(data[2] / 10))
        logger.debug("WHOAMI: {}, {}".format(self.position, repr(data)))
        self.position_data_consistent = True
        asyncio.async(self.update_ai())

    def handle_WHAT_BOMBS(self, data):
        logger.debug(data)
        timed = now()
        new_bombs = []
        for pos, fuse_time, state in data:
            if state == "ticking":
                fuse_time = fuse_time + timed
            elif state == "burning":
                fuse_time = fuse_time + timed - 1.5
            else:
                fuse_time = fuse_time + timed - 1.7
            new_bombs.append(Bomb(pos, fuse_time))
        self.known_bombs = new_bombs

    @asyncio.coroutine
    def walk(self, path):
        logger.debug("walk {}".format(path))
        if not path:
            return
        direction = path[0]
        distance = 1
        for new_direction in path[1:]:
            if direction == new_direction:
                distance += 1
                continue
            yield from self._walk(direction, distance)
            direction = new_direction
            distance = 1
        else:
            yield from self._walk(direction, distance)

    @asyncio.coroutine
    def _walk(self, direction, distance):
        x, y = self.position
        dx, dy = directions[direction]
        new_position = (x + distance * dx, y + distance * dy)
        # TODO: check if it is safe to proceed
        self.send_msg(dict(type="move", direction=direction, distance=distance))
        yield from asyncio.sleep((0.15 * distance) + 0.05)
        self.position = new_position

    def bomb(self, fuse_time):
        self.send_msg(dict(type="bomb", fuse_time=fuse_time))
        self.known_bombs.append(Bomb(self.position, now()+fuse_time))
        loop = asyncio.get_event_loop()

    def update_bombs(self, delta=2):
        # now2 = now() - 2
        # logger.info("update_bombs: {} {}".format(now2, self.known_bombs))
        # self.known_bombs = [b for b in self.known_bombs if b.fuse_time > now2]
        self.send_msg(dict(type="what_bombs"))
        loop.call_later(0.25, self.update_bombs)

    def connection_established(self):
        self.send_msg(dict(type="connect", username="hwm"))
        self.send_msg(dict(type="whoami"))
        self.send_msg(dict(type="map"))

    @asyncio.coroutine
    def update_ai(self):
        logger.debug("update ai")
        if self.data_consitent and not self.ai_running:
            self.ai_running = True
            try:
                info = self.get_best_move()
                path = info[3]
                hide_path = info[6]
                if not hide_path:
                    return
                logger.debug("go, {} b {}".format(path, hide_path))
                yield from self.walk(path)
                logger.debug(hide_path)
                fuse_time = len(hide_path) * 0.2 + 0.1
                self.bomb(fuse_time)
                yield from self.walk(hide_path)
                # yield from asyncio.sleep(len(hide_path)*0.05 + 0.1 + 2)
            finally:
                self.ai_running = False
                asyncio.async(self.update_ai())


    def update_internal_state(self):
        self.send_msg(dict(type="whoami"))
        self.send_msg(dict(type="map"))
        # yield from asyncio.sleep(2)

    @asyncio.coroutine
    def state_walking(self):
        pass

    def read_stdin(self):
        logger.debug("IN {}".format(repr(sys.stdin.readline())))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    c = HWM()
    asyncio.async(c.connect())
    loop.add_reader(sys.stdin, c.read_stdin)
    try:
        loop.run_forever()
    finally:
        loop.close()
