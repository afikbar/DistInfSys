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
        self.recv_from = self.src
        self.hops = int(hops)

    def get_weight(self, neigh) -> int:
        return self.neighbors[neigh]

    def to_message(self) -> str:
        lsp = "LSP;{};{};{};{}".format(self.recv_from, self.src, self.seq, self.hops)
        for neigh, weight in self.neighbors.items():
            lsp += ";{};{}".format(neigh, weight)

        return lsp

    def __eq__(self, other):
        return self.src == other.src and self.seq == other.seq

    def __gt__(self, other):
        return self.src == other.src and self.seq > other.seq

    def __getitem__(self, neigh) -> int:
        return self.neighbors[neigh]

    def __iter__(self):
        return iter(self.neighbors)

    @staticmethod
    def parse_lsp(data):
        # expected data is: LSP;[recv_from];[src];[sequence];[hops];[neighbor name];[edge weight]
        split_data = data.split(sep=';')[1:]
        recv_from, src, seq, hops, neighs = split_data[0], split_data[1], split_data[2], split_data[3], split_data[4:]
        neighs_dict = {int(neighs[i]): int(neighs[i + 1]) for i in range(0, len(neighs), 2)}
        lsp = LSP(src, seq, neighs_dict, hops)
        lsp.recv_from = recv_from
        return lsp


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
        self.edge_weight = int(edge_weight)
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
        self.listen_lock = Lock()
        self.listen = False
        self.table_lock = Lock()
        self.udp_output_lock = Lock()
        self.udp_output_handler = open("UDP_output_router_{}.txt".format(self.name), 'w')
        self.tcp_output_lock = Lock()
        self.tcp_output_handler = open("TCP_output_router_{}.txt".format(self.name), 'w')
        self.routing_table = {}  # {dest: {cost: , next: }}
        self.round = 1
        self.lsdb_lock = Lock()
        self.lsdb = LSDB(self.network_size)
        self.neighbors_lock = Lock()
        self.neighbors = {}  # {neigh:Node()}

    def create_lsp(self, seq):
        # get new weights
        with self.neighbors_lock:
            for neigh, node in self.neighbors.items():
                new_weight = get_new_weight(self.name, self.round, node.neighbor_order, len(self.neighbors))
                if new_weight:
                    node.edge_weight = new_weight
        self.lsdb.add_lsp(
            LSP(src=self.name,
                seq=seq,
                neighbors={neigh: node.edge_weight for neigh, node in self.neighbors.items()},
                hops=0)
        )

    def start_listeners(self):
        if not self.is_listen():
            with self.listen_lock:
                self.listen = True
            print("Start listening on router {}, UDP: {}, TCP: {}".format(self.name, self.udp_port, self.tcp_port))
            threads = [Thread(target=f, args=()) for f in [self.udp_listener, self.tcp_listener]]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        # return threads

    def stop_listeners(self):
        print("\nStop listening on router {}...".format(self.name))
        with self.listen_lock:
            self.listen = False
        with self.udp_output_lock:
            self.udp_output_handler.close()
        with self.tcp_output_lock:
            self.tcp_output_handler.close()
        self.udp_send(self.ip, self.udp_port, 'CLOSE')
        self.tcp_send(self.ip, self.tcp_port, 'CLOSE')

    def is_listen(self):
        with self.listen_lock:
            return self.listen

    def udp_listener(self):
        with socket(AF_INET, SOCK_DGRAM) as s:
            s.bind((self.ip, self.udp_port))
            while self.is_listen():
                data, (c_ip, c_port) = s.recvfrom(4096)
                # print("\n UDP Connection on Router {}, From {}:{}".format(self.name, c_ip, c_port))
                action = Thread(target=self.handle_message, args=(data, c_ip, c_port))
                action.start()

    def handle_conn(self, conn: socket, c_ip, c_port):
        # data = "".encode()
        # conn.settimeout(1)
        with conn:
            # # print("\n TCP Connection on Router {}, From {}:{}".format(self.name, c_ip, c_port))
            # while True:
            #     try:
            #         chunk = conn.recv(4096)
            #         if not chunk:
            #             break
            #         data += chunk
            #     except Exception as e:
            #         print("\nError on Router {} - {}. Tried to recv".format(self.name, e))
            data = conn.recv(4096)

        self.handle_message(data, c_ip, c_port)

    def tcp_listener(self):
        with socket(AF_INET, SOCK_STREAM) as s:
            s.bind((self.ip, self.tcp_port))
            s.listen(self.network_size ** 2)
            while self.is_listen():
                conn, (c_ip, c_port) = s.accept()
                # with conn:
                #     # print("\n TCP Connection on Router {}, From {}:{}".format(self.name, c_ip, c_port))
                #     data = conn.recv(4096)
                Thread(target=self.handle_conn, args=(conn, c_ip, c_port)).start()

    def handle_message(self, data: bytes, c_ip, c_port):
        message = data.decode()
        if message == 'PRINT-ROUTING-TABLE':
            self.write_routing_table()
        elif message == 'SHUT-DOWN':
            self.stop_listeners()
        elif message == 'UPDATE-ROUTING-TABLE':
            # print("\n Update Routing Table in router {}".format(self.name))
            self.update_routing_table(c_ip, c_port)
        elif message.startswith('ROUTE'):
            # print("\n Route in router {}, message: {} ".format(self.name, message))
            self.udp_route(message)
        elif message.startswith('LSP'):
            self.receive_lsp(message)

    def write_routing_table(self):
        with self.table_lock:
            lines = ["{};{}".format(*row.values()) for row in self.routing_table.values()]

        with self.udp_output_lock:
            self.udp_output_handler.write('\n'.join(lines) + '\n')
            # f.flush()

    def route(self, dest: int, is_udp):
        with self.table_lock:
            next_hop = self.routing_table[dest]['next']
        with self.neighbors_lock:
            next_ip, next_port = self.neighbors[next_hop].connection_info(is_udp=is_udp)

        return next_ip, next_port

    def udp_route(self, data):
        _, dest, message = data.split(sep=';')  # message doesn't contain ';'
        # print("Writing route to file: " + data)
        with self.udp_output_lock:
            self.udp_output_handler.write(data + '\n')
            # f.flush()

        # route to dest according to routing table
        dest = int(dest)
        if self.name != dest:
            self.udp_send(*self.route(dest, is_udp=True), data)

    def udp_send(self, ip, port, message: str):
        with socket(AF_INET, SOCK_DGRAM) as s:
            try:
                s.sendto(message.encode(), (ip, port))
            except Exception as e:
                print("\nError on Router {} - {}. Tried to send to router {}:{}".format(self.name, e, ip, port))

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

    def tcp_flood(self, node: Node, lsp: LSP):
        message = "UPDATE;{};{}".format(self.name, node.name)
        with self.tcp_output_lock:
            self.tcp_output_handler.write(message + '\n')
            # f.flush()
        self.tcp_send(node.ip, node.tcp_port, lsp.to_message())

    def flood_lsp(self, lsp: LSP):
        # expected data is: LSP;[recv_from];[src];[sequence];[neighbor name];[edge weight]
        threads = []
        if lsp.hops + 1 >= self.network_size:
            return
        lsp.hops += 1
        with self.neighbors_lock:
            for neigh, node in self.neighbors.items():
                if neigh in [lsp.recv_from, lsp.src]:
                    continue  # Dont send lsp to the node you received it from
                # action = Thread(target=self.tcp_flood, args=(node, lsp))
                # threads.append(action)
                # sleep(0.5)
                self.tcp_flood(node, lsp)

        # for action in threads:
        #     action.start()
        # for action in threads:
        #     action.join()

    def receive_lsp(self, data):
        # expected data is: LSP;[src];[sequence];[hops];[neighbor name];[edge weight]
        lsp = LSP.parse_lsp(data)
        with self.lsdb_lock:
            updated = self.lsdb.add_lsp(lsp)

        # forward to all
        # TODO: check if lsp should be flooded?
        if updated:
            self.flood_lsp(lsp)

    def update_routing_table(self, c_ip, c_port):
        with self.lsdb_lock:
            lsp = self.lsdb[self.name]
            # copy
            lsp = LSP(lsp.src, lsp.seq, {**lsp.neighbors}, lsp.hops)
        self.flood_lsp(lsp)
        # Wait until lsp is recieved from all
        while True:
            with self.lsdb_lock:
                if self.round <= self.lsdb.min_sequence():
                    break
        # Dijkstra
        with self.table_lock:
            for dest, entry in self.routing_table.items():
                if dest == self.name:
                    continue
                with self.lsdb_lock:
                    new_next, new_dist = dijkstra(self.lsdb.db, self.name, dest)
                    self.routing_table[dest] = table_entry(new_dist, new_next)

        # Update routing table

        # Increase round number
        self.round += 1

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
                curr_router.neighbors[name] = Node(name=name, ip=ip, udp_port=udp, tcp_port=tcp,
                                                   edge_weight=edge_weight,
                                                   neighbor_order=k)

        # build LSP right after updating weights (including new weights)
        curr_router.create_lsp(seq=1)

        curr_router.start_listeners()
        print("Finished on router: ", my_name)


