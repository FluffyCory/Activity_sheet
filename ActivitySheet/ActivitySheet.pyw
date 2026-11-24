#!/usr/bin/env python3
"""
Activity Sheet 2.1 – jeden program pro všechny.

  • lokální web s činnostmi (jen 127.0.0.1 – do sítě není vidět)
  • ikonka v trayi: otevřít, správa, nastavení, aktualizace, spouštění po přihlášení
  • dvě sady dat: serverová kopie (stahuje se ze serveru) a vlastní lokální seznam;
    co se zobrazuje, určuje přepínač „zdroj“ v nastavení
  • správa: lokální seznam volně, serverový jen po přihlášení správce (heslo ověřuje server)
  • režim „auto“: operátor pípne kartu a pomocník vyplní warehouse sám (UI Automation)
    režim „basic“: čárový kód + warehouse jako dřív

Bez instalace: Python ze systému + čistě Pythonové knihovny v libs/ (žádné .exe ani .dll).
Nastavení: config.json   Log: activitysheet.log   Operace: operace.log
"""
import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "libs"))
sys.path.insert(0, HERE)

import bridge  # noqa: E402

APP = "Activity Sheet"
VERSION = "2.1.1"
IS_WIN = os.name == "nt"
WEB = os.path.join(HERE, "web")
STATIC = os.path.join(WEB, "static")
DATA_DIR = os.path.join(HERE, "data")
SERVER_FILE = os.path.join(DATA_DIR, "server.json")          # kopie ze serveru
LOCAL_FILE = os.path.join(DATA_DIR, "lokalni.json")           # vlastní seznam tohoto PC
LEGACY_FILE = os.path.join(DATA_DIR, "Activity_MasterData.json")
BACKUP_DIR = os.path.join(DATA_DIR, "zalohy")
CONFIG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "activitysheet.log")
PORT_FILE = os.path.join(HERE, "activitysheet.port")          # port, na kterém program právě běží
FALLBACK_PORT = 28000
OPS_PATH = os.path.join(HERE, "operace.log")

DEFAULTS = {
    "mode": "basic",                 # "auto" = pípnutí karty, "basic" = čárový kód + warehouse
    "source": "server",              # "server" = seznam ze serveru, "local" = vlastní seznam
    "server_url": "https://example.com",                       # adresa tvého serveru se seznamem
    "warehouse_url": "https://warehouse.example.com/productivity/overview",  # stránka warehouse v iframu
    "data_refresh_min": 10,
    "autostart": False,              # spouštět po přihlášení do Windows (zástupce ve Po spuštění)
    "open_on_start": True,           # po spuštění otevřít okno
    "keep_running": True,            # zavřením okna program neukončit (zůstane v trayi)
    "browser": "",                   # "" = podle režimu, "app" = vlastní okno Edge, "browser" = výchozí prohlížeč
    "input_mode": "uia",             # auto režim: "uia" | "keyboard"
    "port": 8080,                    # když je obsazený, použije se 28000 (80 = adresa bez čísla)
    "hostname": "activity-sheet.localhost",   # *.localhost vede vždy na tento PC (bez hosts, bez DNS)
    # warehouse (UI Automation) – viz bridge.py
    "iframe_id": "modal-iframe",
    "start_button": "Start a new activity",
    "card_field": "accessKey",
    "job_field": "activityBarcode",
    "confirm_button": "Confirm",
    "placeholder": "Select...",
    "timeout_start": 20,
    "timeout_form": 8,
    "timeout_job_unlock": 8,
    "timeout_confirm": 8,
    "timeout_result": 8,
    "success_words": ["success", "successfully", "started", "created", "uspesn", "zahajen", "spusten"],
    "error_words": ["error", "invalid", "not found", "failed", "unknown", "already", "not allowed",
                    "cannot", "can't", "chyba", "neplatn", "nenalezen", "nelze", "neexist"],
}

_LOG_LOCK = threading.Lock()
_CONSOLE = "--debug" in sys.argv


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    with _LOG_LOCK:
        if _CONSOLE:
            print(line, flush=True)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


bridge.log = log


def log_op(record):
    record = {"cas": f"{datetime.now():%Y-%m-%d %H:%M:%S}", **record}
    with _LOG_LOCK:
        try:
            with open(OPS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass


def plural(n, one, few, many):
    return one if n == 1 else few if 2 <= n <= 4 else many


def mask(card):
    card = str(card)
    return ("…" + card[-4:]) if len(card) > 4 else card


# ================================================================ nastavení ===
_CFG_LOCK = threading.Lock()


def load_config():
    cfg = dict(DEFAULTS)
    stored = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                stored = json.load(f)
        except Exception as e:
            log(f"chyba v config.json ({e}) – používám výchozí nastavení")
    # převod ze starší verze 2.0
    if "server_url" not in stored and stored.get("data_url"):
        stored["server_url"] = stored["data_url"].split("/api/")[0]
        if not stored["data_url"].strip():
            stored["source"] = "local"
    for old in ("data_url", "publish_url", "publish_token", "admin", "admin_pin"):
        stored.pop(old, None)
    # 2.1: výchozí port 80 bývá obsazený (IIS, Skype…) → přechod na 8080
    if stored.get("port") == 80 and not stored.get("_port_8080"):
        stored["port"] = 8080
    stored["_port_8080"] = True
    cfg.update(stored)
    save_config(cfg)
    return cfg


def save_config(cfg):
    with _CFG_LOCK:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)


