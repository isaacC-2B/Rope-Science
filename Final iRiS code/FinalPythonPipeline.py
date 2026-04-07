import sys
import gi
import pyds
import csv
import os
import time
import threading
import asyncio
from datetime import datetime
from queue import Queue
from bleak import BleakClient, BleakScanner
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QLineEdit)
from PyQt5.QtCore import pyqtSignal, QObject, Qt

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

MOTOR_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
SENSOR_UUID = "11111111-E8F2-537E-4F6C-D104768A1214"
CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

RTSP_SOURCES = [ # custom ip address was set for the LAN of the raspberry pi and the jetson so they are on the same subnet mask
    "rtsp://192.168.0.1:8554/left",
    "rtsp://192.168.0.1:8554/center",
    "rtsp://192.168.0.1:8554/right"
]
CONFIG_FILE = "config.txt"
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Damage_Log.csv")
BAD_LABEL = "bad"
COOLDOWN_TIME = 1.5

log_queue = Queue()

def csv_logger_worker():
    while True:
        item = log_queue.get()
        if item is None: break
        rope_id, ts, source, event, details = item
        file_exists = os.path.isfile(CSV_FILE)
        try:
            with open(CSV_FILE, mode='a', newline='', buffering=1) as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Rope_ID", "Timestamp", "Source", "Event", "Details"])
                writer.writerow([rope_id, ts, source, event, details])
                f.flush()
                os.fsync(f.fileno())
        except: pass
        log_queue.task_done()

threading.Thread(target=csv_logger_worker, daemon=True).start()

class GuiSignals(QObject):
    log_signal = pyqtSignal(str)
    motor_status_signal = pyqtSignal(int)
    sensor_status_signal = pyqtSignal(int)
    sensor_alert_signal = pyqtSignal(int, float)

signals = GuiSignals()
global_last_log_time = 0
current_rope_name = "Unnamed Rope"

class DualBLEManager(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.loop = asyncio.new_event_loop()
        self.active = False
        self.motor_client = None
        self.sensor_client = None

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connection_manager())

    async def connection_manager(self):
        # 1 = not connected
        # 2 = connected
        while True:
            if self.active:
                if not self.motor_client or not self.motor_client.is_connected:
                    signals.motor_status_signal.emit(1)
                    self.motor_client = await self.connect_to(MOTOR_UUID)
                else: signals.motor_status_signal.emit(2)

                if not self.sensor_client or not self.sensor_client.is_connected:
                    signals.sensor_status_signal.emit(1)
                    self.sensor_client = await self.connect_to(SENSOR_UUID, notify=True)
                else: signals.sensor_status_signal.emit(2)
            await asyncio.sleep(2.0)

    async def connect_to(self, service_uuid, notify=False):
        target_name = "Motor" if service_uuid == MOTOR_UUID else "Sensor"
        try:
            devices = await BleakScanner.discover(timeout=4.0)
            for d in devices:
                if d.name and target_name.lower() in d.name.lower():
                    client = BleakClient(d.address)
                    await client.connect()
                    if notify: await client.start_notify(CHAR_UUID, self.on_sensor_data)
                    return client
        except: return None
        return None

    def on_sensor_data(self, sender, data):
        try:
            payload = data.decode('utf-8').strip()
            if ',' in payload:
                parts = payload.split(',')
                signals.sensor_alert_signal.emit(int(parts[0]), float(parts[1]))
            else:
                signals.sensor_alert_signal.emit(int(payload), 0.0)
        except: pass

    def send_motor_cmd(self, val):
        if self.motor_client and self.motor_client.is_connected:
            asyncio.run_coroutine_threadsafe(
                self.motor_client.write_gatt_char(CHAR_UUID, bytearray([val])), self.loop
            )

ble_manager = DualBLEManager()

