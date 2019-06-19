from socket import socket
from socket import error
from socket import AF_INET  # IPv4
from socket import SOCK_STREAM  # TCP
from socket import SOCK_DGRAM  # UDP
from socket import SHUT_RDWR
from socket import SHUT_WR
from threading import Thread
from threading import Lock
from weights import get_new_weight


# region LSP
class LSP(object):
    def __init__(self, src, seq, neighbors):
        '''
        creates lsp
        :param src: source router
        :param seq: sequence number of packet
        :param neighbors: dictionary of {neigh:weight}
        '''
        self.src = int(src)
        self.seq = int(seq)
        self.neighbors = neighbors

    def get_weight(self, neigh) -> float:
        return self.neighbors[neigh]

    def to_message(self) -> str:
        lsp = "LSP;{};{}".format(self.src, self.seq)
        for neigh, weight in self.neighbors.items():
            lsp += ";{};{}".format(neigh, weight)

        return lsp

    def __eq__(self, other):
        return self.src == other.src and self.seq == other.seq

    def __gt__(self, other):
        return self.src == other.src and self.seq > other.seq

    def __getitem__(self, neigh) -> float:
        return self.neighbors[neigh]

    def __iter__(self):
        return iter(self.neighbors)

    @staticmethod
    def parse_lsp(data):
        # expected data is: LSP;[src];[sequence];[neighbor name];[edge weight]
        split_data = data.split(sep=';')[1:]
        src, seq, neighs = split_data[0], split_data[1], split_data[2:]
        neighs_dict = {int(neighs[i]): float(neighs[i + 1]) for i in range(0, len(neighs), 2)}
        return LSP(src, seq, neighs_dict)


# endregion


# region LSDB
class LSDB(object):
    def __init__(self, network_size):
        # db of newest packet from each router (init with -1)
        self.db = {src: LSP(src, -1, None) for src in range(1, network_size + 1)}

    def add_lsp(self, lsp: LSP) -> bool:
        is_newer = lsp > self.db[lsp.src]
        self.db[lsp.src] = lsp if is_newer else self.db[lsp.src]
        return is_newer

    def get_lsp(self, src) -> LSP:
        return self.db[src]

    def min_sequence(self):
        return min([lsp.seq for lsp in self.db.values()])

    def __getitem__(self, src) -> LSP:
        return self.db[src]


# endregion


# region Node
class Node(object):
    def __init__(self, name, ip, udp_port, tcp_port, edge_weight, neighbor_order):
        self.name = name
        self.ip = ip.strip()
        self.udp_port = int(udp_port)
        self.tcp_port = int(tcp_port)
        self.edge_weight = float(edge_weight)
        self.neighbor_order = int(neighbor_order)

    def connection_info(self, is_udp: bool) -> (str, int):
        if is_udp:
            return self.ip, self.udp_port
        return self.ip, self.tcp_port


# endregion

