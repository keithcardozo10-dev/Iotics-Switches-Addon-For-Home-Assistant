"""MQTT client for Iotics -- connects to AWS IoT via WSS 443 with SigV4.

Exact replica of the Mac realtime server's MQTT approach:
- paho-mqtt with transport="websockets"
- SigV4-signed path via aws_iot_wss_path()
- Sec-WebSocket-Protocol: mqtt header (required by AWS IoT)
- Watchdog with reconnect on connection loss or 120s silence

DEBUG VERSION -- verbose logging
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
        _LOGGER.info("MQTT: __init__ called (id=%s)", id(self))
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
            _LOGGER.info("MQTT: added subscription %s (total=%d)", topic, len(self._subscriptions))

    def set_message_callback(self, callback: Callable[[str, str], None]) -> None:
        """Set the callback for incoming MQTT messages."""
        self._message_callback = callback
        _LOGGER.info("MQTT: message callback set")

    async def connect(self) -> None:
        """Connect to AWS IoT MQTT WSS in a background task."""
        _LOGGER.info("MQTT: connect() called, running=%s", self._running)
        if self._running:
            return
        self._running = True
        _LOGGER.info("MQTT: creating _connect_loop task...")
        self._watchdog_task = asyncio.create_task(self._connect_loop())
        _LOGGER.info("MQTT: _connect_loop task created")

    async def disconnect(self) -> None:
        """Disconnect MQTT."""
        _LOGGER.info("MQTT: disconnect() called")
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        await self._do_disconnect()

    async def publish(self, topic: str, payload: str) -> bool:
        """Publish a message. Returns True on success."""
        if not self._client or not self._connected:
            _LOGGER.debug("MQTT: publish skipped (not connected)")
            return False
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._client.publish, topic, payload, 0
            )
            _LOGGER.debug("MQTT: published %s", topic)
            return True
        except Exception as err:
            _LOGGER.error("MQTT publish error: %s", err)
            return False

    async def _connect_loop(self) -> None:
        """Background loop that maintains MQTT connection (exact Mac replica)."""
        _LOGGER.info("MQTT: _connect_loop started (id=%s)", id(self))
        import paho.mqtt.client as mqtt

        while self._running:
            _LOGGER.info("MQTT: connect iteration starting...")
            try:
                client_id = f"hass-iotics-{int(time.time())}-{id(self)}"
                _LOGGER.info("MQTT: client_id=%s", client_id)

                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=client_id,
                    protocol=mqtt.MQTTv311,
                    transport="websockets",
                )
                _LOGGER.info("MQTT: paho client created")

                # TLS -- _create_unverified_context matches standalone bridge pattern
                ctx = ssl._create_unverified_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                client.tls_set_context(ctx)
                _LOGGER.info("MQTT: TLS context set")

                # SigV4 signed path + required WS protocol header
                signed_path = aws_iot_wss_path()
                _LOGGER.info("MQTT: signed path len=%d, first 100=%s", len(signed_path), signed_path[:100])
                client.ws_set_options(
                    path=signed_path,
                    headers={"Sec-WebSocket-Protocol": "mqtt"},
                )
                _LOGGER.info("MQTT: ws_set_options set with Sec-WebSocket-Protocol: mqtt")

                # Callbacks
                def on_connect(c, userdata, flags, reason_code, properties):
                    self._connected = True
                    self._last_msg_time = time.time()
                    _LOGGER.info("MQTT: CONNECTED (rc=%s, flags=%s)", reason_code, flags)
                    for topic in self._subscriptions:
                        _LOGGER.info("MQTT: subscribing to %s", topic)
                        c.subscribe(topic, qos=0)
                    _LOGGER.info("MQTT: subscribed to %d topics", len(self._subscriptions))

                def on_message(c, userdata, msg):
                    self._last_msg_time = time.time()
                    payload = msg.payload.decode("utf-8", "replace")
                    _LOGGER.debug("MQTT: msg on %s: %s", msg.topic, payload)
                    if self._message_callback:
                        try:
                            self._message_callback(msg.topic, payload)
                        except Exception as err:
                            _LOGGER.error("MQTT callback error: %s", err)

                def on_disconnect(c, userdata, flags, reason_code, properties):
                    self._connected = False
                    _LOGGER.warning("MQTT: DISCONNECTED (rc=%s)", reason_code)

                client.on_connect = on_connect
                client.on_message = on_message
                client.on_disconnect = on_disconnect
                _LOGGER.info("MQTT: callbacks registered")

                self._client = client
                _LOGGER.info("MQTT: calling client.connect(%s, 443)...", AWS_IOT_ENDPOINT)

                await asyncio.get_event_loop().run_in_executor(
                    None, client.connect, AWS_IOT_ENDPOINT, 443, MQTT_KEEPALIVE
                )
                _LOGGER.info("MQTT: client.connect returned, starting loop...")
                client.loop_start()
                _LOGGER.info("MQTT: loop_start done, entering watchdog...")

                # Watchdog: reconnect on connection loss or 120s silence
                loops = 0
                while self._running:
                    await asyncio.sleep(MQTT_WATCHDOG_INTERVAL)
                    loops += 1
                    _LOGGER.debug("MQTT: watchdog check %d (connected=%s, last_msg=%.1fs ago)", 
                                  loops, self._connected, time.time() - self._last_msg_time if self._last_msg_time else 0)
                    if not self._connected:
                        _LOGGER.warning("MQTT: not connected, reconnecting...")
                        break
                    if self._last_msg_time and time.time() - self._last_msg_time > MQTT_WATCHDOG_TIMEOUT:
                        _LOGGER.warning("MQTT: watchdog: no msg for 120s, reconnecting...")
                        break

                _LOGGER.info("MQTT: watchdog loop exited")
                client.loop_stop()
                await self._do_disconnect()

            except Exception as err:
                _LOGGER.error("MQTT: connection error: %s", err, exc_info=True)
                await self._do_disconnect()

            if self._running:
                _LOGGER.info("MQTT: will retry in %ds", MQTT_RECONNECT_DELAY)
                await asyncio.sleep(MQTT_RECONNECT_DELAY)
            else:
                _LOGGER.info("MQTT: _running=False, exiting connect loop")

    async def _do_disconnect(self) -> None:
        """Disconnect the MQTT client."""
        _LOGGER.info("MQTT: _do_disconnect")
        self._connected = False
        if self._client:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._client.disconnect)
            except Exception as e:
                _LOGGER.debug("MQTT: disconnect error: %s", e)
            self._client = None
