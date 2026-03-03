# esp32/mqtt_broker.py
"""
MQTT manager for ESP32 Security Box.

Two background tasks:
- rx_loop: receives commands from dashboard
- tx_loop: sends telemetry to dashboard

Uses umqtt.simple (synchronous library) with asyncio wrapper pattern.
"""

import uasyncio as asyncio
import ujson
from umqtt.simple import MQTTClient


# Broker settings
PRIMARY_BROKER = "10.201.48.7"          # Raspberry Pi on school LAN
FALLBACK_BROKER = "broker.emqx.io"      # Public broker backup
TOPIC = "1404TOPIC"

# Timing
RX_CHECK_INTERVAL = 50    # how often to check for messages (ms)
TX_CHECK_INTERVAL = 20    # how often to send queued messages (ms)
RECONNECT_DELAY = 5000    # wait between reconnect attempts (ms)

# Queue limit
MAX_QUEUE_SIZE = 10       # drop old messages if queue gets full


class MqttBroker:
    """
    Manages MQTT connection and message flow for the security box.
    
    Usage:
        mqtt = MqttBroker(
            client_id="box_001",
            on_message=my_handler_function
        )
        mqtt.start()                          # call after asyncio starts
        mqtt.send({"event": "boot"})          # queue a message to send
    """
    
    def __init__(self, client_id, on_message=None):
        self.client_id = client_id
        self.on_message = on_message          # callback when message arrives
        
        # Connection status (read by controller for display)
        self.connected = False
        self.current_broker = None
        
        # Outbound message queue (list used as FIFO)
        self.send_queue = []
        
        # MQTT client object (recreated on each reconnect)
        self.client = None
    
    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------
    
    def send(self, message_dict):
        """
        Queue a message to send. Non-blocking.
        
        Args:
            message_dict: Python dict, will be converted to JSON
        """
        # Drop oldest message if queue is full
        if len(self.send_queue) >= MAX_QUEUE_SIZE:
            self.send_queue.pop(0)
        
        self.send_queue.append(message_dict)
    
    def start(self):
        """Start RX and TX background tasks. Call once after asyncio.run() starts."""
        asyncio.create_task(self.rx_loop())
        asyncio.create_task(self.tx_loop())
    
    # ----------------------------------------------------------------
    # Connection management
    # ----------------------------------------------------------------
    
    def connect(self):
        """
        Try to connect to MQTT broker.
        Tries primary first, then fallback.
        Returns True if connected, False if both failed.
        """
        for broker in [PRIMARY_BROKER, FALLBACK_BROKER]:
            try:
                print(f"[MQTT] Connecting to {broker}")
                
                # Create fresh client
                self.client = MQTTClient(
                    self.client_id,
                    broker,
                    port=1883,
                    keepalive=30
                )
                
                # Set callback for incoming messages
                self.client.set_callback(self.handle_raw_message_utility)
                
                # Connect and subscribe
                self.client.connect()
                self.client.subscribe(TOPIC.encode())
                
                # Success
                self.connected = True
                self.current_broker = broker
                print(f"[MQTT] Connected to {broker}")
                return True
                
            except Exception as e:
                print(f"[MQTT] Failed to connect to {broker}: {e}")
                continue
        
        # Both brokers failed
        self.connected = False
        self.client = None
        return False
    
    def handle_raw_message_utility(self, topic, raw_msg):
        """
        Called by umqtt when a message arrives.
        Parses JSON and forwards to on_message callback.
        """
        try:
            message_dict = ujson.loads(raw_msg)
            
            # Call the handler (usually controller.handle_mqtt_command)
            if self.on_message:
                self.on_message(message_dict)
                
        except Exception as e:
            print(f"[MQTT] Bad message: {e}")
    
    # ----------------------------------------------------------------
    # Background tasks
    # ----------------------------------------------------------------
    
    async def rx_loop(self):
        """
        Receive loop - runs forever.
        
        Checks for incoming messages every 50ms.
        Auto-reconnects if connection drops.
        """
        while True:
            # Connect if not connected
            if not self.connected:
                if not self.connect():
                    # Connection failed, wait before retry
                    await asyncio.sleep_ms(RECONNECT_DELAY)
                    continue
            
            # Check for one message (non-blocking)
            try:
                self.client.check_msg()
                
            except OSError:
                # Socket disconnected
                print("[MQTT] Connection lost")
                self.connected = False
                self.client = None
                
            except Exception as e:
                print(f"[MQTT] RX error: {e}")
                self.connected = False
                self.client = None
            
            # Yield to other tasks
            await asyncio.sleep_ms(RX_CHECK_INTERVAL)
    
    async def tx_loop(self):
        """
        Transmit loop - runs forever.
        
        Checks send queue every 20ms.
        Publishes messages when connected.
        """
        while True:
            # If we have messages and we're connected
            if self.send_queue and self.connected:
                # Get next message
                message_dict = self.send_queue.pop(0)
                
                try:
                    # Convert to JSON and publish
                    json_str = ujson.dumps(message_dict)
                    self.client.publish(TOPIC.encode(), json_str)
                    
                except Exception as e:
                    print(f"[MQTT] Send failed: {e}")
                    self.connected = False
                    self.client = None
                    
                    # Put message back at front of queue
                    self.send_queue.insert(0, message_dict)
            
            # Yield to other tasks
            await asyncio.sleep_ms(TX_CHECK_INTERVAL)