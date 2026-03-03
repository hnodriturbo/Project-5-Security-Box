from nicegui import ui
import os


# NiceGUI server config
NICEGUI_HOST = os.getenv(
    "NICEGUI_HOST", "127.0.0.1"
)  # Use "0.0.0.0" to open on your LAN IP
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))


def on_button_click():
    ui.notify("Button was clicked!")


def on_checkbox_change(event):
    state = "checked" if event.value else "unchecked"
    ui.notify(f"Checkbox is {state}")


def on_slider_change(event):
    ui.notify(f"Slider value: {event.value}")


def on_input_change(event):
    ui.notify(f"Input changed to: {event.value}")


ui.label("Event Handling Demo")

ui.button("Click Me", on_click=on_button_click)
ui.checkbox("Check Me", on_change=on_checkbox_change)
ui.slider(min=0, max=10, value=5, on_change=on_slider_change)
ui.input("Type something", on_change=on_input_change)


# Always use the NICEGUI_HOST and NICEGUI_PORT to use different port because
# the normal port is busy in my computer by apache/postgres.
ui.run(
    host=NICEGUI_HOST,  # bind address
    port=NICEGUI_PORT,  # bind port
    reload=True,
    title="NiceGUI Events & Actions Demo",
)
