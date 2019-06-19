from socket import socket
from socket import AF_INET
from socket import SOCK_DGRAM
from threading import Thread
import random
import string
import time


def send(IP, port, message):
    sock_udp = socket(AF_INET, SOCK_DGRAM)
    sock_udp.sendto(message, (IP, port))
    sock_udp.close()


def send_and_receive(IP, port, message):
    sock_udp = socket(AF_INET, SOCK_DGRAM)
    sock_udp.sendto(message, (IP, port))
    data = sock_udp.recv(4096)
    sock_udp.close()
    if data.decode() != 'FINISHED':
        print('Neighbor In IP: ', IP, ' and port: ', port, 'failed')


def print_routing_table(network_size, UDP_port_start):
    message = 'PRINT-ROUTING-TABLE'.encode()
    for i in range(network_size, 0, -1):
        Thread(target=send, args=('127.0.0.1', UDP_port_start + i - 1, message)).start()


def shut_down(network_size, UDP_port_start):
    message = 'SHUT-DOWN'.encode()
    for i in range(0, network_size):
        Thread(target=send, args=('127.0.0.1', UDP_port_start + i, message)).start()


def update_routing_table(network_size, UDP_port_start):
    threads = []
    message = 'UPDATE-ROUTING-TABLE'.encode()
    for i in range(0, network_size):
        threads.append(Thread(target=send_and_receive, args=('127.0.0.1', UDP_port_start + i, message)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def route(network_size, UDP_port_start):
    destination = (random.randint(1, 1000) % network_size) + 1
    start = (random.randint(1, 1000) % network_size) + 1
    message_len = random.randint(1, 100)
    message = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(message_len))
    route_message = ('ROUTE' + ';' + str(destination) + ';' + message).encode()

    sock_udp = socket(AF_INET, SOCK_DGRAM)
    sock_udp.sendto(route_message, ('127.0.0.1', UDP_port_start + start - 1))
    sock_udp.close()


def test(network_size, UDP_port_start):
    random.seed(24563)
    print("\n Updating routing table #1")
    update_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)

    route(network_size, UDP_port_start)
    time.sleep(0.5)

    route(network_size, UDP_port_start)
    time.sleep(0.5)

    print_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)
    print("\n Updating routing table #2")
    update_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)

    print_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)
    print("\n Updating routing table #3")
    update_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)
    print("\n Updating routing table #4")
    update_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)

    print_routing_table(network_size, UDP_port_start)
    time.sleep(0.5)

    route(network_size, UDP_port_start)
    time.sleep(0.5)

    shut_down(network_size, UDP_port_start)
    time.sleep(1)


def main():
    network_size = int(input('Enter Network Size\n'))
    UDP_port_start = int(input('Enter UDP port\n'))
    test(network_size, UDP_port_start)


if __name__ == '__main__':
    main()
