"""
Publishes sensor simulator records to MQTT, one topic per machine:
factory/M1/sensors ... factory/M5/sensors
"""
import json

import paho.mqtt.client as mqtt

from layers.layer1.common.logger import get_logger
from layers.layer1.config import config

log = get_logger("mqtt_publisher")


class MQTTSensorPublisher:
    def __init__(self, host=None, port=None):
        self.host = host or config.MQTT_BROKER_HOST
        self.port = port or config.MQTT_BROKER_PORT
        self.client = mqtt.Client(client_id=config.MQTT_CLIENT_ID_PUBLISHER, protocol=mqtt.MQTTv311)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._connected = False

    def _on_connect(self, client, userdata, flags, rc):
        self._connected = rc == 0
        if self._connected:
            log.info(f"Publisher connected to MQTT broker {self.host}:{self.port}")
        else:
            log.error(f"Publisher failed to connect, rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        log.warning("Publisher disconnected from MQTT broker")

    def connect(self):
        try:
            self.client.connect(self.host, self.port, keepalive=config.MQTT_KEEPALIVE)
            self.client.loop_start()
        except Exception as e:
            log.error(f"Could not connect to MQTT broker at {self.host}:{self.port} ({e}). "
                       f"Sensor records will still be generated but not delivered.")

    def publish(self, record: dict):
        topic = config.sensor_topic(record["machine_id"])
        payload = json.dumps(record)
        result = self.client.publish(topic, payload, qos=0)
        if result.rc != 0:
            log.error(f"Publish failed on {topic}, rc={result.rc}")
        return result

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
