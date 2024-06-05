DATA_PACKAGE_SIZE = 240
DATASET_COUNT = 10
PPG_COUNT = 4
ACC_COUNT = 3

DATASET_SIZE = 24
PPG_SIZE = 3
ACC_SIZE = 2

ACC_NAME_LIST = ["X", "Y", "Z"]
PPG_NAME_LIST = ["GPPG", "BPPG", "IPPG", "YPPG"]
ALL_NAME_LIST = ACC_NAME_LIST + PPG_NAME_LIST

def parse_package_data(data_bytes):
    parsed_data = {name: [] for name in ALL_NAME_LIST}

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