def effective_browser(cfg):
    b = cfg.get("browser") or ""
    if b in ("app", "browser"):
        return b
    return "app" if cfg.get("mode") == "auto" else "browser"


# ======================================================================= data ===
_DATA_LOCK = threading.Lock()
SYNC = {"last_ok": None, "last_try": None, "error": None, "changed_at": None}
CHANGE = {"reason": None, "at": None, "detail": None}     # proč se naposledy změnil zobrazovaný seznam


def mark_change(reason, detail=None):
    CHANGE.update(reason=reason, at=datetime.now().isoformat(timespec="seconds"), detail=detail)


def migrate_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SERVER_FILE) and os.path.exists(LEGACY_FILE):
        shutil.copyfile(LEGACY_FILE, SERVER_FILE)


def active_file(cfg):
    if cfg.get("source") == "local" and os.path.exists(LOCAL_FILE):
        return LOCAL_FILE
    return SERVER_FILE


def read_bytes(path):
    with _DATA_LOCK, open(path, "rb") as f:
        return f.read()


def read_json(path):
    try:
        return json.loads(read_bytes(path).decode("utf-8"))
    except Exception:
        return None


def data_version(cfg):
    b = read_bytes(active_file(cfg))
    v = {"mtime_ns": int(hashlib.sha1(b).hexdigest()[:12], 16), "size": len(b),
         "source": cfg.get("source"), "change": dict(CHANGE)}
    if cfg.get("source") == "local":
        v["local_updates"] = len(local_updates())
    return v


def summary(path):
    d = read_json(path) if os.path.exists(path) else None
    if not d:
        return None
    ver = d.get("_verze") or {}
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    except OSError:
        mtime = None
    return {"sections": len(d.get("sekce", [])),
            "count": sum(len(s.get("cinnosti", [])) for s in d.get("sekce", [])),
            "version": ver.get("cislo"), "version_time": ver.get("cas"), "saved": mtime}


def write_json(path, data, backup=True):
    os.makedirs(DATA_DIR, exist_ok=True)
    with _DATA_LOCK:
        if backup and os.path.exists(path):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = os.path.splitext(os.path.basename(path))[0]
            shutil.copyfile(path, os.path.join(BACKUP_DIR, f"{name}-{stamp}.json"))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    if backup and os.path.isdir(BACKUP_DIR):
        files = sorted(x for x in os.listdir(BACKUP_DIR) if x.endswith(".json"))
        for old in files[:-40]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except OSError:
                pass


def validate_data(data):
    """Vrací (čistá_data, chyby). Zachová i klíče, které správa nezná."""
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("sekce"), list):
        return None, ["Neplatný formát: chybí seznam sekcí."]
    out = []
    for si, sek in enumerate(data["sekce"]):
        if not isinstance(sek, dict):
            errors.append(f"Sekce č. {si + 1} má neplatný formát.")
            continue
        name = str(sek.get("nazev", "")).strip()
        if not name:
            errors.append(f"Sekce č. {si + 1} nemá název.")
        cinnosti = []
        for ci, c in enumerate(sek.get("cinnosti") or []):
            if not isinstance(c, dict):
                errors.append(f"{name or 'Sekce'}: položka č. {ci + 1} má neplatný formát.")
                continue
            cid = str(c.get("id", "")).strip()
            cname = str(c.get("nazev", "")).strip()
            where = f"{name or 'Sekce ' + str(si + 1)} → řádek {ci + 1}"
            if not cid:
                errors.append(f"{where}: chybí kód.")
            elif len(cid) > 64 or any(ord(ch) < 32 or ord(ch) > 126 for ch in cid):
                errors.append(f"{where}: kód „{cid}“ obsahuje znaky, které čtečka nenačte (jen ASCII).")
            if not cname:
                errors.append(f"{where}: chybí název.")
            cinnosti.append({**c, "id": cid, "nazev": cname})
        out.append({**sek, "nazev": name, "cinnosti": cinnosti})
    return {**data, "sekce": out}, errors


KNOWN_KEY = "_ze_serveru"          # klíče činností ze serveru, které vlastní seznam už „viděl“


def item_key(section, cid):
    return f"{str(section).strip()}|{str(cid).strip()}"


def server_keys(data):
    return {item_key(sk.get("nazev", ""), c.get("id", "")) for sk in (data or {}).get("sekce", [])
            for c in sk.get("cinnosti", [])}


def ensure_local_copy():
    """Při prvním přepnutí na lokální zdroj vznikne vlastní seznam jako kopie serverového."""
    if not os.path.exists(LOCAL_FILE):
        src = read_json(SERVER_FILE) or {"sekce": []}
        src.pop("_verze", None)
        src[KNOWN_KEY] = sorted(server_keys(src))
        write_json(LOCAL_FILE, src, backup=False)
        log("vytvořen vlastní seznam (kopie serverového)")


