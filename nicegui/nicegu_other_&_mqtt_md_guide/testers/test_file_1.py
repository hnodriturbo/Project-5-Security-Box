from nicegui import ui
import os

# NiceGUI server config
NICEGUI_HOST = os.getenv(
    "NICEGUI_HOST", "127.0.0.1"
)  # Use "0.0.0.0" to open on your LAN IP
NICEGUI_PORT = int(os.getenv("NICEGUI_PORT", "8090"))

# Text elements
ui.label("Label")

ui.link("PythonGUIs", "https://pythonguis.com")

ui.chat_message("Hello, World!", name="PythonGUIs Chatbot")

ui.markdown(
    """
    # Markdown Heading 1
    **bold text**
    *italic text*
    `code`
    """
)

ui.restructured_text(
    """
    ==========================
    reStructuredText Heading 1
    ==========================
    **bold text**
    *italic text*
    ``code``
    """
)

ui.html("<strong>bold text using HTML tags</strong>", sanitize=False)


# Always use the NICEGUI_HOST and NICEGUI_PORT to use different port because
# the normal port is busy in my computer by apache/postgres.
ui.run(
    host=NICEGUI_HOST,  # bind address
    port=NICEGUI_PORT,  # bind port
    title="NiceGUI Text Elements",
)
