import subprocess, sys, socket, time, json, os, re, urllib.parse, zipfile
import tkinter as tk
from tkinter import messagebox

MOCK_AIRCRAFT = True

packages = ["requests", "SimConnect", "playwright"]

for pkg in packages:
    subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)

import threading, requests
from playwright.sync_api import sync_playwright

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_script = os.path.join(script_dir, "Settings.py")

        subprocess.run([sys.executable, settings_script], check=False)
        print('Running initial setup...')

    with open(CONFIG_FILE, "r") as f:
        cfg = json.load(f)
    return cfg

config = load_config()

CPDLC_Test = config["CPDLC_Test"]
HOPPIE_CODE = config["HOPPIE_CODE"]
tanker = config["Callsign to send CPDLC"]
USING_SSC = config["Using SSC App"]
SERVER = config["SSC Server"]
WHAZZUP_FILE = config["JoinFS whazzup.txt path"]
SSC_URL = config["SSC_URL"]
UPDATE_INTERVAL = config["UPDATE_INTERVAL"]
ASSUME_DELAY = config["ASSUME_DELAY"]

EUROSCOPE_IP = config["EUROSCOPE_IP"]
EUROSCOPE_PORT = config["EUROSCOPE_PORT"]

token = config["FSHUB_API_KEY"]

USE_SHIP_TARGETS = False

ssc_data = []
ssc_lock = threading.Lock()

def ShipTargets():
    return [
        {"name": "TARGET1", "lat": 52.88485, "lon": 0.15074},
        {"name": "TARGET2", "lat": 52.86498, "lon": 0.19020},
    ]

def get_mock_aircraft():
    return [
        {
            "ID": "GAXTL",
            "CALLSIGN": "GAXTL",
            "LAT": 59.2619,
            "LON": 24.2235,
            "MSL": 200,
            "GS": 100,
            #TH = True Heading
            "TH": 90,
            "MODEL": "P28A",
            "MOCK": True
        }
    ] if MOCK_AIRCRAFT else []

def build_ship_pos(ship, offset):
    lat = ship["lat"] + offset
    return f"@N:{ship['name']}:7000:1:{lat:.5f}:{ship['lon']:.5f}:1000:5:90:0"

def build_ship_fpl(ship):
    return f"$FP{ship['name']}:*A:I:V/SHIP/L:0:ZZZZ:0000:0000:VFR:ZZZZ:0:00:0:00:ZZZZ:/V/:"

def build_ship_assume(ship, controller):
    return f"$CQ{controller}:@94835:IT:{ship['name']}"

targets = ShipTargets() if USE_SHIP_TARGETS else []
ship_offsets = {s["name"]: 0 for s in targets}

url = "https://github.com/VATSIM-UK/UK-Sector-File/releases/download/2026%2F04/UK_2026_04.zip"
releases_url = "https://github.com/VATSIM-UK/UK-Sector-File/releases"

base = os.path.expandvars(r"%APPDATA%\EuroScope")
zip_path = os.path.join(base, "uk_controller_pack.zip")
sector_dir = os.path.join(base, "UK", "Data", "Sector")

def install():
    os.makedirs(base, exist_ok=True)
    r = requests.get(url, stream=True)
    with open(zip_path, "wb") as f:
        for c in r.iter_content(8192):
            f.write(c)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(base)
        
def show_error(msg):
    root.after(0, lambda: messagebox.showerror("SSC Error", msg))

def get_latest_release():
    r = requests.get(releases_url)
    m = re.search(r'/releases/tag/([^"]+)', r.text)
    return urllib.parse.unquote(m.group(1)).replace("/", "_") if m else None

def get_local_sector():
    if os.path.exists(sector_dir):
        for f in os.listdir(sector_dir):
            if f.endswith(".sct") and "UK_" in f:
                return f
    return None

root = None

root = tk.Tk()
root.withdraw()

def run_tk():
    root.mainloop()

latest = get_latest_release()
local = get_local_sector()

def ask_update():
    result = {}

    def _ask():
        result["value"] = messagebox.askyesno(
            "Update required for the UKCP",
            "Install/update UK Controller Pack?"
        )

    root.after(0, _ask)

    while "value" not in result:
        root.update()
        time.sleep(0.05)

    return result["value"]

if not (latest and local and latest in local):
    if ask_update():
        install()
        messagebox.showinfo("Done", "Installed")

from SimConnect import SimConnect, AircraftRequests

VATSIM_CACHE_TIME = 30