def local_updates():
    """Činnosti, které na serveru přibyly a vlastní seznam je ještě neviděl ani nemá.
    Co uživatel smazal nebo upravil, se tu neobjeví (klíč je mezi viděnými)."""
    local = read_json(LOCAL_FILE) if os.path.exists(LOCAL_FILE) else None
    server = read_json(SERVER_FILE)
    if not local or not server:
        return []
    known = set(local.get(KNOWN_KEY) or []) or server_keys(local)    # starší soubor bez evidence
    present = server_keys(local)
    out = []
    for sk in server.get("sekce", []):
        for c in sk.get("cinnosti", []):
            k = item_key(sk.get("nazev", ""), c.get("id", ""))
            if k not in known and k not in present:
                out.append({"sekce": sk.get("nazev", ""), "id": c.get("id", ""), "nazev": c.get("nazev", "")})
    return out


def merge_local_updates():
    """Přidá novinky ze serveru na konec odpovídajících sekcí; nic nemaže ani nepřepisuje."""
    local = read_json(LOCAL_FILE)
    server = read_json(SERVER_FILE)
    new = local_updates()
    if not local or not server:
        return 0
    by_name = {str(sk.get("nazev", "")).strip(): sk for sk in local.get("sekce", [])}
    for item in new:
        src_sec = next((sk for sk in server["sekce"] if sk.get("nazev") == item["sekce"]), None)
        src_item = next((c for c in (src_sec or {}).get("cinnosti", []) if c.get("id") == item["id"]), None)
        name = str(item["sekce"]).strip()
        if name not in by_name:
            sec = {k: v for k, v in (src_sec or {}).items() if k != "cinnosti"}
            sec["nazev"] = name
            sec["cinnosti"] = []
            local.setdefault("sekce", []).append(sec)
            by_name[name] = sec
        by_name[name].setdefault("cinnosti", []).append(dict(src_item or {"id": item["id"], "nazev": item["nazev"]}))
    known = set(local.get(KNOWN_KEY) or []) or server_keys(local)
    local[KNOWN_KEY] = sorted(known | server_keys(server))
    write_json(LOCAL_FILE, local)
    mark_change("merge", len(new))
    log(f"vlastní seznam: přidáno {len(new)} novinek ze serveru")
    return len(new)


def http_json(url, body=None, headers=None, timeout=10):
    """GET/POST JSON. Vrací (status, dict). Síťová chyba → (0, {'message': ...})."""
    h = {"User-Agent": f"ActivitySheet/{VERSION}", "Cache-Control": "no-cache"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read(3_000_000).decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read(100_000).decode("utf-8") or "{}")
        except Exception:
            return e.code, {"message": f"Server vrátil chybu {e.code}."}
    except Exception as e:
        why = getattr(e, "reason", e)
        log(f"server {url}: {why}")
        if isinstance(why, (TimeoutError, socket.timeout)) or "timed out" in str(why):
            return 0, {"message": "Server neodpověděl včas. Zkus to za chvíli znovu."}
        return 0, {"message": "Server není dostupný – zkontroluj připojení k síti nebo adresu serveru v Nastavení."}


def server_base(cfg):
    return (cfg.get("server_url") or "").strip().rstrip("/")


def sync_once(cfg, notify=None):
    """Aktualizuje serverovou kopii. Lokální seznam se nikdy nemění."""
    base = server_base(cfg)
    SYNC["last_try"] = datetime.now().isoformat(timespec="seconds")
    if not base:
        SYNC["error"] = "Adresa serveru není nastavená."
        return False
    status, data = http_json(base + "/api/cinnosti", timeout=8)
    if status != 200 or not isinstance(data, dict) or not isinstance(data.get("sekce"), list) or not data["sekce"]:
        SYNC["error"] = data.get("message") if isinstance(data, dict) and data.get("message") else \
            f"Neočekávaná odpověď serveru ({status})."
        log(f"aktualizace ze serveru se nepovedla: {SYNC['error']} – používám uloženou kopii")
        return False
    old = read_json(SERVER_FILE) if os.path.exists(SERVER_FILE) else None
    first = SYNC["last_ok"] is None                    # první úspěšná kontrola od spuštění programu
    SYNC["error"] = None
    SYNC["last_ok"] = SYNC["last_try"]
    if data != old:                                    # porovnává se obsah, ne pořadí klíčů ani formátování
        write_json(SERVER_FILE, data, backup=old is not None)
        SYNC["changed_at"] = SYNC["last_try"]
        n = sum(len(s.get("cinnosti", [])) for s in data["sekce"])
        log(f"serverový seznam aktualizován ({n} činností)")
        if cfg.get("source") == "server":
            mark_change("startup" if first else "server", n)
        if notify and cfg.get("source") == "server" and not first:
            notify("Seznam činností aktualizován", f"{n} činností ze serveru.")
        elif notify and cfg.get("source") == "local":
            pending = len(local_updates())
            if pending:
                notify("Na serveru jsou novinky",
                       f"{pending} {plural(pending, 'nová činnost', 'nové činnosti', 'nových činností')}"
                       " – přidáš je ve Správě nebo v Nastavení.")
    return True