# region Router
class Router(object):
    def __init__(self, name, udp, tcp, network_size, ip='127.0.0.1'):
        self.network_size = network_size
        self.name = name
        self.ip = ip
        self.udp_port = udp
        self.tcp_port = tcp
        self.listen = False
        self.table_lock = Lock()
        self.udp_output_lock = Lock()
        self.tcp_output_lock = Lock()
        self.routing_table = {}  # {dest: {cost: , next: }}
        self.round = 1
        self.lsdb_lock = Lock()
        self.lsdb = LSDB(self.network_size)
        self.neighbors_lock = Lock()
        self.neighbors = {}  # {neigh:Node()}

    def create_lsp(self, seq):
        self.lsdb.add_lsp(LSP(self.name,
                              seq,
                              {node.name: node.edge_weight for node in self.neighbors.values()})
                          )

    def start_listeners(self):
        if not self.is_listen():
            self.listen = True
            print("Start listening on router {}, UDP: {}, TCP: {}".format(self.name, self.udp_port, self.tcp_port))
            threads = [Thread(target=f, args=()) for f in [self.udp_listener, self.tcp_listener]]
            for thread in threads:
                thread.start()

        # return threads

    def stop_listeners(self):
        print("Stop listening...")
        self.listen = False

    def is_listen(self):
        return self.listen

    def udp_listener(self):
        with socket(AF_INET, SOCK_DGRAM) as s:
            s.bind((self.ip, self.udp_port))
            while self.is_listen():
                # while True:
                data, (c_ip, c_port) = s.recvfrom(4096)
                # if not data:
                #     break
                print("\n UDP Connection on Router {}, From {}:{}".format(self.name, c_ip, c_port))
                action = Thread(target=self.handle_message, args=(data, c_ip, c_port))
                action.start()

    def tcp_listener(self):
        with socket(AF_INET, SOCK_STREAM) as s:
            s.bind((self.ip, self.tcp_port))
            s.listen(self.network_size ** 2)
            while self.is_listen():
                conn, (c_ip, c_port) = s.accept()
                with conn:
                    print("\n TCP Connection on Router {}, From {}:{}".format(self.name, c_ip, c_port))
                    # while True:
                    data = conn.recv(4096)
                    # if not data:
                    #     break
                    # conn.sendall(data)
                    # self.handle_message(data)
                    action = Thread(target=self.handle_message, args=(data, c_ip, c_port))
                    action.start()

    def handle_message(self, data: bytes, c_ip, c_port):
        message = data.decode()
        if message == 'PRINT-ROUTING-TABLE':
            # DO PRINT
            self.write_routing_table()
        elif message == 'SHUT-DOWN':
            self.stop_listeners()
        elif message == 'UPDATE-ROUTING-TABLE':
            # do LINKSTATE
            # self.round += 1
            # do Update routing table
            print("\n Update Routing Table in router {}".format(self.name))
            self.update_routing_table(c_ip, c_port)
        elif message.startswith('ROUTE'):
            self.udp_route(message)
        elif message.startswith('LSP'):
            self.receive_lsp(message, c_ip, c_port)

    def write_routing_table(self):
        lines = ["{};{}".format(*row.values()) for row in self.routing_table.values()]
        filename_template = "UDP_output_router_{}.txt"

        with self.udp_output_lock:
            with open(filename_template.format(self.name), 'a') as f:
                f.write('\n'.join(lines) + '\n')

    def udp_route(self, data):
        _, dest, message = data.split(sep=';')  # message doesn't contain ';'
        filename = "UDP_output_router_{}.txt".format(self.name)
        with self.udp_output_lock:
            with open(filename, 'a') as f:
                f.write(data + '\n')

        # route to dest according to routing table
        dest = int(dest)
        if self.name != dest:
            with self.table_lock:
                next_hop = self.routing_table[dest]['next']
            with self.neighbors_lock:
                next_ip, next_port = self.neighbors[next_hop].connection_info(is_udp=True)

            self.udp_send(next_ip, next_port, message)

    def udp_send(self, ip, port, message: str):
        with socket(AF_INET, SOCK_DGRAM) as s:
            try:
                s.sendto(message.encode(), (ip, port))
            except Exception as e:
                print("\nError - {}, on Router {}, Tried to send to router {}:{}".format(e, self.name, ip, port))

    def tcp_send(self, ip, port, message):
        with socket(AF_INET, SOCK_STREAM) as s:
            try:
                s.connect((ip, port))
                s.sendall(message.encode())
                response = s.recv(4096)
                # what to do with response?
                return response
            except Exception as e:
                print("\nError on Router {} - {}. Tried to send to router {}:{}".format(self.name, e, ip, port))

    def tcp_flood(self, node: Node, lsp: str):
        filename = "TCP_output_router_{}.txt".format(self.name)
        message = "UPDATE;{};{}".format(self.name, node.name)
        with self.tcp_output_lock:
            with open(filename, 'a') as f:
                f.write(message + '\n')
        self.tcp_send(node.ip, node.tcp_port, lsp)

    def flood_lsp(self, lsp: str, skip_ip=None, skip_port=None):
        # expected data is: LSP;[src];[sequence];[neighbor name];[edge weight]
        with self.neighbors_lock:
            for neigh, node in self.neighbors.items():
                if node.ip == skip_ip and node.udp_port == skip_port:
                    continue  # Dont send lsp to the node you received it from
                Thread(target=self.tcp_flood, args=(node, lsp)).start()

    def receive_lsp(self, data, c_ip, c_port):
        # expected data is: LSP;[src];[sequence];[neighbor name];[edge weight]
        lsp = LSP.parse_lsp(data)
        with self.lsdb_lock:
            updated = self.lsdb.add_lsp(lsp)

        # forward to all
        # TODO: check if lsp should be flooded?
        if updated:
            self.flood_lsp(data)

    def update_routing_table(self, c_ip, c_port):
        with self.lsdb_lock:
            lsp = self.lsdb[self.name].to_message()
        self.flood_lsp(lsp)
        # TODO: Wait until lsp is recieved from all??
        while True:
            # with self.lsdb_lock:
            if self.round <= self.lsdb.min_sequence():
                break
        # Dijkstra
        with self.table_lock:
            for dest, entry in self.routing_table.items():
                if dest == self.name:
                    continue
                with self.lsdb_lock:
                    new_dist, new_next = dijkstra2(self.lsdb, self.name, dest)
                entry['cost'] = new_dist
                entry['next'] = new_next

        # Update routing table

        # Increase round number
        self.round += 1
        # get new weights
        with self.neighbors_lock:
            for neigh, node in self.neighbors.items():
                new_weight = get_new_weight(neigh, self.round, node.neighbor_order, len(self.neighbors))
                if new_weight:
                    node.edge_weight = new_weight

        # prepare LSP for next round
        self.create_lsp(seq=self.round)
        self.udp_send(c_ip, c_port, 'FINISHED')