SPECIAL_ROUTES = {
    k.upper(): {
        "dep": v["dep"].upper(),
        "arr": v["arr"].upper(),
        "route": v["route"].upper(),
        "fl": v["fl"].upper()
    }
    for k, v in config.get("SPECIAL_ROUTES", {}).items()
}

try:
    sm = SimConnect()
    aq = AircraftRequests(sm, _time=200)
except:
    aq = None

vatsim_cache = {"data": None, "last": 0}
fshub_cache = {}
whazzup_cache = {}

def fetch_ssc_items():
    try:
        return requests.get(SSC_URL, timeout=2).json().get("ITEMS", [])
    except:
        return []

def to_float(v):
    v = (v or "").strip().lower()
    v = re.sub(r"[^0-9.\-]", "", v)
    return float(v) if v else 0.0

def ssc_scraper():
    global ssc_data

    def clean(v):
        v = (v or "").strip()
        return v if v else "0"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("http://ssc-tracker.org/", wait_until="domcontentloaded")

        page.wait_for_timeout(2000)

        selector = f'button[data-gn="{SERVER}"]'

        button = page.locator(selector)

        print(button.count())

        if button.count() == 0:
            show_error(f"No traffic seen on {SERVER}")
            return

        button.first.wait_for(state="visible", timeout=15000)
        button.first.click()

        page.wait_for_selector("#ssc-setup")
        page.click("#ssc-setup")

        cols = page.locator("input[id^='col-']")
        EXCLUDE = {"GS", "MSL", "ID"}

        for i in range(cols.count()):
            col = cols.nth(i)
            col_id = col.get_attribute("id")
            name = col_id.replace("col-", "").upper()
            if any(ex in name for ex in EXCLUDE):
                continue
            page.locator(f"label[for='{col_id}']").click()

        page.click("#ssc-setup")
        page.keyboard.press("Escape")
        page.wait_for_selector("a.callsign")

        def get(header_map, tds, name):
            i = header_map.get(name)
            if i is None or i >= len(tds):
                return "0"
            return clean(tds[i].inner_text())

        while True:
            callsigns = page.query_selector_all("a.callsign")
            headers = page.query_selector_all("#ssc-acheader th")

            header_map = {}
            for i, h in enumerate(headers):
                title = (h.get_attribute("title") or h.inner_text() or "").strip().upper()
                header_map[title] = i

            live = []

            for c in callsigns:
                row = c.evaluate_handle("el => el.closest('tr')")
                tds = row.query_selector_all("td")

                pid = c.get_attribute("pilotid") or ""
                if not pid:
                    continue

                live.append({
                    "ID": pid,
                    "CALLSIGN": c.inner_text().strip(),
                    "LAT": float(c.get_attribute("latitude") or 0),
                    "LON": float(c.get_attribute("longitude") or 0),
                    "MSL": to_float(get(header_map, tds, "ALTITUDE ABOVE MSL")),
                    "GS": to_float(get(header_map, tds, "GROUNDSPEED")),
                    "TH": to_float(get(header_map, tds, "TRUE HEADING")),
                    "MODEL": get(header_map, tds, "AC") or get(header_map, tds, "MODEL")
                })
            with ssc_lock:
                ssc_data = live
            time.sleep(1)

if not USING_SSC:
    threading.Thread(target=ssc_scraper, daemon=True).start()

