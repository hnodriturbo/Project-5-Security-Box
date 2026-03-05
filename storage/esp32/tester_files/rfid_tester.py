import sys
# This project convention: allow importing from one folder up
sys.path.append("..")


from classes.rfid_class import RFIDClass, DEFAULT_WHITELIST_HEX, DEFAULT_ALLOW_PREFIXES_HEX

def on_allowed(info):
    print("ALLOWED:", info)

def on_denied(info):
    print("DENIED:", info)

rfid = RFIDClass(
    sck_pin=18,
    mosi_pin=5,
    miso_pin=6,
    rst_pin=7,
    cs_pin=4,
    whitelist_hex=DEFAULT_WHITELIST_HEX,
    allow_prefixes_hex=DEFAULT_ALLOW_PREFIXES_HEX,
    on_allowed=on_allowed,
    on_denied=on_denied,
)

rfid.start()  # call after asyncio is running