def sync_loop(cfg, notify):
    while True:
        try:
            sync_once(cfg, notify)
        except Exception:
            log("chyba synchronizace:\n" + traceback.format_exc())
        time.sleep(max(1, float(cfg.get("data_refresh_min", 10) or 10)) * 60)


# ===================================================== spouštění po přihlášení ===
def startup_lnk():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                        "Startup", "Activity Sheet.lnk")


def pythonw_path():
    bundled = os.path.join(HERE, "python", "pythonw.exe")     # přenosný Python ve složce programu
    if os.path.exists(bundled):
        return bundled
    exe_dir, exe = os.path.split(sys.executable)
    cand = os.path.join(exe_dir, exe.lower().replace("python", "pythonw", 1))
    return cand if os.path.exists(cand) else sys.executable


def make_lnk(path, args, desc):
    """Zástupce přes COM z Pythonu – žádné VBS ani PowerShell."""
    import comtypes.client
    sh = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
    lnk = sh.CreateShortcut(path)
    lnk.TargetPath = pythonw_path()
    lnk.Arguments = args
    lnk.WorkingDirectory = HERE
    lnk.IconLocation = os.path.join(STATIC, "assets", "favicon", "favicon.ico")
    lnk.Description = desc
    lnk.Save()


def autostart_enabled():
    return IS_WIN and os.path.exists(startup_lnk())


def set_autostart(on):
    if not IS_WIN:
        return False
    path = startup_lnk()
    if on:
        make_lnk(path, f'"{os.path.join(HERE, "ActivitySheet.pyw")}" --autostart', "Activity Sheet")
        log("spouštění po přihlášení zapnuto")
    elif os.path.exists(path):
        os.remove(path)
        log("spouštění po přihlášení vypnuto")
    return autostart_enabled()


def create_desktop_shortcut():
    import comtypes.client
    sh = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
    path = os.path.join(sh.SpecialFolders("Desktop"), "Activity Sheet.lnk")
    make_lnk(path, f'"{os.path.join(HERE, "ActivitySheet.pyw")}"', "Activity Sheet")
    return path


# ===================================================================== okno ===
def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(p):
                return p
    return None


EDGE_PROFILE = os.path.join(HERE, "edge-profil")


def profile_in_use():
    lock = os.path.join(EDGE_PROFILE, "lockfile")
    if not os.path.exists(lock):
        return False
    try:
        os.remove(lock)
        return False
    except OSError:
        return True


# ------------------------------------------------------------------ jedno okno ---
_WIN_LOCK = threading.Lock()
_LAUNCHED_AT = 0.0
WINDOW = {"id": 0, "path": None}          # žádost pro otevřené okno: přejdi na stránku (čte /api/window)


def find_app_window():
    """Okno Activity Sheet v Edge (--app). Okno v režimu aplikace má v titulku jen název stránky."""
    if not IS_WIN:
        return None
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE                  # 64bit handle, ne int
    found = []

    def exe_of(hwnd):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(1024)
            return buf.value.lower() if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
        finally:
            k32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd) and not u32.IsIconic(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "Chrome_WidgetWin_1":
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, title, n + 1)
        t = title.value.lower()
        if "activity sheet" in t and "microsoft" not in t and exe_of(hwnd).endswith("msedge.exe"):
            found.append(hwnd)
            return False
        return True

    try:
        u32.EnumWindows(cb, 0)
    except Exception as e:
        log(f"hledání okna selhalo: {e}")
    return found[0] if found else None


def focus_window(hwnd):
    import ctypes
    u32 = ctypes.windll.user32
    try:
        u32.ShowWindow(hwnd, 9 if u32.IsIconic(hwnd) else 5)      # SW_RESTORE / SW_SHOW
        if not u32.SetForegroundWindow(hwnd):
            # Windows někdy nedovolí převzít popředí – krátký Alt to odblokuje
            u32.keybd_event(0x12, 0, 0, 0)
            u32.keybd_event(0x12, 0, 2, 0)
            u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
    except Exception as e:
        log(f"okno do popředí selhalo: {e}")


def open_window(cfg, url):
    """Otevře Activity Sheet – vždy jen jedno okno. Když už je otevřené, jen ho přenese do popředí
    (a případně přepne na požadovanou stránku). Vrací True, když jde o vlastní okno Edge."""
    global _LAUNCHED_AT
    if effective_browser(cfg) == "app" and IS_WIN:
        edge = find_edge()
        if edge:
            path = "/" + url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else "/"
            with _WIN_LOCK:
                hwnd = find_app_window()
                if hwnd:
                    if path != "/":                          # Správa / Nastavení z traye
                        WINDOW["id"] += 1
                        WINDOW["path"] = path
                    focus_window(hwnd)
                    return True
                if time.time() - _LAUNCHED_AT < 8:          # okno se právě otevírá (dvojklik apod.)
                    return True
                _LAUNCHED_AT = time.time()
            subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={EDGE_PROFILE}",
                              "--force-renderer-accessibility", "--no-first-run",
                              "--no-default-browser-check", "--window-size=1320,940"], close_fds=True)
            return True
        log("Edge nenalezen – otevírám ve výchozím prohlížeči")
    import webbrowser
    webbrowser.open(url)
    return False


