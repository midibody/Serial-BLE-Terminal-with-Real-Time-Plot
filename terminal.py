import sys
import asyncio
import threading
from typing import Dict, List, Tuple
from datetime import datetime

from BLEcom import BLEComm

from PySide6.QtCore import Slot, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QScrollArea,
)
import pyqtgraph as pg

from PySide6.QtWidgets import QSplitter
from PySide6.QtCore import Qt


cMaxPlotValues = 50  # max points kept per signal (oscilloscope-like window)


# communication backends
class SerialComm:
    def __init__(self, port: str, baudrate: int = 9600):
        import serial
        self.ser = serial.Serial(port, baudrate, timeout=0.1)

    def write(self, data: bytes):
        self.ser.write(data)

    def read(self) -> bytes:
        return self.ser.read(1024)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    #***************
    @staticmethod
    def refresh_com_ports():
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        result = []
        for p in ports:
            result.append((p.device, p.description, p.hwid))
        return result

#**********************************
class GraphicTerminal(QWidget):
    ble_devices_found = Signal(list)  # list[tuple(name, address, rssi)]
    ble_scan_failed = Signal(str)

    def __init__(self, mode: str = "COM"):
        super().__init__()
        self.setWindowTitle("Serial/BLE Terminal & Real Time Plot") 
        self.mode = mode
        self.comm = None

        self.plot_data: Dict[str, List[float]] = {}
        self.plot_curves: Dict[str, pg.PlotDataItem] = {}
        self.kv_widgets: Dict[str, QLineEdit] = {}


        self._rx_buffer = ""
        self.plot_running = True

        # recording
        self.recording = False
        self._log_fh = None

        # BLE scan state
        self._ble_scan_thread = None
        self._ble_scanning = False

        self.color_index = 0
        self.color_palette = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (255, 0, 255),
            (0, 255, 255),
            (255, 128, 0),
            (128, 0, 255),
        ]

        self.ble_devices_found.connect(self._on_ble_devices_found)
        self.ble_scan_failed.connect(self._on_ble_scan_failed)

        self._build_ui()
        self._setup_timer()
        self.on_mode_change(self.mode_combo.currentText())

        # If started in BLE mode, populate immediately
        if self.mode == "BLE":
            self._start_ble_scan()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Mode:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["COM", "BLE"])
        self.mode_combo.setCurrentText(self.mode)
        self.mode_combo.currentTextChanged.connect(self.on_mode_change)
        self.mode_combo.setFixedWidth(80)
        ctrl_layout.addWidget(self.mode_combo)

        ctrl_layout.addWidget(QLabel("Device:"))

        # QComboBox editable: COM = saisie libre, BLE = liste devices
        self.addr_input = QComboBox()
        self.addr_input.setEditable(True)
        self.addr_input.setFixedWidth(400)
        ctrl_layout.addWidget(self.addr_input)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect)
        self.connect_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        self.disconnect_btn.setFixedWidth(110)
        self.disconnect_btn.setEnabled(False)
        ctrl_layout.addWidget(self.disconnect_btn)

        self.screenshot_btn = QPushButton("Screenshot")
        self.screenshot_btn.clicked.connect(self.on_screenshot)
        self.screenshot_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.screenshot_btn)

        self.record_btn = QPushButton("Record term.")
        self.record_btn.clicked.connect(self.on_toggle_record)
        self.record_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton("Clear term.")
        self.clear_btn.clicked.connect(self.on_clear_terminal)
        self.clear_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.clear_btn)

        self.plot_btn = QPushButton("Stop spot")
        self.plot_btn.clicked.connect(self.on_toggle_plot)
        self.plot_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.plot_btn)

        self.help_btn = QPushButton("Help/About")
        self.help_btn.clicked.connect(self.on_help)
        self.help_btn.setFixedWidth(110)
        ctrl_layout.addWidget(self.help_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)


        splitter = QSplitter(Qt.Horizontal)

        # ----- Terminal (gauche) -----
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setMaximumBlockCount(1000)
        splitter.addWidget(self.terminal)

        # ----- Bloc graphique (droite) -----
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Zone scrollable pour afficher des paires clé/valeur
        self.kv_container = QWidget()
        self.kv_layout = QVBoxLayout(self.kv_container)
        self.kv_layout.setContentsMargins(0, 0, 0, 0)
        self.kv_layout.setSpacing(6)
        self.kv_layout.addStretch(1)  # stretch final (on insère avant)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.kv_container)
        right_layout.addWidget(scroll)

        splitter.addWidget(right_panel)

        # Optionnel : taille initiale 50/50
        splitter.setSizes([500, 500])

        #layout.addWidget(splitter)
        layout.addWidget(splitter, stretch=3)

        # Plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.addLegend()
        #layout.addWidget(self.plot_widget)
        layout.addWidget(self.plot_widget, stretch=1)

        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.returnPressed.connect(self.on_send)
        input_layout.addWidget(self.input_line)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.on_send)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        self._apply_mode_ui()

    def _setup_timer(self):
        from PySide6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(50)

    def _apply_mode_ui(self):
        if self.mode == "COM":
            self.addr_input.setEditable(True)
        else:
            self.addr_input.setEditable(False)

    @Slot()
    def on_mode_change(self, text: str):
        self.mode = text
        self._apply_mode_ui()

        if self.mode == "BLE":
            self._start_ble_scan()
        else:
            self.scanComPorts()

    #*************************
    def scanComPorts(self):
        ports = SerialComm.refresh_com_ports()
        self.addr_input.clear()

        if not ports:
            self.addr_input.addItem("No COM ports found", None)
        else:
            for device, desc, hwid in ports:
                #display = f"{device} – {desc}"
                display = f"{device}"

                self.addr_input.addItem(display, device)        

    #*************************
    def _start_ble_scan(self):
        if self._ble_scanning:
            return

        self._ble_scanning = True
        self.addr_input.clear()
        self.addr_input.addItem("Scanning BLE devices...", None)
        self.connect_btn.setEnabled(True)
        self.addr_input.setEnabled(False)

        def _scan():
            try:
                from bleak import BleakScanner

                async def _discover():
                    # return_adv=True -> dict[address] = (BLEDevice, AdvertisementData)
                    return await BleakScanner.discover(timeout=3.0, return_adv=True)

                devices = asyncio.run(_discover())
                out: List[Tuple[str, str, int]] = []

                for _addr, (device, adv) in devices.items():
                    #name = (device.name or "").strip() or "Unknown"
                    # first try adv.local_name, then device.name, else "Unknown":
                    adv_name = (getattr(adv, "local_name", None) or "").strip()
                    dev_name = (getattr(device, "name", None) or "").strip()
                    name = adv_name or dev_name or "Unknown"
                    name_src = "ADV" if adv_name else ("DEV" if dev_name else "NONE")
                    #print(f"Found BLE device. adv_name= {adv_name} dev_name={dev_name}")

                    addr = (getattr(device, "address", "") or "").strip()
                    rssi = getattr(adv, "rssi", None)
                    if addr:
                        out.append((name, addr, int(rssi) if rssi is not None else -999))

                # tri par RSSI (plus fort en premier), puis nom/adresse
                out.sort(key=lambda t: (t[2], t[0].lower(), t[1].lower()), reverse=True)

                self.ble_devices_found.emit(out)
            except Exception as e:
                self.ble_scan_failed.emit(str(e))

        self._ble_scan_thread = threading.Thread(target=_scan, daemon=True)
        self._ble_scan_thread.start()

    @Slot(list)
    def _on_ble_devices_found(self, devices: list):
        self._ble_scanning = False
        self.addr_input.setEnabled(True)
        self.addr_input.clear()

        if not devices:
            self.addr_input.addItem("No BLE device found", None)
            return

        for name, addr, rssi in devices:
            self.addr_input.addItem(f"{name} ({addr})  RSSI: {rssi} dBm", addr)
            #self.addr_input.addItem(f"{name} [{name_src}] ({addr})  RSSI: {rssi} dBm", addr)

        self.addr_input.setCurrentIndex(0)

    @Slot(str)
    def _on_ble_scan_failed(self, err: str):
        self._ble_scanning = False
        self.addr_input.setEnabled(True)
        self.addr_input.clear()
        self.addr_input.addItem("BLE scan failed", None)
        self.terminal.appendPlainText(f"BLE scan error: {err}")

    @Slot()
    def on_toggle_plot(self):
        self.plot_running = not self.plot_running
        self.plot_btn.setText("Stop plot." if self.plot_running else "Run plot.")

    @Slot()
    def on_screenshot(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"oscillo_{timestamp}.jpg"
        pixmap = self.plot_widget.grab()
        pixmap.save(filename, "JPG")
        self.terminal.appendPlainText(f"Screenshot saved: {filename}")

    def on_help(self):

        help_text = (
            "GraphicTerminal Help\n\n"
            "This application allows you to connect to a serial COM port or a BLE device and display incoming data in a terminal-like interface.\n\n"
            "Key features:\n"
            "- Recieves and sends data over COM or BLE\n"
            "- Display incoming data with normalized line endings\n"
            "- Parse and display key-value pairs in a side panel\n"
            "- Plot numeric data in real-time (oscilloscope-like)\n"
            "- Record terminal output to a log file\n"
            "- Take screenshots of the plot area\n\n"
            "Usage:\n"
            "1. Select mode (COM or BLE)\n"
            "2. For COM: select or enter the port name (e.g., COM3)\n"
            "   For BLE: select a device from the list (scanning will be done automatically)\n"
            "3. Click 'Connect' to start receiving data\n"
            "4. Use 'Stop plot.' to pause/resume real-time plotting\n"
            "5. Use 'Record term.' to start/stop recording terminal output to 'terminal.log'\n"
            "6. Use 'Clear term.' to clear the terminal display\n"
            "7. Use 'Screenshot' to save an image of the current plot area\n\n"
            "Special Data format - Key values displayed in the right panel:\n"
            "-------------------------------------------------------------------\n"
            "- Lines recieved in serial or BLE starting with '^' are treated as key-value frames; e.g: '^Temp:25\\tHum:60\\n'\n"
            "  They are parsed and displayed in the right panel with keys and values\n"
            "  Syntax is similar to Arduino Serial Plotter, with key:value frames, separated by a '\\t' and terminated by a '\\n'. But with a '^' prefix to distinguish them from normal lines\n"
            "  The first time a key is seen, a new entry is dynamically added in the right panel\n\n"
            "Special Data format - values plotted in the plot panel:\n"
            "------------------------------------------------------------\n"
            "- Lines starting with '~' are treated as plot data and NOT displayed in the terminal; e.g: '~Signal1:10\\tSignal2:20\\n'\n"
            "  Each 'key:value' pair is parsed, and the value is plotted in real-time on the graph with the key as the label\n"
             "  Syntax is similar to Arduino Serial Plotter, with key:value frames, separated by a '\\t' and terminated by a '\\n'. But with a '~' prefix to distinguish them from normal lines\n"
            "  To customoze the plotting area, right click the mouse to access the menu (auto-range, grid, etc.)\n"
            "  To zoom the plot, click and drag with the left mouse button. To pan, click and drag with the right mouse button.\n\n"
            "Source code available on GitHub: XXX\n"
            ""
        )
        self.terminal.appendPlainText(help_text)

    @Slot()
    def on_clear_terminal(self):
        self.terminal.clear()

    @Slot()
    def on_toggle_record(self):
        self.recording = not self.recording

        if self.recording:
            try:
                self._log_fh = open("terminal.log", "a", encoding="utf-8", buffering=1)
                self.record_btn.setText("STOP REC")
                self.terminal.appendPlainText("Recording enabled: terminal.log")
            except Exception as e:
                self.recording = False
                self._log_fh = None
                self.record_btn.setText("Record Terminal")
                self.terminal.appendPlainText(f"Recording error: {e}")
        else:
            try:
                if self._log_fh:
                    self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None
            self.record_btn.setText("Record Terminal")
            self.terminal.appendPlainText("Recording disabled")

    def _get_selected_addr_or_port(self) -> str:
        if self.mode == "BLE":
            addr = self.addr_input.currentData()
            if isinstance(addr, str) and addr.strip():
                return addr.strip()
            txt = (self.addr_input.currentText() or "").strip()
            if "(" in txt and ")" in txt:
                inside = txt[txt.rfind("(") + 1 : txt.rfind(")")].strip()
                return inside
            return txt
        else:
            data = self.addr_input.currentData()
            if isinstance(data, str) and data.strip():
                return data.strip()
            return (self.addr_input.currentText() or "").strip()

    @Slot()
    def on_connect(self):
        if self.comm is not None:
            return

        addr = self._get_selected_addr_or_port()
        if not addr:
            return

        try:
            if self.mode == "COM":
                self.comm = SerialComm(addr)
            else:
                self.comm = BLEComm(addr)
        except Exception as e:
            self.comm = None
            self.terminal.appendPlainText(f"Connect error: {e}")
            return

        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.terminal.appendPlainText(f"Connected to {addr} ({self.mode})\n")

    @Slot()
    def on_disconnect(self):
        if self.comm is None:
            return

        try:
            close_fn = getattr(self.comm, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

        self.comm = None
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.terminal.appendPlainText("Disconnected")

    @Slot()
    def on_send(self):
        msg = self.input_line.text()
        if self.comm and msg:
            data = (msg + "\n").encode()
            try:
                self.comm.write(data)
            except Exception:
                pass
            self.input_line.clear()


    def _terminal_append_line(self, line: str):
        # Affiche une ligne normalisée (sans inclure les trames '^')
        self.terminal.moveCursor(QTextCursor.End)
        self.terminal.insertPlainText(line + "\n")

        if self.recording and self._log_fh:
            try:
                self._log_fh.write(line + "\n")
            except Exception:
                pass

    def _parse_kv_frame(self, payload: str):
        # payload exemple: "Voltage:10\tCourant:20"
        payload = payload.strip()
        if not payload:
            return

        parts = payload.split("\t")
        for part in parts:
            part = part.strip()
            if not part or ":" not in part:
                continue

            key, val = part.split(":", 1)
            key = key.strip()
            val = val.strip()
            if not key:
                continue

            w = self.kv_widgets.get(key)
            if w is None:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)

                lab = QLabel(key)
                edit = QLineEdit()
                edit.setReadOnly(True)

                row_layout.addWidget(lab, stretch=1)
                row_layout.addWidget(edit, stretch=2)

                insert_index = max(0, self.kv_layout.count() - 1)
                self.kv_layout.insertWidget(insert_index, row)

                self.kv_widgets[key] = edit
                w = edit

            w.setText(val)

    def poll(self):
        if not self.comm:
            return

        try:
            raw = self.comm.read()
        except Exception:
            return
        if not raw:
            return

        text = raw.decode("utf-8", errors="ignore")

        # normalise les fins de ligne
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        self._rx_buffer += text

        # traite uniquement les lignes complètes
        while True:
            idx = self._rx_buffer.find("\n")
            if idx < 0:
                break

            line = self._rx_buffer[:idx]
            self._rx_buffer = self._rx_buffer[idx + 1 :]

            if not line:
                continue

            # trame Key Value: starts with '^'
            if line.startswith("^"):
                self._parse_kv_frame(line[1:])
                #continue

            if line.startswith("~"):
            
                self._parse_plot_line(line[1:])  # on enlève le '~'
            else:
                self._terminal_append_line(line)

            #self._terminal_append_line(line)
            #self._parse_plot_line(line)

    def _parse_plot_line(self, line: str):
        if not self.plot_running:
            return

        line = line.strip()
        if not line:
            return

        if line.startswith("^"):
            return

        for part in line.split("\t"):
            part = part.strip()
            if ":" not in part:
                continue

            name, val = part.split(":", 1)
            name = name.strip().strip("\r")
            if not name:
                continue

            try:
                f = float(val.strip().strip("\r"))
            except ValueError:
                continue

            buf = self.plot_data.setdefault(name, [])
            buf.append(f)

            if len(buf) > cMaxPlotValues:
                del buf[: len(buf) - cMaxPlotValues]

            self._update_plot(name)

    def _update_plot(self, name: str):
        data = self.plot_data.get(name, [])
        curve = self.plot_curves.get(name)

        if curve is None:
            color = self.color_palette[self.color_index % len(self.color_palette)]
            self.color_index += 1
            pen = pg.mkPen(color=color, width=2)
            curve = self.plot_widget.plot([], pen=pen, name=name)
            self.plot_curves[name] = curve

        curve.setData(data)
        #x = list(range(len(data)))  # ou tes timestamps si tu en as
        #curve.setData(x, data, stepMode="left")