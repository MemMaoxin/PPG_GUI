import pyqtgraph as pg
import array
import serial
import threading
import numpy as np
from queue import Queue
import time
from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import Qt
import inspect
import ctypes
from SerialPortDataParse import parse_package_data

#  pyqtgraph PyQt5 pyserial

DISPLAY_SECONDS = 5

pw = []
devices_name_label = []

allPanelNameList = ["PPG", "ACC"]
panelCount = len(allPanelNameList)
panelSampleFrequency = [250, 250]
panelDataLength = np.dot(panelSampleFrequency, DISPLAY_SECONDS)
ppgChannelNameList = ["GPPG", "BPPG", "IPPG", "YPPG"]
accChannelNameList = ["X", "Y", "Z"]
allChannelNameList = [ppgChannelNameList, accChannelNameList]

colors = [
            '#1f77b4', # Blue
            '#ff7f0e', # Orange
            '#2ca02c', # Green
            '#d62728', # Red
            '#9467bd', # Purple
            '#8c564b', # Brown
            '#e377c2', # Pink
            '#7f7f7f', # Gray
            '#bcbd22', # Yellow-Green
            '#17becf'  # Cyan
        ]

allQueueDict = {}
allDataArrayDict = {}
allCurveDict = {}
allIndexDict = {}
allProcess = {}
allXScale = {}
allDataLength = {}

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

############################################
port = "COM5"
baudrate = 250000
samplingRate = 32
plotDuration = 5
############################################

def serial_xx():
    ser = serial.Serial(port, baudrate)
    data_bytes = bytearray()
    package_size = 242

    while True:
        count = ser.inWaiting()
        if count:
            rec_str = ser.read(count)
            data_bytes = data_bytes + rec_str
            data_len = len(data_bytes)
            k = 0
            while k + package_size + 2 < data_len:
                if data_bytes[k] == 0X16 and data_bytes[k + 1] == 0X00 and data_bytes[k + package_size] == 0X16 and data_bytes[k + package_size + 1] == 0X00:

                    rawDict = parse_package_data(data_bytes[k + 2 : k + package_size])
                    for panel in range(panelCount):
                        for channelName in allChannelNameList[panel]:
                            values = rawDict[channelName]
                            if isinstance(values, list):
                                for i, value in enumerate(values):
                                    allQueueDict[channelName].put(value)
                            elif isinstance(values, int):
                                for i, value in enumerate([values]):
                                    allQueueDict[channelName].put(value)
                    k = k + package_size

                else:
                    k = k + 1

            data_bytes[0:k] = b''


class MainWidget(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPG")  # 设置窗口标题
        main_widget = QtWidgets.QWidget()  # 实例化一个widget部件
        main_layout = QtWidgets.QGridLayout()  # 实例化一个网格布局层
        main_widget.setLayout(main_layout)  # 设置主widget部件的布局为网格布局
        main_widget.setStyleSheet('QWidget{background:white;}')  # 设置背景为白色

        for k in range(panelCount):
            pw.insert(k, pg.PlotWidget(enableAutoRange=True))
            pw[k].setLabel(axis='bottom', text='Time / s')
            pw[k].setLabel(axis='left', text='Amplitude')
            pw[k].setBackground("w")

            devices_name_label.insert(k, QtWidgets.QLabel())
            devices_name_label[k].setAlignment(Qt.AlignCenter)
            devices_name_label[k].setStyleSheet("color: #000000; font-size:24px; font-weight:bold")
            devices_name_label[k].setText(allPanelNameList[k])
            
            pw[k].addLegend()
            channelNameList = allChannelNameList[k]
            for channelName, color in zip(channelNameList, colors):
                allQueueDict[channelName] = Queue(maxsize=200)
                dataLength = panelDataLength[k]
                allDataArrayDict[channelName] = np.zeros(dataLength).__array__('d')
                allIndexDict[channelName] = 0
                allDataLength[channelName] = dataLength
                allXScale[channelName] = [x * DISPLAY_SECONDS / dataLength for x in range(dataLength)]
                allCurveDict[channelName] = pw[k].plot(allDataArrayDict[channelName], x = allXScale[channelName], name = channelName, pen = pg.mkPen(color = color))
                
            
            main_layout.addWidget(devices_name_label[k], 1 + 2 * k, 1, 1, 5)
            main_layout.addWidget(pw[k], 2 + 2 * k, 1, 1, 5)
            

        self.create_curve_selection()
        main_layout.addWidget(self.curve_selection_group, 2, 6, 3, 1)
        
        self.setCentralWidget(main_widget)

    def create_curve_selection(self):
        self.curve_selection_layout = QtWidgets.QVBoxLayout()
        self.curve_selection_group = QtWidgets.QGroupBox("Select Curves")
        self.curve_selection_group.setLayout(self.curve_selection_layout)

        for panel in range(panelCount):
            for channelName in allChannelNameList[panel]:
                checkbox = QtWidgets.QCheckBox(channelName)
                checkbox.setChecked(True)
                checkbox.stateChanged.connect(lambda state, name=channelName: self.toggle_curve(name, state))
                self.curve_selection_layout.addWidget(checkbox)
    
    def toggle_curve(self, channel_name, state):
        curve = allCurveDict.get(channel_name)
        if curve:
            curve.setVisible(state == Qt.Checked)
        
    def closeEvent(self, event):
        result = QtWidgets.QMessageBox.question(self, "Impedance", "Do you want to exit?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if result == QtWidgets.QMessageBox.Yes:
            stop_thread(thread_serial_port)
            print("Close successfully")
            event.accept()
        else:
            event.ignore()


def consumer_ppg(channelName):
    while True:
        raw_data = allQueueDict[channelName].get()
        index_on_time = allIndexDict[channelName]
        if index_on_time < allDataLength[channelName]:
            allDataArrayDict[channelName][index_on_time] = raw_data
            allIndexDict[channelName] = index_on_time + 1

        else:
            allDataArrayDict[channelName][:-1] = allDataArrayDict[channelName][1:]
            allDataArrayDict[channelName][index_on_time - 1] = raw_data

def plot_data():
    for i in range(panelCount):
        for channelName in allChannelNameList[i]:
            allCurveDict[channelName].setData(allXScale[channelName], allDataArrayDict[channelName])



if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    gui = MainWidget()
    thread_serial_port = threading.Thread(target=serial_xx, daemon=True)
    thread_serial_port.start()
    gui.show()
    
    timer_plot = pg.QtCore.QTimer()
    timer_plot.timeout.connect(plot_data)  # 定时刷新数据显示
    timer_plot.start(25)  # 多少ms调用一次

    for i in range(panelCount):
        for channelName in allChannelNameList[i]:
            allProcess[channelName] = threading.Thread(target=consumer_ppg, args=(channelName,), daemon=True)
            allProcess[channelName].start()

    sys.exit(app.exec_())