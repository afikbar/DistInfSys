

def router(my_name):
    routing_table = []
    with open("input_router_{}.txt".format(my_name)) as file:
        lines = file.readlines()
        udp_port, tcp_port, network_size = lines[:3]
        neighs_data = lines[3:-2] # or look for asterisk?
        neighs = [neighs_data[i:i+4] for i in range(0, len(neighs_data), 4)]
        for neigh in neighs:
            #do somehting
    return routing_table