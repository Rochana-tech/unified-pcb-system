import json
import os
import queue
import paho.mqtt.client as mqtt
from .contracts import Telemetry

class MQTTBridge:
    """Network callback only queues validated records; runtime owns state mutation."""
    def __init__(self,runtime):
        self.runtime=runtime
        self.pending=queue.Queue(maxsize=1000)
        self.errors=queue.Queue(maxsize=100)
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect=self.on_connect
        self.client.on_disconnect=self.on_disconnect
        self.client.on_message=self.on_message
        if os.getenv('MQTT_USERNAME'):
            self.client.username_pw_set(os.environ['MQTT_USERNAME'],os.getenv('MQTT_PASSWORD'))
        if os.getenv('MQTT_TLS')=='1':
            self.client.tls_set()

    def on_connect(self,client,userdata,flags,reason_code,properties):
        self.runtime.mqtt_status='connected' if not reason_code.is_failure else 'connection_failed'
        if not reason_code.is_failure:
            client.subscribe('factory/+/telemetry',qos=1)

    def on_disconnect(self,client,userdata,flags,reason_code,properties):
        self.runtime.mqtt_status='disconnected'

    def on_message(self,client,userdata,msg):
        try:
            if len(msg.payload)>32768:
                raise ValueError('MQTT payload exceeds 32KB')
            record=Telemetry.model_validate_json(msg.payload)
            if msg.topic != 'factory/'+record.machine_id+'/telemetry':
                raise ValueError('Topic and payload machine IDs differ')
            self.pending.put_nowait(record)
        except (ValueError,queue.Full) as exc:
            try:
                self.errors.put_nowait(str(exc)[:400])
            except queue.Full:
                pass

    def start(self):
        self.runtime.mqtt_status='connecting'
        self.client.connect_async(os.getenv('MQTT_HOST','localhost'),int(os.getenv('MQTT_PORT','1883')),60)
        self.client.loop_start()

    def drain(self):
        for _ in range(100):
            try:
                item=self.pending.get_nowait()
            except queue.Empty:
                break
            try:
                self.runtime.ingest(item)
            except ValueError as exc:
                self.runtime.store.add('mqtt_record_rejected',{'reason':str(exc)})
        while not self.errors.empty():
            self.runtime.store.add('mqtt_record_rejected',{'reason':self.errors.get_nowait()})

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