# endregion


def router(my_name):
    my_name = int(my_name)
    with open("input_router_{}.txt".format(my_name)) as file:
        lines = file.readlines()
        udp_port, tcp_port, network_size = lines[:3]
        max_diameter_weighted = int(lines[-1])
        curr_router = Router(name=my_name, udp=int(udp_port), tcp=int(tcp_port), network_size=int(network_size))

        neighs_data = lines[3:-2]  # or look for asterisk?
        neighs_chunks = [neighs_data[i:i + 5] for i in range(0, len(neighs_data), 5)]
        first_neigh = int(neighs_chunks[0][0])
        init_route = table_entry(cost=max_diameter_weighted, next_hop=first_neigh)
        with curr_router.table_lock:
            # Assuming no 'holes' in router naming
            curr_router.routing_table = dict.fromkeys(range(1, int(network_size) + 1), init_route)
            curr_router.routing_table[my_name] = table_entry(cost=0, next_hop=None)
            for k, (name, ip, udp, tcp, edge_weight) in enumerate(neighs_chunks):
                name = int(name)
                new_weight = get_new_weight(name, 1, k, len(neighs_chunks))
                weight = new_weight if new_weight else edge_weight
                curr_router.neighbors[name] = Node(name=name, ip=ip, udp_port=udp, tcp_port=tcp, edge_weight=weight,
                                                   neighbor_order=k)
                # build LSP right after updating weights
                curr_router.create_lsp(seq=1)

        curr_router.start_listeners()


# region Helper Functions
def table_entry(cost, next_hop):
    return {'cost': cost, 'next': next_hop}


def dijkstra(lsdb: LSDB, src, dest, visited=[], distances={}, predecessors={}):
    """ calculates a shortest path tree routed in src
    """
    # a few sanity checks
    # if src not in lsdb:
    #     raise TypeError('The root of the shortest path tree cannot be found')
    # if dest not in lsdb:
    #     raise TypeError('The target of the shortest path cannot be found')
    # stop condition
    if src == dest:
        # We build the shortest path and display it
        path = []
        pred = dest
        while pred:
            path.append(pred)
            pred = predecessors.get(pred, None)
        return distances[dest], path[-2]
        # print('shortest path: ' + str(path) + " cost=" + str(distances[dest]))
    else:
        # if it is the initial  run, initializes the cost
        if not visited:
            distances[src] = 0
        # visit the neighbors
        for neigh, weight in lsdb[src].neighbors.items():
            if neigh not in visited:
                new_distance = distances[src] + weight
                if new_distance < distances.get(neigh, float('inf')):
                    distances[neigh] = new_distance
                    predecessors[neigh] = src
        # mark as visited
        visited.append(src)
        # now that all neighbors have been visited: recurse
        # select the non visited node with lowest distance 'x'
        # run Dijskstra with src='x'
        unvisited = {}
        for k in lsdb:
            if k not in visited:
                unvisited[k] = distances.get(k, float('inf'))
        x = min(unvisited, key=unvisited.get)
        return dijkstra(lsdb, x, dest, visited, distances, predecessors)


