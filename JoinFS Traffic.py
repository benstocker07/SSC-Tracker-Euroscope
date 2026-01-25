import socket
import time
import json
import requests
from pathlib import Path
from SimConnect import SimConnect, AircraftRequests
import configparser
from pathlib import Path

config = configparser.ConfigParser()
config.read("JoinFS_config.txt")

SSC = config.getboolean("FEATURES", "SSC")
JoinFS = config.getboolean("FEATURES", "JoinFS")
FSHub = config.getboolean("FEATURES", "FSHub")

EUROSCOPE_IP = config.get("EUROSCOPE", "IP")
EUROSCOPE_PORT = config.getint("EUROSCOPE", "PORT")

SSC_URL = config.get("PATHS", "SSC_URL")
WHAZZUP = Path(config.get("PATHS", "JoinFS_WHAZZUP"))
FSHUB_FILE = config.get("PATHS", "FSHUB_FILE")

UPDATE_INTERVAL = config.getint("SETTINGS", "UPDATE_INTERVAL")
ASSUME_DELAY = config.getint("SETTINGS", "ASSUME_DELAY")
VATSIM_CACHE_TIME = config.getint("SETTINGS", "VATSIM_CACHE_TIME")

try:
    sm = SimConnect()
    aq = AircraftRequests(sm, _time=200)
except:
    sm = None
    aq = None

vatsim_cache = {"data": None, "last": 0}

def m_to_ft(m):
    return int(m)

def decode_squawk(raw):
    return ((raw >> 12) & 0xF) * 1000 + ((raw >> 8) & 0xF) * 100 + ((raw >> 4) & 0xF) * 10 + (raw & 0xF)

def get_ssr():
    try:
        raw = aq.get("TRANSPONDER_CODE:1")
        return decode_squawk(int(raw)) if raw else 7000
    except:
        return 7000

def fetch_ssc_items():
    try:
        return requests.get(SSC_URL, timeout=2).json().get("ITEMS", [])
    except:
        return []

def parse_joinfs():
    clients = []
    lines = WHAZZUP.read_text(errors="ignore").splitlines()
    in_clients = False
    for line in lines:
        if line.startswith("!CLIENTS"):
            in_clients = True
            continue
        if line.startswith("!SERVERS"):
            break
        if not in_clients or not line.strip():
            continue
        f = line.split(":")
        if len(f) < 10 or f[3] != "PILOT":
            continue
        try:
            clients.append({
                "ID": f[0],
                "LAT": float(f[5]),
                "LON": float(f[6]),
                "MSL": float(f[7]),
                "GS": float(f[8]),
                "MODEL": f[9].lstrip("/"),
                "TH": 0
            })
        except Exception:
            continue
    return clients

def parse_fshub():
    flights = {}
    try:
        with open(FSHUB_FILE, "r", encoding="utf-8", errors="ignore") as f:
            blocks = f.read().split("==== NEW WEBHOOK ====")
        for block in blocks:
            for line in block.splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                except:
                    continue
                if data.get("_type") != "flight.departed":
                    continue
                plan = data["_data"].get("plan", {})
                cs = plan.get("flight_no")
                if cs:
                    flights[cs] = {
                        "dep": plan.get("departure"),
                        "arr": plan.get("arrival"),
                        "route": plan.get("route", ""),
                        "icao": data["_data"]["aircraft"].get("icao"),
                        "crz": plan.get("cruise_lvl")
                    }
    except:
        pass
    return flights

def get_vatsim_data():
    now = time.time()
    if vatsim_cache["data"] is None or now - vatsim_cache["last"] > VATSIM_CACHE_TIME:
        try:
            vatsim_cache["data"] = requests.get(
                "https://data.vatsim.net/v3/vatsim-data.json", timeout=5
            ).json()
            vatsim_cache["last"] = now
        except:
            pass
    return vatsim_cache["data"]

def get_vatsim_fpl(callsign):
    data = get_vatsim_data()
    if not data:
        return None
    p = next((p for p in data["pilots"] if p["callsign"] == callsign), None)
    if not p or not p.get("flight_plan"):
        return None
    fp = p["flight_plan"]
    return {
        "dep": fp.get("departure"),
        "arr": fp.get("arrival"),
        "route": fp.get("route", ""),
        "icao": fp.get("aircraft_short"),
        "rfl": fp.get("altitude")
    }

def build_fpl(ac, fshub):
    cs = ac["ID"].upper()
    gs = int(ac.get("GS", 250))
    dep = "ZZZZ"
    arr = "ZZZZ"
    route = ""
    acft = ac.get("MODEL", "ZZZZ")
    rfl = None
    if acft == "Typhoon":
        acft = "EUFI"
    if cs in fshub:
        d = fshub[cs]
        dep, arr, route, acft, rfl = d["dep"], d["arr"], d["route"], d["icao"] or acft, d["crz"]
    else:
        v = get_vatsim_fpl(cs)
        if v:
            dep, arr, route, acft, rfl = v["dep"] or dep, v["arr"] or arr, v["route"], v["icao"] or acft, v["rfl"]
    alt = f"FL{int(rfl):03}" if rfl else f"FL{int(m_to_ft(ac.get('MSL',0))/100):03.0f}"
    return f"$FP{cs}:*A:I:H/{acft}/L:{gs}:{dep}:0000:0000:{alt}:{arr}:0:30:2:00:{arr}:/V/:{route}"

def build_pos(ac):
    sq = get_ssr()
    return f"@N:{ac['ID']}:{sq:04d}:1:{ac['LAT']:.5f}:{ac['LON']:.5f}:{m_to_ft(ac['MSL'])}:{int(ac['GS'])}:{int(ac['TH'])}:0"

def build_assume(ctrl, cs):
    return f"$CQ{ctrl}:@94835:IT:{cs}"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((EUROSCOPE_IP, EUROSCOPE_PORT))
sock.listen(1)
print("Waiting for Euroscope...")
conn, _ = sock.accept()
conn.sendall(b"#AA\r\n")
conn.setblocking(False)

fpl_sent = set()
assumed = set()
first_seen = {}
controller = None
fshub_cache = parse_fshub() if FSHub else {}

while True:
    try:
        data = conn.recv(4096).decode(errors="ignore")
        for l in data.splitlines():
            if "SERVER:ATC:" in l:
                controller = l.split("SERVER:ATC:", 1)[1].strip()
    except:
        pass
    if SSC:
        aircraft = fetch_ssc_items()
    elif JoinFS:
        aircraft = parse_joinfs()
    else:
        aircraft = []
    now = time.time()
    for ac in aircraft:
        cs = ac["ID"]
        if cs not in first_seen:
            first_seen[cs] = now
        if cs not in fpl_sent:
            conn.sendall((build_fpl(ac, fshub_cache) + "\r\n").encode())
            fpl_sent.add(cs)
        if controller and cs not in assumed and now - first_seen[cs] >= ASSUME_DELAY:
            conn.sendall((build_assume(controller, cs) + "\r\n").encode())
            assumed.add(cs)
        conn.sendall((build_pos(ac) + "\r\n").encode())
    time.sleep(UPDATE_INTERVAL)
