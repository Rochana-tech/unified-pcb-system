"""
Layer 1 - Data Acquisition & Real-Time Communication
Orchestrates both independent streams:

  Stream A (sensors, dummy)     -> SensorSimulator -> MQTTSensorPublisher
                                    -> MQTT broker -> MQTTSensorConsumer
                                    (validate/reject stale+malformed) -> StateManager

  Stream B (machine/production, -> DummyMachineDataProvider (behind the
  dummy)                           MachineDataProvider interface) -> StateManager

Both streams stay logically separate; StateManager just correlates them by
machine_id/timestamp for whoever queries it (Layer 2/3, or the API below).

Run:  python main.py
API:  http://localhost:8000/docs
"""
import threading
import time

import uvicorn

from layers.layer1.api import app as api_module
from layers.layer1.common.logger import get_logger
from layers.layer1.config import config
from layers.layer1.machine_stream.dummy_machine_provider import DummyMachineDataProvider
from layers.layer1.machine_stream.state_manager import StateManager
from layers.layer1.sensor_stream.mqtt_consumer import MQTTSensorConsumer
from layers.layer1.sensor_stream.mqtt_publisher import MQTTSensorPublisher
from layers.layer1.sensor_stream.sensor_simulator import SensorSimulator

log = get_logger("main")


def main():
    state_manager = StateManager(config.MACHINES)

    # ---- Stream A: sensors (dummy generator -> MQTT -> validated consumer) ----
    publisher = MQTTSensorPublisher()
    publisher.connect()

    consumer = MQTTSensorConsumer(on_valid_record=state_manager.update_sensor)
    consumer.connect()

    simulator = SensorSimulator(on_record=publisher.publish)

    # ---- Stream B: machine/production data (dummy provider behind interface) ----
    machine_provider = DummyMachineDataProvider()
    machine_provider.subscribe(state_manager.update_production)

    api_module.wire(consumer, machine_provider, state_manager)

    time.sleep(1.0)  # let MQTT connections establish before publishing starts
    simulator.start()
    machine_provider.start()

    log.info("Layer 1 running: Stream A over MQTT, Stream B via provider/API.")
    log.info(f"API docs available at http://{config.API_HOST}:{config.API_PORT}/docs")

    server_thread = threading.Thread(
        target=lambda: uvicorn.run(
            api_module.app, host=config.API_HOST, port=config.API_PORT, log_level="warning"
        ),
        daemon=True,
    )
    server_thread.start()

    try:
        while True:
            time.sleep(5)
            log.info(f"Sensor consumer stats: {consumer.stats}")
    except KeyboardInterrupt:
        log.info("Shutting down...")
        simulator.stop()
        machine_provider.stop()
        publisher.disconnect()
        consumer.disconnect()


if __name__ == "__main__":
    main()
