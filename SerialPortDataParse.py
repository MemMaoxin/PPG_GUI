from constants import ACC_NAME_LIST, PPG_NAME_LIST, ALL_NAME_LIST_AS_ONE
from constants import DATASET_COUNT, PPG_COUNT, ACC_COUNT
from constants import DATASET_SIZE, PPG_SIZE, ACC_SIZE


def parse_package_data(data_bytes):
    parsed_data = {name: [] for name in ALL_NAME_LIST_AS_ONE}

    for dataset in range(DATASET_COUNT):
        acc_start = dataset * DATASET_SIZE
        ppg_start = acc_start + ACC_COUNT * ACC_SIZE

        for acc in range(ACC_COUNT):
            index = acc_start + acc * ACC_SIZE
            acc_value = int.from_bytes(data_bytes[index:index+ACC_SIZE], byteorder='little', signed=True)
            parsed_data[ACC_NAME_LIST[acc]].append(acc_value)

        for ppg in range(PPG_COUNT):
            index = ppg_start + ppg * PPG_SIZE
            if ppg == 0 or ppg == 2:
                ppg_value = int.from_bytes(data_bytes[index:index+PPG_SIZE], byteorder='little', signed=False)
            else:
                last_ppg_value = (data_bytes[index] << 16 + data_bytes[index - 1]) & 0xA0A0
                ppg_value = (last_ppg_value << 16) | int.from_bytes(data_bytes[index+1:index+PPG_SIZE], byteorder='little', signed=False)
            parsed_data[PPG_NAME_LIST[ppg]].append(ppg_value)

    return parsed_data