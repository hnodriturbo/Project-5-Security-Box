# 03_timer_data.py
# Timer + simple data element demo (no charts)

from nicegui import ui
from datetime import datetime
import os

# NiceGUI server config
NICEGUI_HOST = os.getenv(
    "NICEGUI_HOST", "127.0.0.1"
)  # Use "0.0.0.0" to open on your LAN IP
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

last_10_times = []  # stores last 10 timestamps


@ui.page("/")
def index():
    ui.label("Timer + data demo")

    current_time_label = ui.label("Time: --:--:--")  # shows live time
    last_list_label = ui.label("Last 10 ticks: (none)")  # shows stored values

    def tick():
        # update live label
        now = datetime.now().strftime("%H:%M:%S")
        current_time_label.set_text(f"Time: {now}")

        # store last 10 values
        last_10_times.append(now)
        if len(last_10_times) > 10:
            last_10_times.pop(0)

        # render stored values as simple text
        last_list_label.set_text("Last 10 ticks: " + ", ".join(last_10_times))

    ui.timer(1.0, tick)  # run tick() every 1 second


# ui.run(title="NiceGUI - Timer/Data", reload=True)

# Always use the NICEGUI_HOST and NICEGUI_PORT to use different port because
# the normal port is busy in my computer by apache/postgres.
ui.run(
    host=NICEGUI_HOST,  # bind address
    port=NICEGUI_PORT,  # bind port
    reload=True,
    title="NiceGUI - Timer/Data",
)
