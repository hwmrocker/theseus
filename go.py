import asyncio
import msgpack


directions = {
# direction: (left, top)
    "w": (0, -1),
    "a": (-1, 0),
    "s": (0, 1),
    "d": (1, 0),
}


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
            if self._is_safe(npos, additional_bombs=[pos]):
                distance = info[0]
                path = info[3][:]
                break
        return distance, path

    def _is_safe(self, pos, additional_bombs=None, distance=10):
        if additional_bombs is None:
            additional_bombs = []
        danger_zone = []
        for x, y in additional_bombs:
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
            # print(" s{}: {}".format(_score, info))
            if _score > best_score:
                best_score = _score
                best_info = info
                # print ("new highscore")
            # print("  s{} {}".format(best_score, best_info))

        print("ret s{} {}".format(best_score, best_info))
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
        print("send: {}".format(msg))
        pack = msgpack.packb(msg)
        self.writer.write(pack)

    def close(self):
        if self.writer:
            self.writer.write_eof()

    def inform(self, *msg):
        print(msg)

    @asyncio.coroutine
    def connect(self):
        print('Connecting...')
        try:
            reader, writer = yield from asyncio.open_connection(self.host, self.port)
            # asyncio.async(self.create_input())
            self.reader = reader
            self.writer = writer
            self.send_msg(dict(type="connect", username="hwm"))
            self.sockname = writer.get_extra_info('sockname')
            unpacker = msgpack.Unpacker(encoding='utf-8')
            while not reader.at_eof():
                pack = yield from reader.read(1024)
                unpacker.feed(pack)
                for msg in unpacker:
                    self.inform(*msg)
            print('The server closed the connection')
            self.writer = None
        except ConnectionRefusedError as e:
            print('Connection refused: {}'.format(e))
            self.close()


class HWM(NetworkClient):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.map = []
        self._ignore_list = []  # ignores unknown callbacks

    def inform(self, msg_type, data):
        try:
            handler = getattr(self, "handle_{}".format(msg_type))
            ret = handler(data)
            print("{}: {}".format(msg_type, ret))

        except AttributeError:
            if msg_type not in self._ignore_list:
                self._ignore_list.append(msg_type)
                print("No handler for {}".format(msg_type))

    def handle_MAP(self, mapstr):
        self.map = []
        for line in mapstr.splitlines():
            self.map.append([c for c in line])
        # print(mapstr)

    def handle_WHOAMI(self, data):
        self.position = (round(data[3] / 10), round(data[2] / 10))
        print("WHOAMI: {}, {}".format(self.position, repr(data)))

    @asyncio.coroutine
    def walk(self, path):
        print("walk {}".format(path))
        # for direction in path:
        #     self.send_msg(dict(type="move", direction=direction, distance=1))
        #     yield from asyncio.sleep(0.15)
        # return
        if not path:
            return
        d = path[0]
        counter = 1
        for newd in path[1:]:
            if d == newd:
                counter += 1
                continue
            self.send_msg(dict(type="move", direction=d, distance=counter))
            yield from asyncio.sleep((0.15 * counter) + 0.05)
            d = newd
            counter = 1
        else:
            self.send_msg(dict(type="move", direction=d, distance=counter))
            yield from asyncio.sleep((0.15 * counter) + 0.05)

    @asyncio.coroutine
    def ai_loop(self):
        yield from asyncio.sleep(0.5)

        while True:

            self.send_msg(dict(type="whoami"))
            self.send_msg(dict(type="map"))
            yield from asyncio.sleep(2)

            info = self.get_best_move()
            path = info[3]
            hide_path = info[6]
            print("go, {} b {}".format(path, hide_path))
            # for direction in path:
            #     self.send_msg(dict(type="move", direction=direction, distance=1))
            #     yield from asyncio.sleep(0.15)
            yield from self.walk(path)
            print(hide_path)
            fuse_time = len(hide_path) * 0.2 + 0.1
            self.send_msg(dict(type="bomb", fuse_time=fuse_time))
            yield from self.walk(hide_path)

            # for direction in hide_path:
            #     self.send_msg(dict(type="move", direction=direction, distance=1))
            #     yield from asyncio.sleep(0.15)

            yield from asyncio.sleep(len(hide_path)*0.05 + 0.1 + 2)


if __name__ == "__main__":
    c = HWM()
    asyncio.async(c.connect())
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(c.ai_loop())
    finally:
        loop.close()
