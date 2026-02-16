# NiceGUI UI + MQTT publish logging (mini guide)

This guide covers:

- NiceGUI UI creation (expanded): containers, spacing, widths, backgrounds, and common patterns.
- MQTT `on_publish` logging: how to log publish confirmations into an on-page log window.

---

## 1) NiceGUI UI creation (expanded)

NiceGUI builds UI with Python context managers (`with ...:`). A “container” is just a component that holds other components.

### 1.1 Core container components

Most used:
- `ui.card()` boxed panel (group controls)
- `ui.row()` horizontal layout
- `ui.column()` vertical layout
- `ui.grid(columns=...)` grid layout
- `ui.separator()` divider line

Useful extras:
- `ui.scroll_area()` scrollable container (logs, long lists)
- `ui.expansion()` collapsible section (advanced controls)
- `ui.tabs()` + `ui.tab_panels()` multi-page UI on one route

### 1.2 Card + row + controls (baseline pattern)

```python
from nicegui import ui

@ui.page('/')
def index():
    with ui.card().classes('w-full p-4 border rounded'):
        ui.label('Skull Control').classes('text-lg font-bold')

        ui.separator()

        with ui.row().classes('gap-2'):
            ui.button('Eyes ON')
            ui.button('Eyes OFF')

        ui.separator()

        ui.label('Neck angle')
        ui.slider(min=0, max=180, value=90).props('label').classes('w-full')
```

### 1.3 Width control (why `w-50` didn’t work)

Tailwind has no `w-50` shorthand. Use one of these:
- `w-1/2` half width
- `w-full` full width
- `max-w-xl` (or `max-w-lg`, `max-w-2xl`) max width panel
- `w-[520px]` exact pixels

Centered “panel” pattern:

```python
with ui.row().classes('justify-center'):
    with ui.card().classes('w-full max-w-xl p-4 border rounded'):
        ui.label('Centered control panel')
```

### 1.4 Background colors (component-level)

Tailwind class:
```python
with ui.card().classes('w-full p-4 rounded bg-gray-100'):
    ui.label('Light background card')
```

Inline CSS:
```python
with ui.card().style('background-color: #0b1220; color: white;').classes('w-full p-4 rounded'):
    ui.label('Dark theme card')
```

### 1.5 Background color (whole page)

```python
ui.query('body').style('background-color: #0b1220; color: #e5e7eb;')
```

### 1.6 Spacing / alignment cheatsheet

- `p-4`, `p-2` padding
- `gap-2`, `gap-4` spacing inside rows/columns
- `mt-2`, `mb-2` margins
- `items-center` vertical align in a row
- `justify-center`, `justify-between` row alignment
- `rounded`, `border`, `border-gray-400`

### 1.7 Scalable “multiple cards” layout

```python
with ui.row().classes('justify-center w-full'):
    with ui.column().classes('w-full max-w-xl gap-4'):

        with ui.card().classes('p-4 border rounded'):
            ui.label('Eyes').classes('font-bold')

        with ui.card().classes('p-4 border rounded'):
            ui.label('Motors').classes('font-bold')

        with ui.card().classes('p-4 border rounded'):
            ui.label('Log').classes('font-bold')
```

### 1.8 More element commands (quick reference)

Text:
- `ui.label('text')`
- `ui.markdown('**bold**')`

Buttons:
- `ui.button('Title', on_click=handler)`
- `ui.button(...).props('color=negative')`

Inputs:
- `ui.input(label='Name')`
- `ui.number(label='Speed', value=10)`
- `ui.switch('Enabled')`
- `ui.checkbox('Option')`
- `ui.select(options=[...], value=...)`

Feedback:
- `ui.notify('Saved')`
- `ui.badge('Connected')`

Grouping:
- `ui.separator()`
- `ui.expansion('Advanced')`
- `ui.tabs()` / `ui.tab_panels()`

### 1.9 Reliable event pattern