def open_path(path):
    if IS_WIN:
        os.startfile(path)  # noqa: S606 – jen vlastní složka / log
    else:
        subprocess.Popen(["xdg-open", path])


# ======================================================================= http ===
class DisabledWorker:
    """Režim basic: automatické přihlášení vypnuté."""

    def __init__(self):
        self.busy = threading.Lock()
        self.init_error = "Automatické přihlášení je vypnuté (běžný režim)."
        self.current_step = None

    def assign(self, card, job):
        return {"result": "error", "message": self.init_error, "step": "start", "texts": []}


class AppState:
    cfg = None
    worker = None
    session = None               # {"token","exp"} – přihlášení správce (jen v paměti)
    port = None                  # port, na kterém server opravdu běží
    notify = None                # funkce z traye pro oznámení
    quit = None
    url = ""


def ensure_worker():
    if AppState.cfg.get("mode") == "auto" and isinstance(AppState.worker, DisabledWorker):
        AppState.worker = bridge.Worker(AppState.cfg)
        log("pomocník pro automatické přihlášení spuštěn")


SETTING_RULES = {
    "mode": ("enum", ("auto", "basic")),
    "source": ("enum", ("server", "local")),
    "server_url": ("url", None),
    "data_refresh_min": ("int", (1, 1440)),
    "open_on_start": ("bool", None),
    "keep_running": ("bool", None),
    "browser": ("enum", ("", "app", "browser")),
    "input_mode": ("enum", ("uia", "keyboard")),
    "port": ("int", (80, 65535)),
    "hostname": ("host", None),
}
RESTART_KEYS = {"port", "hostname"}


def settings_view():
    cfg = AppState.cfg
    return {
        "settings": {k: cfg.get(k) for k in SETTING_RULES},
        "autostart": autostart_enabled(),
        "can_autostart": IS_WIN,
        "effective_browser": effective_browser(cfg),
        "server": summary(SERVER_FILE),
        "local": summary(LOCAL_FILE),
        "local_updates": len(local_updates()),
        "sync": dict(SYNC),
        "version": VERSION,
        "folder": HERE,
        "url": app_url(cfg),
        "logged_in": bool(AppState.session and AppState.session["exp"] > time.time()),
    }


def apply_settings(changes):
    cfg = AppState.cfg
    errors, restart = [], False
    for key, value in changes.items():
        if key == "autostart":
            try:
                set_autostart(bool(value))
            except Exception as e:
                errors.append(f"Spouštění po přihlášení se nepodařilo nastavit: {e}")
            continue
        rule = SETTING_RULES.get(key)
        if not rule:
            continue
        kind, arg = rule
        if kind == "enum" and value not in arg:
            errors.append(f"Neplatná hodnota pro {key}.")
            continue
        if kind == "bool":
            value = bool(value)
        if kind == "int":
            try:
                value = int(value)
            except (TypeError, ValueError):
                errors.append(f"{key}: musí být číslo.")
                continue
            if not arg[0] <= value <= arg[1]:
                errors.append(f"{key}: povolený rozsah {arg[0]}–{arg[1]}.")
                continue
        if kind == "host":
            value = str(value or "").strip().lower()
            if value and not (value == "localhost" or value.endswith(".localhost")):
                errors.append("Adresa musí končit na .localhost (např. activity-sheet.localhost).")
                continue
        if kind == "url":
            value = str(value or "").strip().rstrip("/")
            if value and not value.startswith(("https://", "http://")):
                errors.append("Adresa serveru musí začínat https://")
                continue
        if cfg.get(key) != value:
            if key in RESTART_KEYS:
                restart = True
            if key == "source":
                mark_change("source", value)
            cfg[key] = value
            log(f"nastavení: {key} = {value}")
    if cfg.get("source") == "local":
        ensure_local_copy()
    ensure_worker()
    save_config(cfg)
    return errors, restart