def parse_whazzup():
    out = {}
    try:
        with open(WHAZZUP_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if "!CLIENTS" not in "".join(lines):
            return out
        start = lines.index("!CLIENTS\n") + 1
        for line in lines[start:]:
            if line.startswith("!"):
                break
            p = line.split(":")
            if len(p) > 10:
                cs = p[0].upper()
                out[cs] = {
                    "lat": float(p[5]),
                    "lon": float(p[6]),
                    "alt": int(p[7]),
                    "gs": int(p[8]),
                    "icao": p[9].replace("/ATCCOM.AC_MODEL ", "").strip()
                }
    except:
        pass
    return out

def parse_fshub():
    try:
        r = requests.get(
            "https://app.vtacraf.uk/flightplans/fshub",
            headers={"x-api-key": token},
            timeout=5
        )
        r.raise_for_status()
        if r.status_code == 403:
            print('Invalid API key')
        data = r.json()

        def parse_dep_arr(route: str):
            if not route:
                return "", ""

            parts = route.strip().upper().split()

            if len(parts) == 0:
                return "", ""

            dep = parts[0]
            arr = parts[-1]

            return dep, arr

        out = {}

        for item in data.get("flightplans", []):
            cs = (item.get("callsign") or "").upper()

            route = (item.get("route") or "").upper()

            dep, arr = parse_dep_arr(route)

            out[cs] = {
                "dep": dep,
                "arr": arr,
                "route": route,
                "icao": None,
                "crz": item.get("cruise_level")
            }

        return out

    except Exception as e:
        print(e)
        return {}

def fshub_updater():

    global fshub_cache

    while True:

        try:
            if token:
                fshub_cache = parse_fshub()

        except Exception as e:
            err = str(e)

            print("FSHUB ERROR:", err)

        time.sleep(30)

threading.Thread(target=fshub_updater, daemon=True).start()

def get_vatsim():
    now = time.time()
    if not vatsim_cache["data"] or now - vatsim_cache["last"] > VATSIM_CACHE_TIME:
        try:
            vatsim_cache["data"] = requests.get("https://data.vatsim.net/v3/vatsim-data.json").json()
            vatsim_cache["last"] = now
        except:
            pass
    return vatsim_cache["data"]

def get_ssr():
    try:
        return int(aq.get("TRANSPONDER_CODE:1"))
    except:
        return 7000

def build_pos(ac):
    return f"@N:{ac['ID']}:{get_ssr():04d}:1:{ac['LAT']:.5f}:{ac['LON']:.5f}:{int(ac['MSL'])}:{int(ac['GS'])}:{int(ac['TH'])}:0"

def build_fpl(ac):
    cs = ac["ID"].upper()
    acft = ac.get("MODEL") or "ZZZZ"

    if "TYPHOON" in acft.upper() or acft.upper() == "EFA":
        acft = "EUFI"

    if "ZK" in acft.upper() or acft.upper() == "EFA":
        acft = "EUFI"

    if "VULCAN" in acft.upper():
        acft = 'VULC'

    if "TORNADO" in acft.upper():
        acft = 'TOR'

    if "CHINOOK" in acft.upper():
        acft = 'H47'

    if "APACHE" in acft.upper():
        acft = 'H64'

    if acft == "F-111":
        acft = "F111"

    dep = arr = route = ""
    rfl = None

    if cs in SPECIAL_ROUTES:
        d = SPECIAL_ROUTES[cs]

        dep = d.get("dep") or ""
        arr = d.get("arr") or ""
        route = d.get("route") or ""
        rfl = str(d.get("fl") or "").replace("FL", "")

    if cs in fshub_cache:
        d = fshub_cache[cs]

        dep = d.get("dep") or ""
        arr = d.get("arr") or ""
        route = (d.get("route") or "").upper().strip()
        acft = d.get("icao") or acft
        rfl = d.get("crz")

    alt = f"FL{int(rfl):03}" if rfl else "FL300"

    return f"$FP{cs}:*A:I:H/{acft}/L:250:{dep}:0000:0000:{alt}:{arr}:0:30:2:00:{arr}:/V/:{route}"

sock = socket.socket()
sock.bind((EUROSCOPE_IP, EUROSCOPE_PORT))
sock.listen(5)

conn, _ = sock.accept()
conn.sendall(b"#AA\r\n")
conn.setblocking(False)

controller = None
seen = {}
sent = set()
assumed = set()

def send_telex(frm, to, msg):
    if not CPDLC_Test:
        return
    requests.post("https://www.hoppie.nl/acars/system/connect.html", data={
        "logon": HOPPIE_CODE,
        "from": frm,
        "to": to,
        "type": "telex",
        "packet": msg
    })

while True:
    try:
        data = conn.recv(4096).decode(errors="ignore")
        for l in data.splitlines():
            if l.startswith("#TM"):
                p = l.split(":")
                if len(p) > 2:
                    s = p[0][3:]
                    r = ":".join(p[2:])
                    if "," in r:
                        t, m = r.split(",", 1)
                        if t == "":
                            t = tanker
                        send_telex(s, t.strip(), m.strip())
            if "SERVER:ATC:" in l:
                controller = l.split(":")[-1].strip()
    except:
        pass

    if USING_SSC:
        items = fetch_ssc_items() + get_mock_aircraft()
    else:
        with ssc_lock:
            items = ssc_data.copy() + get_mock_aircraft()
        now = time.time()   

    for ac in items:
        cs = ac["ID"].upper()

        if cs not in seen:
            seen[cs] = now

        if cs not in sent:
            conn.sendall((build_fpl(ac) + "\r\n").encode())
            sent.add(cs)

        conn.sendall((build_pos(ac) + "\r\n").encode())

        if controller and cs not in assumed and now - seen[cs] > ASSUME_DELAY:
            conn.sendall((f"$CQ{controller}:@94835:IT:{cs}\r\n").encode())
            assumed.add(cs)
            print(f'Assuming {cs}')

    time.sleep(UPDATE_INTERVAL)    