# region Helper Functions
def table_entry(cost, next_hop):
    return {'cost': cost, 'next': next_hop}


def dijkstra(db, src, dest=None):
    # vertices from db as unvisited
    unvisited = list(db.keys())
    # Initialize dictionary of shortest distances
    D = {v: {'path': [], 'distance': 2 ** 31 - 1} for v in unvisited}
    D[src]['distance'] = 0
    # While all vertices haven't been yet visited
    while len(unvisited) > 0:
        # Select current node as min. of shortest distances so far computed
        min_dist, curr = min([(D[n]['distance'], n) for n in unvisited])
        # Add current node to its path
        D[curr]['path'].append(curr)
        # We're at the destination already
        if curr == dest:
            return D[dest]['path'][1], D[dest]['distance']
        # Loop over all neighboring vertices
        for neigh, dist in db[curr].neighbors.items():
            # make sure we haven't visited n already
            if neigh in unvisited:
                # compute distance to this neighbor through current vertex
                curr_dist = min_dist + dist
                # check if this distance is less than currently assigned
                # tentative distance
                if curr_dist < D[neigh]['distance']:
                    # re-assign shortest distance
                    D[neigh]['distance'] = curr_dist
                    # shortest path to this vertex is through current vertex
                    D[neigh]['path'] = D[curr]['path'][:]

        # Remove current node from unvisited ones
        unvisited.remove(curr)
    return D