def dijkstra2(G, start, end=None):
    """
    Find shortest paths from the start vertex to all
    vertices nearer than or equal to the end.
    The input graph G is assumed to have the following
    representation: A vertex can be any object that can
    be used as an index into a dictionary.  G is a
    dictionary, indexed by vertices.  For any vertex v,
    G[v] is itself a dictionary, indexed by the neighbors
    of v.  For any edge v->w, G[v][w] is the length of
    the edge.  This is related to the representation in
    <http://www.python.org/doc/essays/graphs.html>
    where Guido van Rossum suggests representing graphs
    as dictionaries mapping vertices to lists of neighbors,
    however dictionaries of edges have many advantages
    over lists: they can store extra information (here,
    the lengths), they support fast existence tests,
    and they allow easy modification of the graph by edge
    insertion and removal.  Such modifications are not
    needed here but are important in other graph algorithms.
    Since dictionaries obey iterator protocol, a graph
    represented as described here could be handed without
    modification to an algorithm using Guido's representation.
    Of course, G and G[v] need not be Python dict objects;
    they can be any other object that obeys dict protocol,
    for instance a wrapper in which vertices are URLs
    and a call to G[v] loads the web page and finds its links.

    The output is a pair (D,P) where D[v] is the distance
    from start to v and P[v] is the predecessor of v along
    the shortest path from s to v.

    Dijkstra's algorithm is only guaranteed to work correctly
    when all edge lengths are positive. This code does not
    verify this property for all edges (only the edges seen
     before the end vertex is reached), but will correctly
    compute shortest paths even for some graphs with negative
    edges, and will raise an exception if it discovers that
    a negative edge has caused it to make a mistake.
    """

    D = {}  # dictionary of final distances
    P = {}  # dictionary of predecessors
    Q = priorityDictionary()  # est.dist. of non-final vert.
    Q[start] = 0

    for v in Q:
        D[v] = Q[v]
        if v == end: break

        for w in G[v]:
            vwLength = D[v] + G[v][w]
            if w in D:
                if vwLength < D[w]:
                    raise ValueError("Dijkstra: found better path to already-final vertex")
            elif w not in Q or vwLength < Q[w]:
                Q[w] = vwLength
                P[w] = v
    Path = []
    while True:
        Path.append(end)
        if end == start: break
        end = P[end]
    Path.reverse()
    return D[end], Path[1]


# endregion


# Priority dictionary using binary heaps
# David Eppstein, UC Irvine, 8 Mar 2002


class priorityDictionary(dict):
    def __init__(self):
        '''Initialize priorityDictionary by creating binary heap
of pairs (value,key).  Note that changing or removing a dict entry will
not remove the old pair from the heap until it is found by smallest() or
until the heap is rebuilt.'''
        self.__heap = []
        dict.__init__(self)

    def smallest(self):
        '''Find smallest item after removing deleted items from heap.'''
        if len(self) == 0:
            raise IndexError("smallest of empty priorityDictionary")
        heap = self.__heap
        while heap[0][1] not in self or self[heap[0][1]] != heap[0][0]:
            lastItem = heap.pop()
            insertionPoint = 0
            while 1:
                smallChild = 2 * insertionPoint + 1
                if smallChild + 1 < len(heap) and \
                        heap[smallChild] > heap[smallChild + 1]:
                    smallChild += 1
                if smallChild >= len(heap) or lastItem <= heap[smallChild]:
                    heap[insertionPoint] = lastItem
                    break
                heap[insertionPoint] = heap[smallChild]
                insertionPoint = smallChild
        return heap[0][1]

    def __iter__(self):
        '''Create destructive sorted iterator of priorityDictionary.'''

        def iterfn():
            while len(self) > 0:
                x = self.smallest()
                yield x
                del self[x]

        return iterfn()

    def __setitem__(self, key, val):
        '''Change value stored in dictionary and add corresponding
pair to heap.  Rebuilds the heap if the number of deleted items grows
too large, to avoid memory leakage.'''
        dict.__setitem__(self, key, val)
        heap = self.__heap
        if len(heap) > 2 * len(self):
            self.__heap = [(v, k) for k, v in self.iteritems()]
            self.__heap.sort()  # builtin sort likely faster than O(n) heapify
        else:
            newPair = (val, key)
            insertionPoint = len(heap)
            heap.append(None)
            while insertionPoint > 0 and \
                    newPair < heap[(insertionPoint - 1) // 2]:
                heap[insertionPoint] = heap[(insertionPoint - 1) // 2]
                insertionPoint = (insertionPoint - 1) // 2
            heap[insertionPoint] = newPair

    def setdefault(self, key, val):
        '''Reimplement setdefault to call our customized __setitem__.'''
        if key not in self:
            self[key] = val
        return self[key]
