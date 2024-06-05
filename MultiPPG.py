import ctypes
import inspect
import sys
import threading
import time
from queue import Queue

import numpy as np
import pyqtgraph as pg
import serial
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from SerialPortDataParse import parse_package_data
from color import COLORS
from constants import ALL_NAME_LIST, PANEL_NAME_LIST, ALL_NAME_LIST_AS_ONE

# Constants
DISPLAY_SECONDS = 10
PORT = "COM5"
BAUDRATE = 250000
PACKAGE_SIZE = 242

class SerialDataHandler:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = serial.Serial(self.port, self.baudrate)
        self.data_bytes = bytearray()

    def read_data(self):
        count = self.ser.inWaiting()
        if count:
            rec_str = self.ser.read(count)
            self.data_bytes += rec_str
            return self.process_data()
        return None

    def process_data(self):
        data_len = len(self.data_bytes)
        k = 0
        raw_data_list = []
        while k + PACKAGE_SIZE + 2 < data_len:
            if (
                self.data_bytes[k] == 0x16
                and self.data_bytes[k + 1] == 0x00
                and self.data_bytes[k + PACKAGE_SIZE] == 0x16
                and self.data_bytes[k + PACKAGE_SIZE + 1] == 0x00
            ):
                raw_data = parse_package_data(
                    self.data_bytes[k + 2 : k + PACKAGE_SIZE]
                )
                raw_data_list.append(raw_data)
                k += PACKAGE_SIZE
            else:
                k += 1
        self.data_bytes = self.data_bytes[k:]
        return raw_data_list

class DataPlotter:
    def __init__(self, panel_name_list, all_name_list, all_name_list_as_one, colors):
        self.panel_name_list = panel_name_list
        self.all_name_list = all_name_list
        self.all_name_list_as_one = all_name_list_as_one
        self.colors = colors
        self.panel_count = len(panel_name_list)
        self.panel_sample_frequency = [250, 250]
        self.panel_data_length = np.multiply(self.panel_sample_frequency, DISPLAY_SECONDS)

        self.init_dicts()

    def init_dicts(self):
        self.all_queue_dict = {name: Queue(maxsize=200) for name in self.all_name_list_as_one}
        self.all_data_array_dict = {name: np.zeros(length, dtype=float) for panel, length in zip(self.all_name_list, self.panel_data_length) for name in panel}
        self.all_index_dict = {name: 0 for name in self.all_name_list_as_one}
        self.all_curve_dict = {}
        self.all_x_scale = {}
        self.all_data_length = {name: length for panel, length in zip(self.all_name_list, self.panel_data_length) for name in panel}

    def setup_plot_widgets(self):
        self.plot_widgets = []
        for k in range(self.panel_count):
            pw = pg.PlotWidget(enableAutoRange=True)
            pw.setLabel(axis="bottom", text="Time / s")
            pw.setLabel(axis="left", text="Amplitude")
            pw.setBackground("w")
            pw.addLegend()
            self.plot_widgets.append(pw)

            channel_name_list = self.all_name_list[k]
            for channel_name, color in zip(channel_name_list, self.colors):
                self.all_x_scale[channel_name] = [
                    x * DISPLAY_SECONDS / self.all_data_length[channel_name] for x in range(self.all_data_length[channel_name])
                ]
                self.all_curve_dict[channel_name] = pw.plot(
                    self.all_data_array_dict[channel_name],
                    x=self.all_x_scale[channel_name],
                    name=channel_name,
                    pen=pg.mkPen(color=color),
                )
        return self.plot_widgets

    def update_plot_data(self):
        for channel_name in self.all_curve_dict:
            self.all_curve_dict[channel_name].setData(
                self.all_x_scale[channel_name], self.all_data_array_dict[channel_name]
                )

    def update_data_arrays(self, raw_data):
        for channel_name in self.all_name_list_as_one:
            values = raw_data.get(channel_name, [])
            if not isinstance(values, list):
                values = [values]
            for value in values:
                index_on_time = self.all_index_dict[channel_name]
                if index_on_time < self.all_data_length[channel_name]:
                    self.all_data_array_dict[channel_name][index_on_time] = value
                    self.all_index_dict[channel_name] = index_on_time + 1
                else:
                    self.all_data_array_dict[channel_name][:-1] = self.all_data_array_dict[channel_name][1:]
                    self.all_data_array_dict[channel_name][-1] = value