class Handler(BaseHTTPRequestHandler):
    server_version = f"ActivitySheet/{VERSION}"
    pages = {}
    allowed = set()
    allowed_hosts = set()

    def log_message(self, *a):
        pass

    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _host_ok(self):
        return (self.headers.get("Host") or "") in self.allowed_hosts

    def _page(self, name):
        with open(os.path.join(WEB, "templates", name), "rb") as f:
            body = f.read()
        if b"{{WAREHOUSE_URL}}" in body:
            url = str(AppState.cfg.get("warehouse_url") or "")
            if not re.fullmatch(r"https?://[^\s'\"<>\\]+", url):
                url = DEFAULTS["warehouse_url"]
            body = body.replace(b"{{WAREHOUSE_URL}}", url.replace("&", "&amp;").encode("utf-8"))
        self._send(200, body, "text/html; charset=utf-8")

    def _not_found(self):
        try:
            with open(os.path.join(WEB, "templates", "404.html"), "rb") as f:
                body = f.read()
        except OSError:
            body = b"404"
        self._send(404, body, "text/html; charset=utf-8")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            self._send(403, {"error": "forbidden"})
            return
        cfg = AppState.cfg
        w = AppState.worker
        path = self.path.split("?")[0]
        if path == "/":
            self._page("index.html")
        elif path == "/admin":
            self._page("admin.html")
        elif path == "/nastaveni":
            self._page("nastaveni.html")
        elif path == "/api/cinnosti":
            self._send(200, read_bytes(active_file(cfg)))
        elif path == "/api/cinnosti/meta":
            self._send(200, data_version(cfg))
        elif path == "/api/local/updates":
            self._send(200, {"items": local_updates()})
        elif path == "/api/settings":
            self._send(200, settings_view())
        elif path == "/api/admin/info":
            s = AppState.session
            self._send(200, {"source": cfg.get("source"), "server_url": server_base(cfg),
                             "logged_in": bool(s and s["exp"] > time.time()),
                             "session_expires": s["exp"] if s else None,
                             "server": summary(SERVER_FILE), "local": summary(LOCAL_FILE)})
        elif path == "/api/window":
            self._send(200, dict(WINDOW))
        elif path == "/api/bridge/status":
            self._send(200, {"ok": not w.init_error, "error": w.init_error, "busy": w.busy.locked(),
                             "version": VERSION, "mode": cfg.get("mode", "basic"),
                             "input_mode": cfg.get("input_mode", "uia")})
        elif path == "/api/bridge/progress":
            self._send(200, {"busy": w.busy.locked(), "step": w.current_step})
        elif path.startswith("/static/"):
            rel = os.path.normpath(path[len("/static/"):]).lstrip("\\/")
            full = os.path.abspath(os.path.join(STATIC, rel))
            if not full.startswith(os.path.abspath(STATIC) + os.sep) or not os.path.isfile(full):
                self._not_found()
                return
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            with open(full, "rb") as f:
                self._send(200, f.read(), ctype)
        else:
            self._not_found()

    def _body(self, limit=3_000_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("příliš velké")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        if not self._host_ok() or self.headers.get("Origin") not in self.allowed:
            log(f"odmítnuto: Origin {self.headers.get('Origin')!r}, Host {self.headers.get('Host')!r}")
            self._send(403, {"ok": False, "message": "Nepovolený původ požadavku."})
            return
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._send(415, {"ok": False, "message": "Očekávám JSON."})
            return
        try:
            body = self._body()
        except Exception:
            self._send(400, {"ok": False, "message": "Špatný požadavek."})
            return
        route = {
            "/api/bridge/assign": self.post_assign,
            "/api/settings": self.post_settings,
            "/api/settings/sync": self.post_sync,
            "/api/settings/open-folder": self.post_open_folder,
            "/api/admin/login": self.post_login,
            "/api/admin/logout": self.post_logout,
            "/api/admin/data": self.post_data,
            "/api/local/merge": self.post_merge,
        }.get(self.path)
        if not route:
            self._send(404, {"ok": False, "message": "not found"})
            return
        try:
            route(body)
        except Exception as e:
            log("chyba požadavku:\n" + traceback.format_exc())
            self._send(500, {"ok": False, "message": f"Chyba programu: {e}"})

    # ---- automatické přihlášení
    def post_assign(self, body):
        card = str(body.get("card", "")).strip()
        job = str(body.get("job", "")).strip()
        label = str(body.get("label", ""))[:100]
        if not card or not job or len(card) > 64 or len(job) > 64 or any(ord(c) < 32 for c in card + job):
            self._send(400, {"result": "error", "message": "Chybí nebo je neplatná karta / kód práce."})
            return
        log(f"operace: karta {mask(card)}, práce {job} {label}")
        res = AppState.worker.assign(card, job)
        log(f"  → {res['result']}: {res['message']}  ({res.get('step')}, {res.get('ms', '?')} ms)"
            + (f"  texty: {res['texts']}" if res.get("texts") else ""))
        log_op({"karta": mask(card), "prace": job, "nazev": label, **res})
        self._send(200, res)

    # ---- nastavení
    def post_settings(self, body):
        errors, restart = apply_settings(body.get("changes") or {})
        self._send(200 if not errors else 422,
                   {"ok": not errors, "errors": errors, "restart": restart, **settings_view()})

    def post_sync(self, body):
        ok = sync_once(AppState.cfg, AppState.notify)
        self._send(200, {"ok": ok, "message": None if ok else SYNC["error"], **settings_view()})

    def post_open_folder(self, body):
        what = body.get("what")
        open_path(LOG_PATH if what == "log" and os.path.exists(LOG_PATH) else HERE)
        self._send(200, {"ok": True})

    def post_merge(self, body):
        if not os.path.exists(LOCAL_FILE):
            self._send(409, {"ok": False, "message": "Vlastní seznam zatím neexistuje."})
            return
        n = merge_local_updates()
        self._send(200, {"ok": True, "added": n,
                         "message": f"Přidáno {n} {plural(n, 'novinka', 'novinky', 'novinek')} do vlastního seznamu."
                         if n else "Žádné novinky."})

    # ---- správa
    def post_login(self, body):
        password = str(body.get("password", ""))
        status, j = http_json(server_base(AppState.cfg) + "/api/admin/login", {"password": password}, timeout=15)
        if status == 200 and j.get("ok") and j.get("session"):
            AppState.session = {"token": j["session"], "exp": float(j.get("expires") or time.time() + 8 * 3600)}
            log("správa: správce přihlášen")
            self._send(200, {"ok": True, "expires": AppState.session["exp"]})
        else:
            self._send(401 if status in (401, 403) else 502,
                       {"ok": False, "message": j.get("message") or "Přihlášení se nepovedlo."})

    def post_logout(self, body):
        AppState.session = None
        self._send(200, {"ok": True})

    def post_data(self, body):
        cfg = AppState.cfg
        data, errors = validate_data(body.get("data"))
        if errors:
            self._send(422, {"ok": False, "message": "Seznam obsahuje chyby.", "errors": errors})
            return
        count = sum(len(s["cinnosti"]) for s in data["sekce"])
        if cfg.get("source") == "local":
            data.pop("_verze", None)
            existing = read_json(LOCAL_FILE) or {}
            if existing.get(KNOWN_KEY):
                data[KNOWN_KEY] = existing[KNOWN_KEY]
            write_json(LOCAL_FILE, data)
            mark_change("local_edit", count)
            log(f"správa: vlastní seznam uložen ({count} činností)")
            self._send(200, {"ok": True, "message": f"Uloženo do vlastního seznamu ({count} činností).",
                             "count": count})
            return
        s = AppState.session
        if not s or s["exp"] <= time.time():
            self._send(401, {"ok": False, "need_login": True, "message": "Přihlas se jako správce."})
            return
        data.pop("_verze", None)
        status, j = http_json(server_base(cfg) + "/api/cinnosti", {"data": data},
                              {"Authorization": f"Bearer {s['token']}"}, timeout=20)
        if status == 401:
            AppState.session = None
            self._send(401, {"ok": False, "need_login": True, "message": "Přihlášení vypršelo, přihlas se znovu."})
            return
        if status != 200 or not j.get("ok"):
            msg = j.get("message") or f"Server vrátil chybu {status}."
            self._send(502 if status in (0, 500, 502, 503) else status,
                       {"ok": False, "message": msg, "errors": j.get("errors")})
            return
        if j.get("version"):
            data["_verze"] = j["version"]
        write_json(SERVER_FILE, data)
        mark_change("server_edit", count)
        log(f"správa: serverový seznam uložen na server – {j.get('message')}")
        self._send(200, {"ok": True, "message": j.get("message") or "Uloženo na server.", "count": count})


def app_hostname(cfg):
    h = str(cfg.get("hostname") or "").strip().lower()
    # povolené jen *.localhost – jiné jméno by bez úprav systému nevedlo na tento PC
    if h and (h == "localhost" or h.endswith(".localhost")) and all(c.isalnum() or c in ".-" for c in h):
        return h
    return "127.0.0.1"


def running_port(cfg):
    """Port, na kterém program opravdu běží (může se lišit od nastaveného, když byl obsazený)."""
    try:
        with open(PORT_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return int(cfg["port"])


def app_url(cfg, port=None):
    port = int(port or AppState.port or cfg["port"])
    return f"http://{app_hostname(cfg)}{'' if port == 80 else f':{port}'}/"


def start_server(cfg):
    """Zkusí nastavený port; když je obsazený (nebo ho Windows nepovolí), vezme náhradní 28000."""
    ports = [int(cfg["port"])]
    if FALLBACK_PORT not in ports:
        ports.append(FALLBACK_PORT)
    last = None
    for port in ports:
        try:
            srv = make_server(cfg, port)
            if port != ports[0]:
                log(f"port {ports[0]} je obsazený – běžím na {port}")
            AppState.port = port
            with open(PORT_FILE, "w", encoding="utf-8") as f:
                f.write(str(port))
            return srv
        except OSError as e:
            last = e
            log(f"port {port} nejde použít: {e}")
    raise last


def make_server(cfg, port=None):
    port = int(port or cfg["port"])
    names = {"127.0.0.1", "localhost", app_hostname(cfg)}
    hosts = {f"{n}:{port}" for n in names} | ({n for n in names} if port == 80 else set())
    Handler.allowed_hosts = hosts
    Handler.allowed = {f"http://{h}" for h in hosts}
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


# ===================================================================== single ===
_INSTANCE_LOCK = None


def acquire_instance_lock():
    """Pojmenovaný mutex – Windows ho uvolní samy, když proces skončí (i při restartu)."""
    global _INSTANCE_LOCK
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        k32.CreateMutexW.restype = wintypes.HANDLE
        h = k32.CreateMutexW(None, False, "Local\\ActivitySheet_single_instance")
        err = ctypes.get_last_error()
        if not h:
            return True
        if err == 183:
            k32.CloseHandle(h)
            return False
        _INSTANCE_LOCK = h
        return True
    try:
        import fcntl
        f = open(os.path.join(HERE, "activitysheet.lock"), "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _INSTANCE_LOCK = f
        return True
    except BlockingIOError:
        return False
    except Exception:
        return True


# ======================================================================= main ===
def message_box(text):
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP, 0x10)
    else:
        print(text)


def main():
    argv = sys.argv[1:]
    migrate_data()
    cfg = load_config()
    AppState.cfg = cfg
    url = app_url(cfg)                    # upřesní se po spuštění serveru

    if "--zastupce" in argv:
        try:
            print("Zástupce vytvořen:", create_desktop_shortcut())
        except Exception as e:
            print("Zástupce se nepodařilo vytvořit:", e)
        return

    if "--zkouska" in argv:                  # zkouška vstupu s neplatnou kartou
        global _CONSOLE
        _CONSOLE = True
        i = argv.index("--zkouska")
        card = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("--") else "000000000"
        if "--rezim" in argv:
            cfg["input_mode"] = argv[argv.index("--rezim") + 1]
        print(f"Zkouška vstupu – režim „{cfg.get('input_mode', 'uia')}“, karta „{card}“ (má být NEPLATNÁ).")
        print("Activity Sheet musí být otevřený s nějakou činností. Začínám za 3 s.\n")
        time.sleep(3)
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            for line in bridge.WarehouseDriver(cfg).probe(card):
                print(line)
        return

    if not acquire_instance_lock():
        log("už běží – jen otevírám okno")
        open_window(cfg, app_url(cfg, running_port(cfg)))
        return

    log(f"{APP} {VERSION} start (PID {os.getpid()}, režim {cfg['mode']}, zdroj {cfg['source']})")
    if cfg.get("source") == "local":
        ensure_local_copy()
    if not os.path.exists(SERVER_FILE):
        write_json(SERVER_FILE, {"sekce": []}, backup=False)
    AppState.worker = bridge.Worker(cfg) if cfg.get("mode") == "auto" else DisabledWorker()
    if cfg.get("autostart") != autostart_enabled():      # config ↔ skutečný stav zástupce
        cfg["autostart"] = autostart_enabled()
        save_config(cfg)

    try:
        srv = start_server(cfg)
    except OSError as e:
        message_box(f"Program nemůže otevřít port {cfg['port']} ani {FALLBACK_PORT} ({e}). "
                    "Neběží tu ještě starší verze Activity Sheet?")
        return
    url = app_url(cfg)
    AppState.url = url
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"server na {url}")

    stop = threading.Event()

    def quit_app():
        log("ukončeno uživatelem")
        stop.set()

    AppState.quit = quit_app

    def notify(title, text):
        if AppState.notify:
            AppState.notify(title, text)

    threading.Thread(target=sync_loop, args=(cfg, notify), daemon=True).start()

    def open_main(path=""):
        is_app = open_window(cfg, url + path)
        if is_app and not cfg.get("keep_running", True):
            def watch():
                time.sleep(5)
                while profile_in_use():
                    time.sleep(2)
                if not cfg.get("keep_running", True):
                    log("okno zavřeno a „neukončovat“ je vypnuté – konec")
                    stop.set()
                    if AppState.tray_stop:
                        AppState.tray_stop()
            threading.Thread(target=watch, daemon=True).start()

    if "--server" in argv:
        while not stop.is_set():
            stop.wait(1)
        return

    if not ("--autostart" in argv and not cfg.get("open_on_start", True)):
        open_main()

    AppState.tray_stop = None
    try:
        import tray
        t = tray.Tray(
            tooltip=APP,
            icon_path=os.path.join(STATIC, "assets", "favicon", "favicon.ico"),
            menu=lambda: [
                ("Otevřít Activity Sheet", lambda: open_main(), {"default": True}),
                ("Správa činností", lambda: open_main("admin"), {}),
                ("Nastavení…", lambda: open_main("nastaveni"), {}),
                None,
                ("Aktualizovat seznam", lambda: threading.Thread(
                    target=lambda: notify("Activity Sheet", "Seznam je aktuální." if sync_once(cfg, notify)
                                          else f"Server nedostupný: {SYNC['error']}"), daemon=True).start(), {}),
                ("Spouštět po přihlášení", lambda: toggle_autostart(cfg), {"checked": autostart_enabled()}),
                None,
                ("Otevřít log", lambda: open_path(LOG_PATH if os.path.exists(LOG_PATH) else HERE), {}),
                ("Ukončit", quit_app, {}),
            ],
            on_click=lambda: open_main(),
        )
        AppState.notify = t.notify
        AppState.tray_stop = t.stop
        threading.Thread(target=lambda: (stop.wait(), t.stop()), daemon=True).start()
        t.run()                                # blokuje do Ukončit
    except Exception:
        log("tray nejde spustit – program poběží bez ikonky:\n" + traceback.format_exc())
        while not stop.is_set():
            stop.wait(1)


def toggle_autostart(cfg):
    try:
        cfg["autostart"] = set_autostart(not autostart_enabled())
        save_config(cfg)
    except Exception as e:
        log(f"spouštění po přihlášení nejde přepnout: {e}")


AppState.tray_stop = None

if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("pád:\n" + traceback.format_exc())
        raise
    finally:
        os._exit(0)
