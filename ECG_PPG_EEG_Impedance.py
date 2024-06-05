import pyqtgraph as pg
import array
import serial
import threading
import numpy as np
from queue import Queue
import time
from PyQt5 import QtWidgets
import sys
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import Qt
import inspect
import ctypes

#  pyqtgraph PyQt5 pyserial

file_open_flag = False
sample_frequency = 250
display_seconds = 10
package_size = 242
dataset_size = 24
dataset_count = 10
led_count = 4
led_size = 3
data_length = sample_frequency * display_seconds
curve = []
data = []
data_bytes = bytearray()
pw = []
que = []
index_now = []
process = []
custom_file = []
velocity = []
label = []
rate = []

devices_name = ["GPPG", "BPPG", "IPPG", "YPPG"]
devices_name_label = []

x_scale = [i1 * 10 / data_length for i1 in range(data_length)]

def _async_raise(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def stop_thread(thread):
    _async_raise(thread.ident, SystemExit)

def serial_xx():
    global data_bytes
    while True:
        count = mSerial.inWaiting()
        if count:
            rec_str = mSerial.read(count)
            data_bytes = data_bytes + rec_str
            data_len = len(data_bytes)
            k = 0
            while k + package_size + 2 < data_len:  # pacakge size is 242
                if data_bytes[k] == 0X16 and data_bytes[k + 1] == 0X00 and data_bytes[k + package_size] == 0X16 and data_bytes[k + package_size + 1] == 0X00:
                    for dataset in range(dataset_count):
                        for led in range(led_count):
                            start_index = k + 8 + dataset * dataset_size + led * led_size
                            ppg_value = 0
                            if led == 0 or led == 2:
                                ppg_value = (data_bytes[start_index + 1] << 16) | (data_bytes[start_index + 0] << 8) | (data_bytes[start_index + 3])
                            else:
                                last_ppg_value = (data_bytes[start_index] << 16 + data_bytes[start_index - 1]) & 170
                                ppg_value = (last_ppg_value << 16) |  (data_bytes[start_index + 2] << 8) | data_bytes[start_index + 1]

                            que[led].put(ppg_value)
                            rate[led] = rate[led] + 1
                    k = k + package_size

                else:
                    k = k + 1

            data_bytes[0:k] = b''


class MainWidget(QtWidgets.QMainWindow):
    def action_save(self):
        global custom_file, file_open_flag

        if self.saveButton.text() == "SaveData":
            self.saveButton.setText("StopSaveData")
            custom_file_name = QFileDialog.getSaveFileName(self,
                                                         "文件保存",
                                                         "./",
                                                         "Text Files (*.txt)")
            if not custom_file_name:
                custom_file_name = "default.txt"
            custom_file = open(custom_file_name, 'w')
            custom_file.write('PPG data of wrist band')
            file_open_flag = True
        elif self.saveButton.text() == "StopSaveData":
            self.saveButton.setText("SaveData")
            file_open_flag = False
            custom_file.close()

    @staticmethod
    def action_refresh():
        mSerial.write(("A" + "\r\n").encode())

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPG")  # 设置窗口标题
        main_widget = QtWidgets.QWidget()  # 实例化一个widget部件
        main_layout = QtWidgets.QGridLayout()  # 实例化一个网格布局层
        main_widget.setLayout(main_layout)  # 设置主widget部件的布局为网格布局
        main_widget.setStyleSheet('QWidget{background:white;}')  # 设置背景为白色

        for k in range(led_count):
            pw.insert(k, pg.PlotWidget(enableAutoRange=True))
            pw[k].setLabel(axis='bottom', text='Time / s')
            pw[k].setLabel(axis='left', text='Amplitude')
            pw[k].setBackground("w")

            data.insert(k, array.array('i'))
            data[k] = np.zeros(data_length).__array__('d')

            que.insert(k, Queue(maxsize=2000))
            index_now.insert(k, 0)
            label.insert(k, QtWidgets.QLabel())
            label[k].setAlignment(Qt.AlignCenter)
            label[k].setText(' Receiving rate:  0 % ')

            devices_name_label.insert(k, QtWidgets.QLabel())
            devices_name_label[k].setAlignment(Qt.AlignCenter)
            devices_name_label[k].setStyleSheet("color: #000000; font-size:24px; font-weight:bold")
            devices_name_label[k].setText(devices_name[k])

            rate.insert(k, 0)
            velocity.insert(k, 0)

        for k, p, d, color in zip(range(led_count), pw, data, ['#FF8C00', '#6495ED', '#FF6347', '#BA55D3', '#666666']):
            # 深橙色、矢车菊蓝、番茄色、板岩暗蓝灰色 https://www.sioe.cn/yingyong/yanse-rgb-16/
            curve.insert(k, (p.plot(d, x=x_scale, pen=pg.mkPen(color=color))))
            main_layout.addWidget(devices_name_label[k], 1 + 3 * k, 1, 1, 5)
            main_layout.addWidget(pw[k], 2 + 3 * k, 1, 1, 5)
            main_layout.addWidget(label[k], 3 + 3 * k, 1, 1, 3)


        # 保存按钮
        self.saveButton = QtWidgets.QPushButton(main_widget)
        self.saveButton.setText("SaveData")
        self.saveButton.setStyleSheet("QPushButton{color:#FFA500}"
                                      "QPushButton:hover{color:#DC143C}"
                                      "QPushButton{background-color:#000000}"
                                      "QPushButton{border:1px}"
                                      "QPushButton{border-radius:10px}"
                                      "QPushButton{padding:6px 6px}"
                                      "QPushButton{font:bold 20px}")
        self.saveButton.clicked.connect(self.action_save)
        main_layout.addWidget(self.saveButton, 16, 1, 1, 5)

        self.setCentralWidget(main_widget)  # 设置窗口默认部件为主widget

    def closeEvent(self, event):
        result = QtWidgets.QMessageBox.question(self, "Impedance", "Do you want to exit?",
                                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if result == QtWidgets.QMessageBox.Yes:
            stop_thread(thread_serial_port)
            print("Close successfully")
            event.accept()
        else:
            event.ignore()


def consumer_ppg(index):
    while True:
        raw_data = que[index].get()
        if index_now[index] < data_length:
            data[index][index_now[index]] = raw_data
            index_now[index] = index_now[index] + 1

        else:
            data[index][:-1] = data[index][1:]
            data[index][index_now[index] - 1] = raw_data

def plot_data():
    for led in range(led_count):
        curve[led].setData(x_scale, data[led])

def rate_refresh():
    for k in range(led_count):
        velocity[k] = rate[k] - velocity[k]
        valid = velocity[k]
        receiving_rate = valid * 100 / (3 * 250)
        velocity[k] = rate[k]
        label[k].setText(' Efficiency:  %d %%' % receiving_rate)


if __name__ == "__main__":
    # 设置端口号及波特率
    port_xx = "COM5"
    bps = 250000
    # 串口执行到这已经打开 再用open命令会报错
    mSerial = serial.Serial(port_xx, int(bps))
    if mSerial.isOpen():
        print("Open successfully")
        mSerial.flushInput()  # 清空缓冲区

    else:
        print("open failed")
        mSerial.close()  # 关闭端口
    app = QtWidgets.QApplication(sys.argv)
    gui = MainWidget()
    thread_serial_port = threading.Thread(target=serial_xx, daemon=True)
    thread_serial_port.start()
    gui.show()
    
    timer_plot = pg.QtCore.QTimer()
    timer_plot.timeout.connect(plot_data)  # 定时刷新数据显示
    timer_plot.start(30)  # 多少ms调用一次
    
    timer_rate_refresh = pg.QtCore.QTimer()
    timer_rate_refresh.timeout.connect(rate_refresh)  # 定时刷新数据显示
    timer_rate_refresh.start(3000)  # 多少ms调用一次

    for i in range(led_count):
        process.insert(i, threading.Thread(target=consumer_ppg, args=(i,), daemon=True))
        process[i].start()

    sys.exit(app.exec_())
