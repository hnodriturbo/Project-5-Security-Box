import network
import ntptime
import time
import machine
from machine import RTC



# Tengist Wi-Fi með SSID og lykilorði
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF) 
    wlan.active(True) # Kveikjum a wlan
    wlan.disconnect()  # Tryggir að eldri tenging er ekki til staðar
    print(f"Tenging við Wi-Fi netið: {ssid}...")

    wlan.connect(ssid, password)
    for _ in range(10):  # Reynir að tengjast í 10 sekúndur
        if wlan.isconnected() and wlan.config('essid') == ssid:
            print(f"Tengdur við Wi-Fi: {ssid}")
            print("Nettenging:", wlan.ifconfig())
            return ssid  # Skilar SSID ef tengist vel
        time.sleep(1)  # Bíður í sekúndu milli tilrauna

    print(f"Mistókst að tengjast Wi-Fi netinu: {ssid}")
    return None  # Skilar None ef tenging mistókst



# Samstillir tíma með NTP
def sync_time():
    try:
        ntptime.settime()  # Synca við ntp server
        print("Time synchronized")
    except:
        print("Error synchronizing time")


# Yfirfæra tímann yfir á lesanlegra form
def get_time():
    rtc = machine.RTC()
    current_time = (
        rtc.datetime()
    )  # Ná i tímann í (ár, mánuður, dagur, klst, mínóta, sekónta) formatti
    print(f"Klukkan í ESP32 hefur verið stillt á réttan tíma")
    print(f"Klukkan er: {current_time[0]}-{current_time[1]}-{current_time[2]} {current_time[4]}:{current_time[5]}:{current_time[6]}")
    


# Tengjast WiFi - Stilla Tíma - Prenta Tíma
def setup_wifi_and_time():
    """
    Reynir fyrst að tengjast við skólanetið (TskoliVESM).
    Ef það tekst ekki, tengist það við heimilið (Hringdu).
    """
    
    # Listi með tveimur tuples
    wifi_networks = [ ("Hringdu-jSy6", "FmdzuC4n"), ("TskoliVESM", "Fallegurhestur")]
    
    connected_ssid = None  # Gera tóma breytu fyrir netið

    # Nota svo for lúppu til að tengjast wifi úr listanum (bara til að það reyni bæði)
    for ssid, pwd in wifi_networks:
        connected_ssid = connect_wifi(ssid, pwd)
        if connected_ssid:  # If connected successfully, stop trying
            break

    # Athugar hvort tenging tókst
    if connected_ssid:
        print(f"Tengdur við netið {connected_ssid} í Verksmiðja" if connected_ssid == "TskoliVESM" 
              else f"Tengdur við heimilisnetið {connected_ssid}")

        # Samstillir tíma með NTP og birtir núverandi tíma
        sync_time()
        get_time()
    else:
        print("Ekki tókst að tengjast neinu Wi-Fi.")

