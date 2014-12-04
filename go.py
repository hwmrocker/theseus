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
ch.setLevel(logging.ERROR)
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

    # def __init__(self, *args, **kw):
    #     super().__init__(*args, **kw)
    need_update = True
    final = False
    distance = 10

    def is_safe(self, pos, time_info, world):
        if time_info:
            from_time, to_time = time_info
            if (to_time < (self.fuse_time - 0.3)) or ((self.fuse_time + 2) < from_time):
                return True
        if self.need_update:
            self.update(world)
        if self.position == pos:
            return False
        for danger_zone in self.danger_zones:
            if pos in danger_zone:
                return False
        return True

    def update_fire_trails(self, fire_trails):
        self.need_update = False
        self.danger_zones = []
        for end_pos in fire_trails:
            fire_trail = []
            x, y = end_pos
            bx, by = self.position
            if x == bx:
                if y > by:
                    y_list = range(y, by, -1)
                else:
                    y_list = range(y+1, by+1)
                for by in y_list:
                    fire_trail.append((bx, by))
            elif y == by:
                if x > bx:
                    x_list = range(x, bx, -1)
                else:
                    x_list = range(x+1, bx+1)

                for bx in x_list:
                    fire_trail.append((bx, by))
            else:
                raise "Firetrails can only grow on x, or y axis"
            self.danger_zones.append(fire_trail)
        self.final = True

    def update(self, world):
        if self.final:
            return
        self.danger_zones = []
        try:
            x, y = self.position
        except ValueError:
            print(repr(self.position))
            raise
        for direction, (dx, dy) in directions.items():
            fire_trail = []
            for i in range(1, self.distance + 1):
                nx = x + i * dx
                ny = y + i * dy
                npos = (nx, ny)
                if not world.valid_map_pos(npos):
                    break

                tile = world.get_tile(npos)
                if tile == "W":
                    break
                elif tile == "M":
                    break
                fire_trail.append(npos)
            self.danger_zones.append(fire_trail)
        self.need_update = False
        # logger.error(self.danger_zones)


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
        return self.map[y][x]

    def valid_map_pos(self, pos):
        x, y = pos
        return 0 <= y < 49 and 0 <= x < 49
        # return 0 <= y < len(self.map) and 0 <= x < len(self.map[y])

    def get_tile_info(self, info):
        (nd, nmint, nmaxt, path, pos) = info
        bombscore = self._get_bomb_score(pos)
        for min_hide_distance, hide_path, endpos in self._get_min_hide_distance(pos):
            yield (nd, nmint, nmaxt, path, pos, bombscore, min_hide_distance, hide_path, endpos)

    def distance_counter(self, pos, info=None, direction=None):
        if info is None:
            return (0, 0., 0., [], pos)
        nd = info[0] + 1
        nmint = info[1] + 0.1
        nmaxt = info[2] + 0.2
        path = []
        if info:
            path = info[3][:]
            if direction:
                path.append(direction)
        ninfo = (nd, nmint, nmaxt, path, pos)
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

    def _get_min_hide_distance(self, pos, max_tiles=8):
        nb_tiles = self.get_neighbour_tiles(walkable=True, start_position=pos)
        distance = 100000
        path = []
        new_bomb = Bomb(pos, now())
        for npos, info in nb_tiles:
            if self._is_safe(npos, additional_bombs=[new_bomb]):
                distance = info[0]
                path = info[3][:]
                yield distance, path, npos
                max_tiles -= 1
                if max_tiles == 0:
                    break

    def _is_safe(self, pos, time_info=None, additional_bombs=None):
        bombs = self.known_bombs[:]
        if additional_bombs is not None:
            bombs += additional_bombs
        if time_info:
            right_now = now()
            from_time, to_time = time_info
            from_time += right_now
            to_time += right_now
            time_info = from_time, to_time

        for bomb in bombs:
            if not bomb.is_safe(pos, time_info, world=self):
                return False
        return True

    def get_neighbour_tiles(self, walkable=False, start_position=None, additional_bombs=None, extra_time=0):
        if start_position is None:
            start_position = self.position
        visited = set([])
        to_visit = [(start_position, self.distance_counter(start_position))]
        while to_visit:
            pos, info = to_visit.pop(0)
            x, y = pos
            visited.add(pos)
            if not self._is_safe(pos, (info[1], info[2] + extra_time), additional_bombs=additional_bombs):
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
                ninfo = self.distance_counter(npos, info, direction)
                to_visit.append((npos, ninfo))

    def get_bomb_and_hide_paths(self):
        paths = self.get_neighbour_tiles(walkable=True)
        for _, info in paths:
            yield from self.get_tile_info(info)

    def _score_endpos(self, endpos, bombpos, max_depth=3):
        # return 0
        additional_bombs = [Bomb(bombpos, now())]
        bombscore = 0
        for pos, info in self.get_neighbour_tiles(
                start_position=endpos,
                walkable=True,
                additional_bombs=additional_bombs,
                extra_time=2
                ):
            if info[0] > max_depth:
                break
            bombscore += self._get_bomb_score(pos)
        x, y = endpos
        return bombscore #+ self.heatmap[y][x]

    def get_best_move(self, max_depth=15):
        def score(distance, mint, maxt, path, bombpos, score, hide_distance, hide_path, endpos):
            if hide_path:
                bonus = 1000 if score > 0 else 0
                return ((score * 10) - maxt - (hide_distance * 3)) * 100 + self._score_endpos(endpos, bombpos) + bonus
            return (score * 10) - maxt - (hide_distance * 0.2) - 100000

        paths = self.get_bomb_and_hide_paths()
        info = next(paths)
        best_score = score(*info)
        best_info = info
        for info in paths:
            if info[0] > max_depth:
                break
            _score = score(*info)
            if _score > best_score:
                best_score = _score
                best_info = info

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

    def __init__(self, name="HWM", password="geheim", *args, **kw):
        super().__init__(*args, **kw)
        self.map = []
        self._ignore_list = []  # ignores unknown callbacks
        self._known_bombs = {}
        self.map_data_consistent = False
        self.position_data_consistent = False
        self.ai_running = False
        self.alive = False
        self.name = name
        self.password = password
        loop.call_later(1, self.update_bombs)

    @property
    def known_bombs(self):
        return list(self._known_bombs.values())

    @known_bombs.setter
    def known_bombs(self, value):
        return
        # if there is a bomb missing or fuse_time more than a second later
        # we need to check the mapdata again
        for b in self._known_bombs:
            found_match = False
            for _b in value:
                # TODO check this condition again
                if b.position == _b.position and (b.fuse_time - 1) < _b.fuse_time < (b.fuse_time + 1):
                    found_match = True
                    break
            if not found_match:
                self.map_data_consistent = False
                loop.call_soon(self.update_internal_state)
                for b in value:
                    b.need_update = True
                break
        self._known_bombs = value

    def get_or_create_bomb(self, pos, fuse_time):
        idx = "|".join(map(str, pos))
        try:
            return self._known_bombs[idx]
        except:
            self._known_bombs[idx] = Bomb(pos, fuse_time)
        return self._known_bombs[idx]

    def add_bomb(self, pos, fuse_time):
        logger.debug("add_bomb {}".format(pos))
        idx = "|".join(map(str, pos))
        self._known_bombs[idx] = Bomb(pos, fuse_time)

    def delete_bomb(self, pos, walls=None):
        logger.debug("delete_bomb {}".format(pos))
        idx = "|".join(map(str, pos))
        if idx in self._known_bombs:
            del self._known_bombs[idx]

        for pos in walls:
            x, y = pos
            self.map[y][x] = "g"
        for b in self.known_bombs:
            b.update(self.map)

    def set_fire_trails(self, pos, fire_trails, fuse_time=None):
        logger.debug("set_fire_trails {}".format(pos))
        idx = "|".join(map(str, pos))
        if not self._known_bombs[idx]:
            self.add_bomb(pos, fuse_time)
        self._known_bombs[idx].set_fire_trails(fire_trails)

    @property
    def data_consitent(self):
        print("m{} p{}".format(self.map_data_consistent, self.position_data_consistent))
        return self.map_data_consistent and self.position_data_consistent

    def inform(self, msg_type, data):
        if msg_type != "ERR":
            self.alive = True
        fn_name = "handle_{}".format(msg_type)
        if hasattr(self, fn_name):
            handler = getattr(self, fn_name)
            ret = handler(data)
            logger.debug("{}: {}".format(msg_type, ret))

        else:
            if msg_type not in self._ignore_list:
                self._ignore_list.append(msg_type)
                logger.error("No handler for {}".format(msg_type))

    def handle_MAP(self, mapstr):
        self.map = []
        for line in mapstr.splitlines():
            self.map.append([c for c in line])

        self.map_data_consistent = True
        asyncio.async(self.generate_heatmap())
        asyncio.async(self.update_ai())

    def generate_heatmap(self):
        self.heatmap = [[0] * 49] * 49
        for y, line in enumerate(self.map):
            for x, tile in enumerate(line):
                if tile == "W":
                    for _y, _line in enumerate(self.heatmap):
                        for _x, heat in enumerate(_line):
                            self.heatmap[_y][_x] += 100 - ((x - _x) ** 2 + abs(y - _y) ** 2) ** 0.5
                    yield from asyncio.sleep(0.01)

    def handle_WHOAMI(self, data):
        self.position = (round(data[3] / 10), round(data[2] / 10))
        logger.debug("WHOAMI: {}, {}".format(self.position, repr(data)))
        self.position_data_consistent = True
        asyncio.async(self.update_ai())

    def handle_BOMB(self, data):
        timed = now()
        new_bombs = []
        try:
            from_id, pos, fuse_time, state, extra = data
        except ValueError:
            print(repr(data))
            import sys
            sys.exit(0)
        logger.debug(data)
        if state == "ticking":
            self.add_bomb(pos, fuse_time + timed)
        elif state == "burning":
            # fuse_time = fuse_time + timed - 1.7
            bomb = self.get_or_create_bomb(pos, fuse_time + timed - 1.7)
            bomb.update_fire_trails(extra)
        elif state == "hiding":
            self.delete_bomb(pos, extra)
        # new_bombs.append()
        # self.known_bombs = new_bombs

    def handle_ERR(self, data):
        logger.error(data)
        if data == "you are dead":
            self.alive = False

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
    def _walk(self, direction, distance, timeout=5):
        x, y = self.position
        dx, dy = directions[direction]
        safe_distance = None
        new_position = (x + distance * dx, y + distance * dy)
        logger.debug("walk ... {} {}".format(direction, distance))
        while distance > 0:
            for i in range(1, distance + 1):
                _new_position = (x + i * dx, y + i * dy)
                if (not self._is_safe(new_position, time_info=(0.1 * i, 0.1 * i + 0.1))):
                    break
                safe_distance = i
                new_position = _new_position
                logger.debug("new safe position {}".format(new_position))
            logger.debug(" safe_distance {}".format(safe_distance))
            if safe_distance is None:
                raise Exception("Oh no")
            if safe_distance > 0:
                self.send_msg(dict(type="move", direction=direction, distance=safe_distance))
                yield from asyncio.sleep((0.15 * distance) + 0.05)
                self.position = new_position
                distance -= safe_distance
            else:
                if timeout > 0:
                    timeout -= 0.5
                    yield from asyncio.sleep(0.5)
                else:
                    raise Exception("Oh no block")

    def bomb(self, fuse_time):
        self.send_msg(dict(type="bomb", fuse_time=fuse_time))
        # self.known_bombs.append(Bomb(self.position, now()+fuse_time))
        self.add_bomb(self.position, now()+fuse_time)
        loop = asyncio.get_event_loop()

    def update_bombs(self, delta=2):
        # self.send_msg(dict(type="what_bombs"))
        # loop.call_later(0.25, self.update_bombs)
        pass

    def connection_established(self):
        self.send_msg(dict(type="connect", username=self.name, password=self.password, async=True))
        self.send_msg(dict(type="whoami"))
        self.send_msg(dict(type="map"))

    @asyncio.coroutine
    def update_ai(self):
        logger.debug("update ai")
        if self.data_consitent and self.alive and not self.ai_running:
            self.ai_running = True
            try:
                info = self.get_best_move()
                path = info[3]
                hide_path = info[7]
                if not hide_path:
                    return
                logger.debug("go, {} b {}".format(path, hide_path))
                yield from self.walk(path)
                logger.debug(hide_path)
                fuse_time = len(hide_path) * 0.2 + 0.3 + 0.5
                self.bomb(fuse_time)
                yield from self.walk(hide_path)
                # yield from asyncio.sleep(len(hide_path)*0.05 + 0.1 + 2)
            finally:
                self.ai_running = False
                yield from asyncio.sleep(0.5)
                asyncio.async(self.update_ai())
        else:
            yield from asyncio.sleep(0.5)
            asyncio.async(self.update_ai())

    def update_internal_state(self):
        self.send_msg(dict(type="whoami"))
        # self.send_msg(dict(type="map"))
        # yield from asyncio.sleep(2)

    @asyncio.coroutine
    def state_walking(self):
        pass

    def read_stdin(self):
        logger.debug("IN {}".format(repr(sys.stdin.readline())))


if __name__ == "__main__":
    import sys
    name = "Theseus"
    password = None
    if len(sys.argv) == 2:
        name = sys.argv[1]
    elif len(sys.argv) == 3:
        name = sys.argv[1]
        password = sys.argv[2]
    # print(sys.argv)
    # sys.exit(0)
    loop = asyncio.get_event_loop()
    c = HWM(name=name, password=password)
    asyncio.async(c.connect())
    loop.add_reader(sys.stdin, c.read_stdin)
    try:
        loop.run_forever()
    finally:
        loop.close()