class MainWidget(QtWidgets.QMainWindow):
    def __init__(self, data_handler, data_plotter):
        super().__init__()
        self.data_handler = data_handler
        self.data_plotter = data_plotter

        self.setWindowTitle("PPG")
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QGridLayout()
        main_widget.setLayout(main_layout)
        main_widget.setStyleSheet("QWidget{background:white;}")

        self.plot_widgets = self.data_plotter.setup_plot_widgets()
        self.devices_name_label = []

        for k, pw in enumerate(self.plot_widgets):
            label = QtWidgets.QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #000000; font-size:24px; font-weight:bold")
            label.setText(self.data_plotter.panel_name_list[k])
            self.devices_name_label.append(label)

            main_layout.addWidget(label, 1 + 2 * k, 1, 1, 5)
            main_layout.addWidget(pw, 2 + 2 * k, 1, 1, 5)

        self.create_curve_selection()
        main_layout.addWidget(self.curve_selection_group, 2, 6, 3, 1)

        self.setCentralWidget(main_widget)

    def create_curve_selection(self):
        self.curve_selection_layout = QtWidgets.QVBoxLayout()
        self.curve_selection_group = QtWidgets.QGroupBox("Select Curves")
        self.curve_selection_group.setLayout(self.curve_selection_layout)

        for channel_name in self.data_plotter.all_name_list_as_one:
            checkbox = QtWidgets.QCheckBox(channel_name)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(
                lambda state, name=channel_name: self.toggle_curve(name, state)
            )
            self.curve_selection_layout.addWidget(checkbox)

    def toggle_curve(self, channel_name, state):
        curve = self.data_plotter.all_curve_dict.get(channel_name)
        if curve:
            curve.setVisible(state == Qt.Checked)

    def closeEvent(self, event):
        result = QtWidgets.QMessageBox.question(
            self, "Exit", "Do you want to exit?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if result == QtWidgets.QMessageBox.Yes:
            stop_thread(self.data_thread)
            print("Close successfully")
            event.accept()
        else:
            event.ignore()

    def start_threads(self):
        self.data_thread = threading.Thread(target=self.serial_thread, daemon=True)
        self.data_thread.start()

        self.plot_timer = pg.QtCore.QTimer()
        self.plot_timer.timeout.connect(self.data_plotter.update_plot_data)
        self.plot_timer.start(25)

        self.consumer_threads = []
        for channel_name in self.data_plotter.all_name_list_as_one:
            thread = threading.Thread(
                target=self.consumer_ppg, args=(channel_name,), daemon=True
            )
            thread.start()
            self.consumer_threads.append(thread)

    def serial_thread(self):
        while True:
            raw_data_list = self.data_handler.read_data()
            if raw_data_list:
                for raw_data in raw_data_list:
                    self.data_plotter.update_data_arrays(raw_data)

    def consumer_ppg(self, channel_name):
        while True:
            raw_data = self.data_plotter.all_queue_dict[channel_name].get()
            index_on_time = self.data_plotter.all_index_dict[channel_name]
            if index_on_time < self.data_plotter.all_data_length[channel_name]:
                self.data_plotter.all_data_array_dict[channel_name][index_on_time] = raw_data
                self.data_plotter.all_index_dict[channel_name] = index_on_time + 1
            else:
                self.data_plotter.all_data_array_dict[channel_name][:-1] = self.data_plotter.all_data_array_dict[channel_name][1:]
                self.data_plotter.all_data_array_dict[channel_name][-1] = raw_data

def _async_raise(tid, exctype):
    """Raises an exception in the thread with id tid."""
    if not inspect.isclass(exctype):
        raise TypeError("Only types can be raised (not instances)")
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("Invalid thread id")
    elif res != 1:
        # If it returns a number greater than one, we need to reset the exception state
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), 0)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def stop_thread(thread):
    _async_raise(thread.ident, SystemExit)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    data_handler = SerialDataHandler(PORT, BAUDRATE)
    data_plotter = DataPlotter(panel_name_list=PANEL_NAME_LIST, all_name_list=ALL_NAME_LIST, all_name_list_as_one=ALL_NAME_LIST_AS_ONE,colors=COLORS)
    gui = MainWidget(data_handler, data_plotter)

    gui.start_threads()
    gui.show()

    sys.exit(app.exec_())