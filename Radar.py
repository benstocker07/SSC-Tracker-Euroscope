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
        return json.load(f)

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

ssc_data = []
ssc_lock = threading.Lock()

def get_id(ac):
    return (ac.get("CALLSIGN") or ac.get("ID") or "").upper().strip()

def get_mock_aircraft():
    return [{
        "ID": "GAXTL",
        "CALLSIGN": "GAXTL",
        "LAT": 59.2619,
        "LON": 24.2235,
        "MSL": 200,
        "GS": 100,
        "TH": 90,
        "MODEL": "P28A",
    }] if MOCK_AIRCRAFT else []

def fetch_ssc_items():
    try:
        return requests.get(SSC_URL, timeout=2).json().get("ITEMS", [])
    except:
        return []

def ssc_scraper():
    global ssc_data

    def clean_text(v):
        v = (v or "").strip()
        return v if v else "0"

    def to_float(v):
        v = (v or "").strip()
        v = re.sub(r"[^0-9.\-]", "", v)
        return float(v) if v else 0.0

    def to_int(v):
        v = (v or "").strip()
        v = re.sub(r"[^0-9\-]", "", v)
        return int(v) if v else 0

    def clean_model(v):
        v = str(v or "").upper().strip()

        v = v.replace("ATCCOM.AC_MODEL_", "")
        v = v.replace("ATCCOM.AC_MODEL", "")
        v = v.replace("$$:", "")
        v = v.replace("$$", "")

        v = re.sub(r"\..*$", "", v) 
        v = re.sub(r"[^A-Z0-9-]", "", v)

        if "TYPHOON" in v:
            return "EUFI"

        if "C17" in v:
            return "C17"

        return v or "ZZZZ"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("http://ssc-tracker.org/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        selector = f'button[data-gn="{SERVER}"]'
        button = page.locator(selector)

        if button.count() == 0:
            print("No SSC traffic")
            return

        button.first.click()

        page.wait_for_selector("#ssc-setup")
        page.click("#ssc-setup")

        cols = page.locator("input[id^='col-']")
        EXCLUDE = {"GS", "MSL", "ID"}

        for i in range(cols.count()):
            col = cols.nth(i)
            col_id = col.get_attribute("id") or ""
            name = col_id.replace("col-", "").upper()

            if any(ex in name for ex in EXCLUDE):
                continue

            page.locator(f"label[for='{col_id}']").click()

        page.click("#ssc-setup")
        page.keyboard.press("Escape")

        page.wait_for_selector("a.callsign")

        headers = page.query_selector_all("#ssc-acheader th")
        header_map = {}

        for i, h in enumerate(headers):
            title = (h.get_attribute("title") or h.inner_text() or "").strip().upper()
            header_map[title] = i

        def get(tds, name):
            i = header_map.get(name)
            if i is None or i >= len(tds):
                return "0"
            return clean_text(tds[i].inner_text())

        while True:
            callsigns = page.query_selector_all("a.callsign")
            live = []

            for c in callsigns:
                row = c.evaluate_handle("el => el.closest('tr')")
                tds = row.query_selector_all("td")

                pid = c.get_attribute("pilotid") or ""
                if not pid:
                    continue

                model_raw = get(tds, "MODEL") or get(tds, "AC")
                ac_type = clean_model(model_raw)

                live.append({
                    "ID": pid,
                    "CALLSIGN": pid,
                    "LAT": float(c.get_attribute("latitude") or 0),
                    "LON": float(c.get_attribute("longitude") or 0),
                    "MSL": to_int(get(tds, "ALTITUDE ABOVE MSL")),
                    "GS": to_int(get(tds, "GROUNDSPEED")),
                    "TH": to_int(get(tds, "TRUE HEADING")),
                    "MODEL": ac_type
                })

            with ssc_lock:
                ssc_data = live

            time.sleep(1)

if not USING_SSC:
    threading.Thread(target=ssc_scraper, daemon=True).start()

def parse_fshub():
    try:
        r = requests.get(
            "https://app.vtacraf.uk/flightplans/fshub",
            headers={"x-api-key": token},
            timeout=5
        )
        r.raise_for_status()
        data = r.json()

        out = {}

        for item in data.get("flightplans", []):
            cs = (item.get("callsign") or "").upper()
            if not cs:
                continue

            route = (item.get("route") or "").upper()
            parts = route.split()

            dep = parts[0] if parts else ""
            arr = parts[-1] if parts else ""

            out[cs] = {
                "dep": dep,
                "arr": arr,
                "route": route,
                "crz": item.get("cruise_level")
            }

        return out

    except:
        return {}

def fshub_updater():
    global fshub_cache
    fshub_cache = {}

    while True:
        if token:
            fshub_cache = parse_fshub()
        time.sleep(30)

threading.Thread(target=fshub_updater, daemon=True).start()

sock = socket.socket()
sock.bind((EUROSCOPE_IP, EUROSCOPE_PORT))
sock.listen(1)

conn, _ = sock.accept()
conn.sendall(b"#AA\r\n")
conn.setblocking(False)

controller = None
seen = {}
sent = set()
assumed = set()

def safe_send(data):
    try:
        conn.sendall(data)
    except:
        pass

def build_pos(ac):
    cs = get_id(ac)
    return f"@N:{cs}:7000:1:{ac['LAT']:.5f}:{ac['LON']:.5f}:{int(ac['MSL'])}:{int(ac['GS'])}:{int(ac['TH'])}:0"

def build_fpl(ac):
    cs = get_id(ac)

    raw = (ac.get("MODEL") or "").upper().strip()

    raw = raw.replace("ATCCOM.AC_MODEL_", "")
    raw = raw.replace("$$:", "")
    raw = raw.replace("$$", "")

    if "TYPHOON" in raw:
        acft = "EUFI"
    elif "C17" in raw or "C-17" in raw:
        acft = "C17"
    else:
        acft = re.sub(r"[^A-Z0-9-]", "", raw) or "ZZZZ"

    print("Aircraft Model:", raw, "->", acft)

    dep = arr = route = ""
    rfl = None

    if cs in fshub_cache:
        d = fshub_cache[cs]
        dep = d.get("dep") or ""
        arr = d.get("arr") or ""
        route = d.get("route") or ""
        rfl = d.get("crz")

    alt = f"FL{int(rfl):03}" if rfl else "FL300"

    return f"$FP{cs}:*A:I:H/{acft}/L:250:{dep}:0000:0000:{alt}:{arr}:0:30:2:00:{arr}:/V/:{route}"

def fsd_keepalive():
    while True:
        safe_send(b"#AA\r\n")
        time.sleep(5)

threading.Thread(target=fsd_keepalive, daemon=True).start()

while True:
    now = time.time()

    try:
        data = conn.recv(4096).decode(errors="ignore")
        print(data)
        for l in data.splitlines():
            if "SERVER:ATC:" in l:
                controller = l.split(":")[-1].strip()
    except:
        pass

    items = []

    if USING_SSC:
        items = fetch_ssc_items()
    else:
        with ssc_lock:
            items = ssc_data.copy()

    for ac in items:

        cs = get_id(ac)
        if not cs:
            continue

        if cs not in seen:
            seen[cs] = now

        if cs not in sent:
            safe_send((build_fpl(ac) + "\r\n").encode())
            sent.add(cs)

        safe_send((build_pos(ac) + "\r\n").encode())

        if controller and cs not in assumed and now - seen[cs] > ASSUME_DELAY:
            safe_send((f"$CQ{controller}:@94835:IT:{cs}\r\n").encode())
            assumed.add(cs)

    time.sleep(UPDATE_INTERVAL)