class DeepStreamWorker(threading.Thread):
    def __init__(self):
        super().__init__()
        self.pipeline = None
        self.loop = GLib.MainLoop()
        self.daemon = True
        self.system_active = False

    def run(self):
        Gst.init(None)
        self.pipeline = Gst.Pipeline()

        muxer = Gst.ElementFactory.make("nvstreammux", "muxer")
        muxer.set_property("width", 1440); muxer.set_property("height", 640)
        muxer.set_property("batch-size", 3); muxer.set_property("live-source", 1)
        muxer.set_property("batched-push-timeout", 40000) # longer timeout to prevent from missing camera streams
        self.pipeline.add(muxer)

        for i, uri in enumerate(RTSP_SOURCES):
            src = Gst.ElementFactory.make("rtspsrc", f"src_{i}")
            src.set_property("location", uri); src.set_property("latency", 150)
            self.pipeline.add(src)
            src.connect("pad-added", self.cb_newpad, muxer, i)

        pgie = Gst.ElementFactory.make("nvinfer", "pgie")
        pgie.set_property("config-file-path", CONFIG_FILE)
        tiler = Gst.ElementFactory.make("nvmultistreamtiler", "tiler")
        tiler.set_property("rows", 1); tiler.set_property("columns", 3)
        tiler.set_property("width", 1440); tiler.set_property("height", 640)
        osd = Gst.ElementFactory.make("nvdsosd", "osd")
        sink = Gst.ElementFactory.make("nveglglessink", "sink")
        sink.set_property("sync", 0)

        for el in [pgie, tiler, osd, sink]: self.pipeline.add(el)
        muxer.link(pgie); pgie.link(tiler); tiler.link(osd); osd.link(sink)
        osd.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, self.osd_probe, 0)
        self.pipeline.set_state(Gst.State.PLAYING)
        self.loop.run()

    def cb_newpad(self, rtspsrc, pad, muxer, i):
        depay = Gst.ElementFactory.make("rtph264depay", f"depay_{i}")
        parse = Gst.ElementFactory.make("h264parse", f"parse_{i}")
        decoder = Gst.ElementFactory.make("nvv4l2decoder", f"dec_{i}")
        self.pipeline.add(depay); self.pipeline.add(parse); self.pipeline.add(decoder)
        depay.sync_state_with_parent(); parse.sync_state_with_parent(); decoder.sync_state_with_parent()
        pad.link(depay.get_static_pad("sink")); depay.link(parse); parse.link(decoder)
        decoder.get_static_pad("src").link(muxer.get_request_pad(f"sink_{i}"))

    def osd_probe(self, pad, info, u_data): # classification / labeling
        if not self.system_active: return Gst.PadProbeReturn.OK
        global global_last_log_time
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(info.get_buffer()))
        l_frame = batch_meta.frame_meta_list
        while l_frame:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            l_obj = frame_meta.obj_meta_list
            while l_obj:
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                label = obj_meta.obj_label.strip()

                if not label:
                    l_class = obj_meta.classifier_meta_list
                    if l_class:
                        class_meta = pyds.NvDsClassifierMeta.cast(l_class.data)
                        l_label = class_meta.label_info_list
                        if l_label:
                            label_info = pyds.NvDsLabelInfo.cast(l_label.data)
                            label = label_info.result_label.strip()

                if label.lower() == BAD_LABEL.lower():
                    curr = time.time()
                    if (curr - global_last_log_time) >= COOLDOWN_TIME:
                        global_last_log_time = curr
                        ts = datetime.now().strftime("%H:%M:%S")
                        log_queue.put((current_rope_name, ts, f"CAMERA", "VISUAL_ALERT", "Bad Label"))
                        signals.log_signal.emit(f"Visual detection: CAMERA @ {ts}")
                l_obj = l_obj.next
            l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

