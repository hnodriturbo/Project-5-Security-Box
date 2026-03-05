# tasks.py
# Coordinates solenoid pulse and reed confirmation

import uasyncio as asyncio


# ------------------------------
# Unlock flow
# ------------------------------
async def unlock_flow(
    solenoid,
    reed_switch,
    closed_state_value=1,
    pulse_duration_ms=200,
    confirmation_timeout_ms=1200,
    event_callback=None,
):
    if event_callback:
        event_callback("unlock_started", {})

    initial_state = await reed_switch.read_stable()

    await solenoid.pulse(duration_ms=pulse_duration_ms)

    changed_state = await reed_switch.wait_for_change(
        timeout_ms=confirmation_timeout_ms
    )

    if changed_state is None:
        if event_callback:
            event_callback("unlock_fault", {"reason": "no_reed_change"})
        return False

    drawer_is_closed = (changed_state == int(closed_state_value))

    if drawer_is_closed:
        if event_callback:
            event_callback("unlock_fault", {"reason": "still_closed"})
        return False

    if event_callback:
        event_callback("unlock_confirmed", {"state": changed_state})

    return True


# ------------------------------
# Background drawer monitor
# ------------------------------
async def drawer_monitor(
    reed_switch,
    closed_state_value=1,
    poll_interval_ms=50,
    event_callback=None,
):
    last_state = await reed_switch.read_stable()

    if event_callback:
        event_callback(
            "drawer_state",
            {"state": last_state, "is_closed": last_state == int(closed_state_value)},
        )

    while True:
        current = await reed_switch.read_stable()

        if current != last_state:
            last_state = current

            if event_callback:
                event_callback(
                    "drawer_state",
                    {"state": current, "is_closed": current == int(closed_state_value)},
                )

        await asyncio.sleep_ms(int(poll_interval_ms))


# ------------------------------
# Create background tasks
# ------------------------------
def create_system_tasks(reed_switch, event_callback=None):
    tasks = {}

    tasks["drawer_monitor"] = asyncio.create_task(
        drawer_monitor(
            reed_switch=reed_switch,
            event_callback=event_callback,
        )
    )

    return tasks