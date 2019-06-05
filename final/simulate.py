import random
from router import router
from threading import Thread


def get_initial_weight():
    return random.randint(1, 100)


def routers_input_weights(pick_neighbor_prob, UDP_port, TCP_port, network_size, dont_change_weight_prob,
                          max_update_rounds):
    total_weight = 0
    for router in range(1, network_size + 1):
        router_UDP_port = UDP_port + router - 1
        router_TCP_port = TCP_port + router - 1

        neighbor = (router % network_size) + 1
        neighbor_UDP_port = UDP_port + neighbor - 1
        neighbor_TCP_port = TCP_port + neighbor - 1

        input_file_name = 'input_router_' + str(router) + '.txt'
        weights_file_name = 'weights_router_' + str(router) + '.txt'
        input_file = open(input_file_name, 'w')

        input_file.write(str(router_UDP_port) + '\n')
        input_file.write(str(router_TCP_port) + '\n')
        input_file.write(str(network_size) + '\n')
        input_file.write(str(neighbor) + '\n')
        input_file.write('127.0.0.1\n')
        input_file.write(str(neighbor_UDP_port) + '\n')
        input_file.write(str(neighbor_TCP_port) + '\n')
        weight = get_initial_weight()
        total_weight = total_weight + weight
        input_file.write(str(weight) + '\n')

        neighbors_count = 1

        for new_neighbor in range(1, network_size + 1):
            if new_neighbor == router or new_neighbor == neighbor:
                continue
            prob = random.random()
            if prob < pick_neighbor_prob:
                neighbors_count = neighbors_count + 1
                new_neighbor_UDP_port = UDP_port + new_neighbor - 1
                new_neighbor_TCP_port = TCP_port + new_neighbor - 1
                input_file.write(str(new_neighbor) + '\n')
                input_file.write('127.0.0.1\n')
                input_file.write(str(new_neighbor_UDP_port) + '\n')
                input_file.write(str(new_neighbor_TCP_port) + '\n')
                weight = get_initial_weight()
                total_weight = total_weight + weight
                input_file.write(str(weight) + '\n')
        input_file.close()

        weights_file = open(weights_file_name, 'w')
        for i in range(0, max_update_rounds):
            for j in range(0, neighbors_count):
                prob = random.random()
                if prob < dont_change_weight_prob:
                    weight_prob = random.randint(1, 100)
                    weights_file.write(str(weight_prob) + '\n')
                else:
                    weights_file.write('None\n')
        weights_file.close()

    for router in range(1, network_size + 1):
        file_name = 'input_router_' + str(router) + '.txt'
        file = open(file_name, 'a')
        file.write('*\n')
        file.write(str(total_weight) + '\n')
        file.close()


# Constructs and simulates a network.
def main():
    random.seed(53689)
    pick_neighbor_prob = 0.1
    UDP_port_start = 31000
    TCP_port_start = 41000
    dont_change_weight_prob = 0.3
    max_update_rounds = 100

    try:
        network_size = int(input('Enter network size \n'))
    except:
        print('ERROR--network size')

    routers_input_weights(pick_neighbor_prob, UDP_port_start, TCP_port_start, network_size, dont_change_weight_prob,
                          max_update_rounds)

    threads = []
    for i in range(1, network_size + 1):
        threads.append(Thread(target=router, args=(i,)))

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()


if __name__ == '__main__':
    main()