class ControlWindow(QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.initUI()
        signals.motor_status_signal.connect(self.update_motor_ui)
        signals.sensor_status_signal.connect(self.update_sensor_ui)
        signals.log_signal.connect(self.ai_lbl.setText)
        signals.sensor_alert_signal.connect(self.handle_sensor_code)

    def initUI(self):
        self.setWindowTitle('iRiS Control Pannel')
        self.setFixedSize(600, 500) # max to fit the 7-inch touchscreen is 800 by 500 and the initalize button will already be squished
        c = QWidget(); layout = QVBoxLayout(c)

        self.rope_input = QLineEdit(); self.rope_input.setPlaceholderText("Enter Rope ID...")
        self.rope_input.textChanged.connect(self.update_id)
        layout.addWidget(QLabel("<b>ROPE ID:</b>")); layout.addWidget(self.rope_input)

        self.m_status = QLabel("MOTOR: OFF"); self.s_status = QLabel("SENSOR: OFF")
        layout.addWidget(self.m_status); layout.addWidget(self.s_status)

        btn_init = QPushButton('INITIALIZE SYSTEM'); btn_init.clicked.connect(self.start_all); 
        btn_init.setStyleSheet("background-color: #27ae60; color: white; height: 40px;"); layout.addWidget(btn_init)

        btn_run = QPushButton('RUN MOTORS'); btn_run.clicked.connect(lambda: ble_manager.send_motor_cmd(1))
        btn_run.setStyleSheet("background-color: #27ae60; color: white; height: 40px;"); layout.addWidget(btn_run)

        btn_stop = QPushButton('STOP MOTORS'); btn_stop.clicked.connect(lambda: ble_manager.send_motor_cmd(0))
        btn_stop.setStyleSheet("background-color: #f39c12; color: white; height: 40px;"); layout.addWidget(btn_stop)

        btn_halt = QPushButton('STOP ALL')
        btn_halt.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; height: 40px;")
        btn_halt.clicked.connect(self.stop_all); layout.addWidget(btn_halt)

        self.ai_lbl = QLabel("Cameras on standby"); layout.addWidget(QLabel("<b>Visual:</b>")); layout.addWidget(self.ai_lbl)
        self.sensor_lbl = QLabel("Awaiting Rope"); layout.addWidget(QLabel("<b>Tactile:</b>")); layout.addWidget(self.sensor_lbl)

        self.setCentralWidget(c)

    def update_id(self, t):
        global current_rope_name
        current_rope_name = t if t.strip() else "Unnamed_Rope"

    def handle_sensor_code(self, code, adc_val):
        ts = datetime.now().strftime("%H:%M:%S")

        scenarios = {
            0: ("INSERT ROPE","#7f8c8d"),
            4: ("DETECTED", "#f39c12"),
            6: ("MONITORING", "#2ecc71"),
            5: ("COMPLETE", "#3498db")
        }
        msg, color = scenarios.get(code, (f"CODE {code}", "#7f8c8d"))

        if code == 3:
            self.sensor_lbl.setText(f"Compressibility spike!: {adc_val:.1f} !!!")
            self.sensor_lbl.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 18px;")
            log_queue.put((current_rope_name, ts, "Tactile", "COMPRESSIBILITY SPIKE", f"ADC: {adc_val:.2f}"))
        else:
            self.sensor_lbl.setText(msg)
            self.sensor_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 18px;")
            if code == 5:
                log_queue.put((current_rope_name, ts, "Tactile", "EVENT", "Run Finished"))

    def update_motor_ui(self, s):
        t, c = (["OFF", "SCANNING", "CONNECTED"][s], ["gray", "orange", "green"][s])
        self.m_status.setText(f"MOTOR: {t}"); self.m_status.setStyleSheet(f"color: {c}; font-weight: bold;")

    def update_sensor_ui(self, s):
        t, c = (["OFF", "SCANNING", "CONNECTED"][s], ["gray", "orange", "green"][s])
        self.s_status.setText(f"SENSOR: {t}"); self.s_status.setStyleSheet(f"color: {c}; font-weight: bold;")

    def start_all(self):
        ble_manager.active = True
        self.worker.system_active = True
        self.ai_lbl.setText("Monitoring Active")

    def stop_all(self):
        self.worker.system_active = False
        ble_manager.send_motor_cmd(0)
        ble_manager.active = False
        self.ai_lbl.setText("Muted.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ds = DeepStreamWorker()
    win = ControlWindow(ds)
    win.show()
    ble_manager.start(); ds.start()
    sys.exit(app.exec_())