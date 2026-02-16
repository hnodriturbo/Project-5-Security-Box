# -----------------------------
# Default imports for this part
# -----------------------------
import os
from datetime import datetime
import asyncio
from aiomqtt import Client
from random import randint
from nicegui import ui, app

# -----------------------------
# NiceGUI server config
# -----------------------------

NICEGUI_HOST = os.getenv("NICEGUI_HOST", "127.0.0.1")
# Use "0.0.0.0" to open on LAN

# Custom port because Apache/Postgres use the default port
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# Breyta sem heldur utan um gögnin frá MQTT
gognin = None

MQTT_BROKER = "test.mosquitto.org"
MQTT_TOPIC = "1404TOPIC"


async def mottaka():
    global gognin
    async with Client(MQTT_BROKER) as client:
        while True:
            await client.subscribe(MQTT_TOPIC)
            async for message in client.messages:
                gognin = message.payload.decode()


# vefsíðan þarf að vera í falli með decarator-num ui.page
@ui.page("/")
def root():
    gagna_label = ui.label("Engin gögn móttekin enn")

    def uppfaera_gogn():
        if gognin:
            gagna_label.set_text(f"{gognin}")

    ui.timer(1.0, uppfaera_gogn)  # uppfærist á einnar sekúndu fresti


# NiceGUI ræsir móttökufallið async
app.on_startup(mottaka)

# ræsa vefsíðu
# ui.run(root)
ui.run(
    root,
    host=NICEGUI_HOST,
    port=NICEGUI_PORT,
)
