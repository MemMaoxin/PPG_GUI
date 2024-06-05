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
from constants import ALL_NAME_LIST
from color import COLORS

from SerialPortDataParse import parse_package_data
from color import COLORS
from constants import ALL_NAME_LIST

# Constants
DISPLAY_SECONDS = 10
PORT = "COM5"
BAUDRATE = 250000
PACKAGE_SIZE = 242

# Global Variables
pw = []
devices_name_label = []
allPanelNameList = ["PPG", "ACC"]
PANEL_COUNT = len(allPanelNameList)
panelSampleFrequency = [250, 250]
panelDataLength = np.multiply(panelSampleFrequency, DISPLAY_SECONDS)

allQueueDict = {}
allDataArrayDict = {}
allCurveDict = {}
allIndexDict = {}
allProcess = {}
allXScale = {}
allDataLength = {}

def _async_raise(tid, exctype):
    """Raises an exception in the threads with id tid"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        tid, ctypes.py_object(exctype)
    )
    if res == 0:
        raise ValueError("Invalid thread id")
    elif res != 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def stop_thread(thread):
    _async_raise(thread.ident, SystemExit)

def serial_thread():
    ser = serial.Serial(PORT, BAUDRATE)
    data_bytes = bytearray()

    while True:
        count = ser.inWaiting()
        if count:
            rec_str = ser.read(count)
            data_bytes += rec_str
            data_len = len(data_bytes)
            k = 0
            while k + PACKAGE_SIZE + 2 < data_len:
                if (
                    data_bytes[k] == 0x16
                    and data_bytes[k + 1] == 0x00
                    and data_bytes[k + PACKAGE_SIZE] == 0x16
                    and data_bytes[k + PACKAGE_SIZE + 1] == 0x00
                ):
                    rawDict = parse_package_data(
                        data_bytes[k + 2 : k + PACKAGE_SIZE]
                    )
                    for panel in range(PANEL_COUNT):
                        for channelName in ALL_NAME_LIST[panel]:
                            values = rawDict[channelName]
                            if isinstance(values, list):
                                for value in values:
                                    allQueueDict[channelName].put(value)
                            elif isinstance(values, int):
                                allQueueDict[channelName].put(values)
                    k += PACKAGE_SIZE
                else:
                    k += 1
            data_bytes = data_bytes[k:]

class MainWidget(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPG")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QGridLayout()
        main_widget.setLayout(main_layout)
        main_widget.setStyleSheet("QWidget{background:white;}")

        for k in range(PANEL_COUNT):
            pw.append(pg.PlotWidget(enableAutoRange=True))
            pw[k].setLabel(axis="bottom", text="Time / s")
            pw[k].setLabel(axis="left", text="Amplitude")
            pw[k].setBackground("w")

            devices_name_label.append(QtWidgets.QLabel())
            devices_name_label[k].setAlignment(Qt.AlignCenter)
            devices_name_label[k].setStyleSheet(
                "color: #000000; font-size:24px; font-weight:bold"
            )
            devices_name_label[k].setText(allPanelNameList[k])

            pw[k].addLegend()
            channelNameList = ALL_NAME_LIST[k]
            for channelName, color in zip(channelNameList, COLORS):
                allQueueDict[channelName] = Queue(maxsize=200)
                dataLength = panelDataLength[k]
                allDataArrayDict[channelName] = np.zeros(dataLength, dtype=float)
                allIndexDict[channelName] = 0
                allDataLength[channelName] = dataLength
                allXScale[channelName] = [
                    x * DISPLAY_SECONDS / dataLength for x in range(dataLength)
                ]
                allCurveDict[channelName] = pw[k].plot(
                    allDataArrayDict[channelName],
                    x=allXScale[channelName],
                    name=channelName,
                    pen=pg.mkPen(color=color),
                )

            main_layout.addWidget(devices_name_label[k], 1 + 2 * k, 1, 1, 5)
            main_layout.addWidget(pw[k], 2   + 2 * k, 1, 1, 5)

        self.create_curve_selection()
        main_layout.addWidget(self.curve_selection_group, 2, 6, 3, 1)

        self.setCentralWidget(main_widget)

    def create_curve_selection(self):
        self.curve_selection_layout = QtWidgets.QVBoxLayout()
        self.curve_selection_group = QtWidgets.QGroupBox("Select Curves")
        self.curve_selection_group.setLayout(self.curve_selection_layout)

        for panel in range(PANEL_COUNT):
            for channelName in ALL_NAME_LIST[panel]:
                checkbox = QtWidgets.QCheckBox(channelName)
                checkbox.setChecked(True)
                checkbox.stateChanged.connect(
                    lambda state, name=channelName: self.toggle_curve(name, state)
                )
                self.curve_selection_layout.addWidget(checkbox)

    def toggle_curve(self, channel_name, state):
        curve = allCurveDict.get(channel_name)
        if curve:
            curve.setVisible(state == Qt.Checked)

    def closeEvent(self, event):
        result = QtWidgets.QMessageBox.question(
            self, "Exit", "Do you want to exit?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
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
    for i in range(PANEL_COUNT):
        for channelName in ALL_NAME_LIST[i]:
            allCurveDict[channelName].setData(
                allXScale[channelName], allDataArrayDict[channelName]
            )

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    gui = MainWidget()

    thread_serial_port = threading.Thread(target=serial_thread, daemon=True)
    thread_serial_port.start()

    gui.show()

    timer_plot = pg.QtCore.QTimer()
    timer_plot.timeout.connect(plot_data)
    timer_plot.start(25)

    for i in range(PANEL_COUNT):
        for channelName in ALL_NAME_LIST[i]:
            allProcess[channelName] = threading.Thread(
                target=consumer_ppg, args=(channelName,), daemon=True
            )
            allProcess[channelName].start()

    sys.exit(app.exec_())