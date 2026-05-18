import tkinter as tk
from tkinter import ttk, messagebox
import json, os, sys, secrets, requests

root = None

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "Using SSC App": True,
    "CPDLC_Test": False,
    "HOPPIE_CODE": "",
    "Callsign to send CPDLC": "",
    "SSC Server": "",
    "SSC_URL": "http://127.0.0.1:55055/json",
    "JoinFS whazzup.txt path": "",
    "UPDATE_INTERVAL": 1,
    "ASSUME_DELAY": 5,
    "EUROSCOPE_IP": "0.0.0.0",
    "EUROSCOPE_PORT": 6809,
    "SPECIAL_ROUTES": {},
    "FSHUB_API_KEY": "",
    "USER_EMAIL": ""
}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_FILE, "r") as f:
        cfg = json.load(f)

    cfg.setdefault("SPECIAL_ROUTES", {})
    cfg.setdefault("FSHUB_API_KEY", "")
    cfg.setdefault("USER_EMAIL", "")
    return cfg

config = load_config()

def generate_api_key():
    return secrets.token_urlsafe(24)

def open_cpdlc_window():
    win = tk.Toplevel(root)
    win.title("CPDLC Settings")
    win.geometry("350x180")
    win.attributes("-topmost", True)

    frame = ttk.Frame(win, padding=15)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="HOPPIE Code").pack(anchor="w")
    hoppie_var = tk.StringVar(value=config.get("HOPPIE_CODE", ""))
    ttk.Entry(frame, textvariable=hoppie_var).pack(fill="x")

    ttk.Label(frame, text="Callsign").pack(anchor="w", pady=(10, 0))
    tanker_var = tk.StringVar(value=config.get("Callsign to send CPDLC", ""))
    ttk.Entry(frame, textvariable=tanker_var).pack(fill="x")

    def save():
        config["HOPPIE_CODE"] = hoppie_var.get().upper().strip()
        config["Callsign to send CPDLC"] = tanker_var.get().upper().strip()
        save_config(config)
        win.destroy()

    ttk.Button(frame, text="Save", command=save).pack(pady=15)

def open_special_route_window():
    win = tk.Toplevel(root)
    win.title("Special Aircraft Route")
    win.geometry("450x450")
    win.attributes("-topmost", True)

    frame = ttk.Frame(win, padding=15)
    frame.pack(fill="both", expand=True)

    clear_var = tk.BooleanVar(value=False)

    def clear_routes():
        if clear_var.get():
            if messagebox.askyesno("Clear Routes", "Delete ALL special routes?"):
                config["SPECIAL_ROUTES"] = {}
                save_config(config)
            else:
                clear_var.set(False)

    ttk.Checkbutton(
        frame,
        text="Clear all existing special routes",
        variable=clear_var,
        command=clear_routes
    ).pack(anchor="w", pady=(0, 10))

    callsign_var = tk.StringVar()
    dep_var = tk.StringVar()
    arr_var = tk.StringVar()
    fl_var = tk.StringVar(value="300")
    route_var = tk.StringVar()

    def field(label, var):
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Entry(frame, textvariable=var).pack(fill="x", pady=(0, 8))

    field("Callsign", callsign_var)
    field("Departure ICAO", dep_var)
    field("Arrival ICAO", arr_var)
    field("Flight Level", fl_var)
    field("Route", route_var)

    def save():
        callsign = callsign_var.get().upper().strip()
        dep = dep_var.get().upper().strip()
        arr = arr_var.get().upper().strip()
        route = route_var.get().upper().strip()
        fl = fl_var.get().replace("FL", "").strip()

        if not callsign:
            messagebox.showerror("Error", "Callsign cannot be empty")
            return

        if len(dep) != 4 or not dep.isalpha():
            messagebox.showerror("Error", "Departure ICAO must be 4 letters")
            return

        if len(arr) != 4 or not arr.isalpha():
            messagebox.showerror("Error", "Arrival ICAO must be 4 letters")
            return

        if not route:
            messagebox.showerror("Error", "Route cannot be empty")
            return

        if not fl.isdigit():
            messagebox.showerror("Error", "Flight level must be numeric")
            return

        config["SPECIAL_ROUTES"][callsign] = {
            "dep": dep,
            "arr": arr,
            "route": route,
            "fl": f"FL{fl}"
        }

        save_config(config)
        win.destroy()

    ttk.Button(frame, text="Save Route", command=save).pack(pady=15)