Prefer reading values from the component itself:

```python
def on_changed():
    handler(component.value)

component.on('update:model-value', on_changed)
```

---

## 2) MQTT `on_publish` logging into your UI log

`on_publish` runs when the client finishes publishing.

- QoS 0: “sent/queued” (no broker ack required)
- QoS 1/2: confirms broker handshake

### 2.1 Minimal `on_publish` logger

```python
def on_publish(client, userdata, mid):
    log(f'Published mid={mid}')

client.on_publish = on_publish
```

### 2.2 Match publishes to payloads (queued -> published)

```python
PENDING: dict[int, dict] = {}

def send_command(payload: dict) -> None:
    ensure_mqtt_started()
    info = client.publish(TOPIC, json.dumps(payload).encode('utf-8'), qos=1)
    PENDING[info.mid] = payload
    log(f'Queued mid={info.mid}: {payload}')

def on_publish(client, userdata, mid):
    payload = PENDING.pop(mid, None)
    if payload is None:
        log(f'Published mid={mid}')
        return
    log(f'Published mid={mid}: {payload}')

client.on_publish = on_publish
```

### 2.3 When not to use `wait_for_publish()` in UI

`wait_for_publish()` blocks. Avoid it in slider callbacks. Use it only for one-off testing.

---

## 3) Compact “UI + MQTT logging” sample

```python
from nicegui import ui
import paho.mqtt.client as mqtt
import json
import time

BROKER = 'test.mosquitto.org'
PORT = 1883
TOPIC = '1404-remote-sender'

client = mqtt.Client()
mqtt_started = False

logs = []
PENDING = {}
log_box = None

def log(message):
    global log_box
    timestamp = time.strftime('%H:%M:%S')
    logs.append(f'[{timestamp}] {message}')
    if len(logs) > 50:
        logs.pop(0)
    if log_box is not None:
        log_box.set_value('\n'.join(logs))
    print(f'[{timestamp}] {message}')

def ensure_mqtt_started():
    global mqtt_started
    if mqtt_started:
        return
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_start()
    mqtt_started = True
    log(f'MQTT connected to {BROKER}:{PORT}')

def on_publish(client, userdata, mid):
    payload = PENDING.pop(mid, None)
    if payload is None:
        log(f'Published mid={mid}')
        return
    log(f'Published mid={mid}: {payload}')

client.on_publish = on_publish

def send_command(payload):
    ensure_mqtt_started()
    info = client.publish(TOPIC, json.dumps(payload).encode('utf-8'), qos=1)
    PENDING[info.mid] = payload
    log(f'Queued mid={info.mid}: {payload}')

def eyes_on():
    send_command({'type': 'eyes', 'enabled': True})

def eyes_off():
    send_command({'type': 'eyes', 'enabled': False})

@ui.page('/')
def index():
    global log_box
    ensure_mqtt_started()

    ui.query('body').style('background-color: #0b1220; color: #e5e7eb;')

    with ui.row().classes('justify-center w-full'):
        with ui.card().classes('w-full max-w-xl p-4 border border-gray-500 rounded bg-white'):
            ui.label('Skull Remote').classes('text-lg font-bold')

            with ui.row().classes('gap-2'):
                ui.button('Eyes ON', on_click=eyes_on)
                ui.button('Eyes OFF', on_click=eyes_off)

            ui.separator()

            log_box = ui.textarea(value='', label='Log').props('readonly').classes(
                'w-full h-44 border border-gray-400 rounded'
            )

            log('UI loaded')

ui.run(host='127.0.0.1', port=8090, reload=False)
```

---

## 4) Practical next steps

1) Keep QoS 0 while iterating fast.
2) Switch critical commands to QoS 1 later (stop_all, scene start/stop).
3) Add `/ack` from ESP32 when you want real hardware confirmation.
4) Keep the UI log compact and visible; it saves hours of guessing.
