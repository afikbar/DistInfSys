max_input_weights = 100


def get_new_weight(router, round, neighbor_count, degree):
    if round > max_input_weights:
        return None
    file_name = 'weights_router_' + str(router) + '.txt'
    weights_file = open(file_name, 'r')
    lines = weights_file.readlines()
    weights_file.close()
    line_num = (round - 1) * degree + neighbor_count
    line = lines[line_num].rstrip('\n')

    if line == 'None':
        return None
    return int(line)
