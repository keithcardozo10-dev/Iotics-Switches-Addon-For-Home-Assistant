"""MQTT client for Iotics — connects to AWS IoT via WSS 443 with SigV4.

Handles connection lifecycle, reconnection, and message dispatch.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Callable

from .iotics_api import aws_iot_wss_path, AWS_IOT_ENDPOINT

_LOGGER = logging.getLogger(__name__)

MQTT_KEEPALIVE = 30
MQTT_RECONNECT_DELAY = 5
MQTT_WATCHDOG_INTERVAL = 15
MQTT_WATCHDOG_TIMEOUT = 120  # reconnect if no msg in 120s


class IoticsMqttClient:
    """Manages the MQTT connection to AWS IoT via WebSocket Secure."""

    def __init__(self) -> None:
        self._client = None
        self._connected = False
        self._subscriptions: list[str] = []
        self._message_callback: Callable[[str, str], None] | None = None
        self._last_msg_time: float = 0
        self._watchdog_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()
        self._running = False

    def add_subscription(self, topic: str) -> None:
        """Add a topic to subscribe to once connected."""
        if topic not in self._subscriptions:
            self._subscriptions.append(topic)

    def set_message_callback(self, callback: Callable[[str, str], None]) -> None:
        """Set the callback for incoming MQTT messages."""
        self._message_callback = callback

    async def connect(self) -> None:
        """Connect to AWS IoT MQTT WSS in a background task."""
        if self._running:
            return
        self._running = True
        self._watchdog_task = asyncio.create_task(self._connect_loop())

    async def disconnect(self) -> None:
        """Disconnect MQTT."""
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        await self._do_disconnect()

    async def publish(self, topic: str, payload: str) -> bool:
        """Publish a message. Returns True on success."""
        if not self._client or not self._connected:
            return False
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._client.publish, topic, payload, 0
            )
            return True
        except Exception as err:
            _LOGGER.error("MQTT publish error: %s", err)
            return False

    async def _connect_loop(self) -> None:
        """Background loop that maintains MQTT connection."""
        import paho.mqtt.client as mqtt

        while self._running:
            try:
                client_id = f"hass-iotics-{int(time.time())}-{id(self)}"

                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=client_id,
                    protocol=mqtt.MQTTv311,
                    transport="websockets",
                )

                # TLS — AWS IoT requires it
                ctx = ssl.create_default_context()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                client.tls_set_context(ctx)

                # Signed WebSocket path
                signed_path = aws_iot_wss_path()
                client.ws_set_options(path=signed_path)

                # Callbacks
                def on_connect(c, userdata, flags, reason_code, properties):
                    self._connected = True
                    self._last_msg_time = time.time()
                    _LOGGER.info("MQTT connected (rc=%s)", reason_code)
                    for topic in self._subscriptions:
                        c.subscribe(topic, qos=0)
                    _LOGGER.info("MQTT subscribed to %d topics", len(self._subscriptions))

                def on_message(c, userdata, msg):
                    self._last_msg_time = time.time()
                    payload = msg.payload.decode("utf-8", "replace")
                    if self._message_callback:
                        try:
                            self._message_callback(msg.topic, payload)
                        except Exception as err:
                            _LOGGER.error("MQTT callback error: %s", err)

                def on_disconnect(c, userdata, flags, reason_code, properties):
                    self._connected = False
                    _LOGGER.info("MQTT disconnected (rc=%s)", reason_code)

                client.on_connect = on_connect
                client.on_message = on_message
                client.on_disconnect = on_disconnect

                self._client = client
                _LOGGER.info("Connecting MQTT to %s:443...", AWS_IOT_ENDPOINT)

                await asyncio.get_event_loop().run_in_executor(
                    None, client.connect, AWS_IOT_ENDPOINT, 443, MQTT_KEEPALIVE
                )
                client.loop_start()

                # Watchdog: keep connection alive
                while self._running:
                    await asyncio.sleep(MQTT_WATCHDOG_INTERVAL)
                    if not self._connected:
                        _LOGGER.info("MQTT not connected, reconnecting...")
                        break
                    if time.time() - self._last_msg_time > MQTT_WATCHDOG_TIMEOUT:
                        _LOGGER.info("MQTT watchdog: no msg for 120s, reconnecting...")
                        break

                client.loop_stop()
                await self._do_disconnect()

            except Exception as err:
                _LOGGER.error("MQTT connection error: %s", err)
                await self._do_disconnect()

            if self._running:
                await asyncio.sleep(MQTT_RECONNECT_DELAY)

    async def _do_disconnect(self) -> None:
        """Disconnect the MQTT client."""
        self._connected = False
        if self._client:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._client.disconnect)
            except Exception:
                pass
            self._client = None
