"""
Subscribes to factory/+/sensors, validates each message, stamps receipt time,
rejects malformed / stale messages, and caches the latest reading per machine.
"""
import threading

import paho.mqtt.client as mqtt

from layers.layer1.common.logger import get_logger
from layers.layer1.common.utils import is_stale, now_iso, safe_json_loads, validate_sensor_record
from layers.layer1.config import config

log = get_logger("mqtt_consumer")


class MQTTSensorConsumer:
    def __init__(self, host=None, port=None, on_valid_record=None):
        self.host = host or config.MQTT_BROKER_HOST
        self.port = port or config.MQTT_BROKER_PORT
        self.on_valid_record = on_valid_record  # callback(record)
        self.client = mqtt.Client(client_id=config.MQTT_CLIENT_ID_CONSUMER, protocol=mqtt.MQTTv311)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._lock = threading.Lock()
        self.latest_readings = {}  # machine_id -> record
        self.stats = {"received": 0, "accepted": 0, "rejected": 0}

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info(f"Consumer connected to MQTT broker {self.host}:{self.port}")
            client.subscribe(config.SENSOR_TOPIC_WILDCARD, qos=0)
            log.info(f"Subscribed to {config.SENSOR_TOPIC_WILDCARD}")
        else:
            log.error(f"Consumer failed to connect, rc={rc}")

    def _on_message(self, client, userdata, msg):
        self.stats["received"] += 1
        record, err = safe_json_loads(msg.payload.decode("utf-8"))
        if err:
            self.stats["rejected"] += 1
            log.error(f"Rejected malformed message on {msg.topic}: {err}")
            return

        ok, reason = validate_sensor_record(record)
        if not ok:
            self.stats["rejected"] += 1
            log.error(f"Rejected invalid schema on {msg.topic}: {reason}")
            return

        if is_stale(record["timestamp"], config.STALE_MESSAGE_THRESHOLD_SEC):
            self.stats["rejected"] += 1
            log.warning(f"Rejected stale message from {record['machine_id']} (timestamp={record['timestamp']})")
            return

        record["_received_at"] = now_iso()
        self.stats["accepted"] += 1

        with self._lock:
            self.latest_readings[record["machine_id"]] = record

        if self.on_valid_record:
            self.on_valid_record(record)

    def get_latest(self, machine_id=None):
        with self._lock:
            if machine_id:
                return self.latest_readings.get(machine_id)
            return dict(self.latest_readings)

    def connect(self):
        try:
            self.client.connect(self.host, self.port, keepalive=config.MQTT_KEEPALIVE)
            self.client.loop_start()
        except Exception as e:
            log.error(f"Could not connect to MQTT broker at {self.host}:{self.port} ({e})")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