def open_settings():
    win = tk.Toplevel(root)
    win.title("Settings")
    win.geometry("420x650")
    win.attributes("-topmost", True)
    win.protocol("WM_DELETE_WINDOW", win.destroy)

    frame = ttk.Frame(win, padding=15)
    frame.pack(fill="both", expand=True)

    vars_dict = {}

    def add(label, key):
        ttk.Label(frame, text=label).pack(anchor="w")
        var = tk.StringVar(value=str(config.get(key, "")))
        ttk.Entry(frame, textvariable=var).pack(fill="x")
        vars_dict[key] = var

    ssc_var = tk.BooleanVar(value=config.get("Using SSC App", True))
    cpdlc_var = tk.BooleanVar(value=config.get("CPDLC_Test", False))

    ttk.Checkbutton(frame, text="Using SSC App", variable=ssc_var).pack(anchor="w")

    ttk.Checkbutton(
        frame,
        text="Use CPDLC",
        variable=cpdlc_var,
        command=lambda: open_cpdlc_window() if cpdlc_var.get() else None
    ).pack(anchor="w")

    ttk.Button(frame, text="Add Special Aircraft Route",
               command=open_special_route_window).pack(anchor="w", pady=5)

    vars_dict["Using SSC App"] = ssc_var
    vars_dict["CPDLC_Test"] = cpdlc_var

    add("SSC Server", "SSC Server")
    add("SSC URL", "SSC_URL")
    add("JoinFS whazzup.txt path", "JoinFS whazzup.txt path")
    add("Update Interval", "UPDATE_INTERVAL")
    add("Assume Delay", "ASSUME_DELAY")
    add("EuroScope IP", "EUROSCOPE_IP")
    add("EuroScope Port", "EUROSCOPE_PORT")

    email_var = tk.StringVar(value=config.get("USER_EMAIL", ""))
    ttk.Label(frame, text="User Email").pack(anchor="w")
    ttk.Entry(frame, textvariable=email_var).pack(fill="x", pady=(0, 10))
    vars_dict["USER_EMAIL"] = email_var

    ttk.Label(frame, text="FSHub API Key").pack(anchor="w")
    fshub_var = tk.StringVar(value=config.get("FSHUB_API_KEY", ""))

    key_frame = ttk.Frame(frame)
    key_frame.pack(fill="x", pady=(0, 10))

    ttk.Entry(key_frame, textvariable=fshub_var).pack(side="left", fill="x", expand=True)

    def gen_key():
        email = email_var.get().strip().lower()

        if not email:
            messagebox.showerror("Error", "Enter an email first")
            return

        try:
            ip = requests.get("https://api.ipify.org", timeout=5).text.strip()

            SERVER = "https://app.vtacraf.uk/register"

            payload = {
                "email": email,
                "ip": ip
            }

            r = requests.post(SERVER, json=payload, timeout=10)

            if r.status_code != 200:
                messagebox.showerror("Server Error", r.text)
                return

            data = r.json()

            api_key = data.get("api_key", "")

            fshub_var.set(api_key)

            messagebox.showinfo(
                "Success",
                f"API key assigned:\n\n{api_key}"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))
    ttk.Button(key_frame, text="Generate", command=gen_key).pack(side="right")

    vars_dict["FSHUB_API_KEY"] = fshub_var

    def save():
        for k, v in vars_dict.items():
            config[k] = v.get()

        config["UPDATE_INTERVAL"] = int(config.get("UPDATE_INTERVAL", 1))
        config["ASSUME_DELAY"] = int(config.get("ASSUME_DELAY", 5))
        config["EUROSCOPE_PORT"] = int(config.get("EUROSCOPE_PORT", 6809))

        save_config(config)
        win.destroy()

    ttk.Button(frame, text="Save", command=save).pack(pady=20)

def create_settings_button(parent):
    return tk.Button(
        parent,
        text="☰",
        font=("Arial", 20),
        command=open_settings
    )

def launch():
    global root

    root = tk.Tk()
    root.geometry("60x60+100+100")
    root.overrideredirect(False)
    root.attributes("-topmost", True)

    btn = create_settings_button(root)
    btn.pack(expand=True, fill="both")

    root.mainloop()


if __name__ == "__main__":
    launch()
