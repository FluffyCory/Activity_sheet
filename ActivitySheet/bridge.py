"""
Automatické přihlášení do warehouse přes UI Automation (bez myši).

Najde v okně Activity Sheet iframe s warehouse, zmáčkne „Start a new activity“,
vloží kartu (accessKey), počká na odemčení pole s kódem práce (activityBarcode),
vloží kód a přečte toast. Výsledek: ok / error / unconfirmed – úspěch se nikdy
nedomýšlí.
"""
import os
import queue
import threading
import time
import traceback
import unicodedata

IS_WIN = os.name == "nt"
log = print          # nahradí hlavní program


def _log(msg):
    log(msg)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# ================================================================ warehouse ===
class Fail(Exception):
    """Ukončí operaci s daným výsledkem (error / unconfirmed)."""

    def __init__(self, result, message, step, texts=None):
        super().__init__(message)
        self.result, self.message, self.step, self.texts = result, message, step, texts or []


class WarehouseDriver:
    """Ovládání warehouse přes UI Automation. Běží jen v jednom vlákně (worker)."""

    POLL = 0.12

    def __init__(self, cfg):
        import uiautomation as auto
        self.auto = auto
        self.cfg = cfg
        self.on_step = None          # callback pro živý průběh (Worker)
        auto.SetGlobalSearchTimeout(1)

    def at(self, step):
        """Nahlásí aktuální krok (pro okno Activity Sheet) a vrátí ho."""
        if self.on_step:
            try:
                self.on_step(step)
            except Exception:
                pass
        return step

    # ---------------------------------------------------------- hledání ---
    def find_warehouse(self):
        """Najde dokument warehouse uvnitř iframu Activity Sheet. Vrací (okno, dokument)."""
        auto = self.auto
        fg = auto.GetForegroundWindow()
        wins = [w for w in auto.GetRootControl().GetChildren() if w.ClassName == "Chrome_WidgetWin_1"]
        wins.sort(key=lambda w: w.NativeWindowHandle != fg)       # okno v popředí první
        for w in wins:
            frame = w.Control(AutomationId=self.cfg["iframe_id"], ControlType=auto.ControlType.DocumentControl,
                              searchDepth=40)
            if not frame.Exists(0.3, 0.1):
                continue
            doc = frame.DocumentControl(searchDepth=2)
            if doc.Exists(0.5, 0.1):
                return w, doc
            return w, frame
        return None, None

    def field(self, doc, auto_id):
        return doc.EditControl(AutomationId=auto_id, searchDepth=40)

    def start_button(self, doc):
        return doc.ButtonControl(Name=self.cfg["start_button"], searchDepth=40)

    def texts(self, doc):
        """Všechny neprázdné texty v dokumentu warehouse (pro chytání toastů)."""
        out = set()
        try:
            for c, _ in self.auto.WalkControl(doc, maxDepth=40):
                if c.ControlTypeName in ("EditControl", "DocumentControl"):
                    continue
                n = (c.Name or "").strip()
                if n and len(n) < 300:
                    out.add(n)
        except Exception:
            pass
        return out

    def count_name(self, doc, name):
        n = 0
        try:
            for c, _ in self.auto.WalkControl(doc, maxDepth=40):
                if (c.Name or "").strip() == name:
                    n += 1
        except Exception:
            pass
        return n

    def classify(self, new_texts):
        ok = err = None
        for t in new_texts:
            nt = norm(t)
            if err is None and any(w in nt for w in self.cfg["error_words"]):
                err = t
            if ok is None and any(w in nt for w in self.cfg["success_words"]):
                ok = t
        return ok, err

    # ---------------------------------------------------------- psaní ---
    def press_enter(self):
        """Hlavní Enter (ne numerický) – stejně jako ho posílá čtečka."""
        auto = self.auto
        kf = auto.KeyboardEventFlag
        auto.SendInput(auto.KeyboardInput(0x0D, 0x1C, kf.KeyDown),
                       auto.KeyboardInput(0x0D, 0x1C, kf.KeyUp))
        time.sleep(0.05)

    def activate(self, win):
        """Okno Activity Sheet do popředí (i z minimalizace)."""
        try:
            import ctypes
            h = win.NativeWindowHandle
            if not h:
                return
            if ctypes.windll.user32.IsIconic(h):
                ctypes.windll.user32.ShowWindow(h, 9)          # SW_RESTORE
            if self.auto.GetForegroundWindow() != h:
                self.auto.SetForegroundWindow(h)
                time.sleep(0.1)
        except Exception:
            pass

    def focus(self, win, edit, step, need_system_focus):
        """Zaměří pole. Vrací True, když má pole i systémový fokus."""
        if need_system_focus:
            self.activate(win)
        for _ in range(3):
            try:
                edit.SetFocus()
            except Exception:
                pass
            time.sleep(0.1)
            if edit.HasKeyboardFocus:
                return True
        if need_system_focus:
            raise Fail("error", "Nepodařilo se zaměřit pole ve warehouse (je okno prohlížeče vidět?).", step)
        return False

    def type_into(self, win, edit, text, step):
        mode = self.cfg.get("input_mode", "uia")
        if mode == "keyboard":
            self._type_keyboard(win, edit, text, step)
        else:
            self._type_uia(win, edit, text, step)

    def _clear(self, vp, step):
        if (vp.Value or "") != "":
            try:
                vp.SetValue("")
            except Exception:
                pass
            time.sleep(0.05)
            if (vp.Value or "") != "":
                raise Fail("error", "Pole ve warehouse není prázdné a nejde vymazat.", step)

    def _verify(self, vp, text, step, wait=1.5):
        deadline = time.time() + wait
        while (vp.Value or "") != text and time.time() < deadline:
            time.sleep(0.05)
        if (vp.Value or "") != text:
            raise Fail("error", f"Do pole se nezapsalo správně (je tam „{vp.Value}“). Nic jsem neodeslal.", step)

    def _type_uia(self, win, edit, text, step):
        """Hodnota se vloží přes UI Automation (žádné psaní znaků), Enter přes klávesnici.
        Okno Activity Sheet zůstane v popředí – výsledek musí být ve warehouse vidět."""
        self.focus(win, edit, step, need_system_focus=True)
        vp = edit.GetValuePattern()
        self._clear(vp, step)
        try:
            vp.SetValue(text)
        except Exception as e:
            raise Fail("error", f"Hodnotu nejde vložit přes UI Automation ({e}). "
                                "Zkus v config.json \"input_mode\": \"keyboard\".", step)
        self._verify(vp, text, step)
        time.sleep(0.1)                        # nechat stránku zpracovat změnu
        if (vp.Value or "") != text:           # stránka hodnotu vrátila → nepřijala ji
            raise Fail("error", "Warehouse vloženou hodnotu nepřijal (pole se vrátilo). "
                                "Zkus v config.json \"input_mode\": \"keyboard\".", step)
        if not edit.HasKeyboardFocus:
            raise Fail("error", "Pole ztratilo fokus těsně před potvrzením – nic jsem neodeslal.", step)
        self.press_enter()

    def _type_keyboard(self, win, edit, text, step):
        """Záloha: simulovaná klávesnice (Unicode znaky + Enter). Během psaní se nesmí klikat."""
        auto = self.auto
        self.focus(win, edit, step, need_system_focus=True)
        vp = edit.GetValuePattern()
        self._clear(vp, step)
        for ch in text:
            if not edit.HasKeyboardFocus:
                raise Fail("error", "Během psaní se fokus přesunul jinam (někdo sáhl na klávesnici/myš?). "
                                    "Zkontroluj warehouse.", step)
            auto.SendUnicodeChar(ch)
            time.sleep(0.015)
        self._verify(vp, text, step)
        self.press_enter()

    def job_ready(self, job_edit):
        try:
            if not (job_edit.Exists(0, 0) and job_edit.IsEnabled and job_edit.IsKeyboardFocusable):
                return False
        except Exception:
            return False
        if self.cfg.get("input_mode", "uia") == "keyboard":
            try:
                job_edit.SetFocus()
            except Exception:
                pass
            time.sleep(0.1)
            return bool(job_edit.HasKeyboardFocus)
        return True

    # ------------------------------------------------------------ zkouška ---
    def probe(self, card):
        """Zkouška vstupu: vloží (neplatnou) kartu a vypíše, co warehouse udělal. Kód práce nevkládá."""
        cfg = self.cfg
        out = []
        win, doc = self.find_warehouse()
        if not doc:
            return ["✗ Nenašel jsem Activity Sheet s warehouse (otevři v něm nějakou činnost)."]
        card_edit = self.field(doc, cfg["card_field"])
        if not card_edit.Exists(0, 0):
            btn = self.start_button(doc)
            if not btn.Exists(2, 0.2):
                return ["✗ Ve warehouse není tlačítko Start ani formulář."]
            btn.GetInvokePattern().Invoke()
            if not card_edit.Exists(cfg["timeout_form"], self.POLL):
                return ["✗ Formulář se neotevřel."]
        out.append("✓ formulář otevřený")
        job_edit = self.field(doc, cfg["job_field"])
        out.append(f"  pole kódu práce před kartou: {'odemčené' if self.job_ready(job_edit) else 'zamčené'}")
        before = self.texts(doc)
        try:
            self.type_into(win, card_edit, card, "zkouška")
        except Fail as f:
            out.append(f"✗ {f.message}")
            return out
        out.append(f"✓ karta vložena a ověřena v poli, Enter odeslán (režim {cfg.get('input_mode', 'uia')}), "
                   "okno vráceno zpět")
        seen, unlocked = set(), False
        deadline = time.time() + cfg["timeout_job_unlock"]
        while time.time() < deadline:
            seen |= self.texts(doc) - before
            if self.job_ready(job_edit):
                unlocked = True
            time.sleep(self.POLL)
        try:
            val = self.field(doc, cfg["card_field"]).GetValuePattern().Value
        except Exception:
            val = "?"
        out.append(f"  pole karty teď obsahuje: „{val}“")
        out.append(f"  pole kódu práce po kartě: {'ODEMČENÉ' if unlocked else 'zamčené'}")
        out.append("  nové texty ve warehouse: " + (" | ".join(sorted(seen)) if seen else "(žádné)"))
        ok, err = self.classify(seen)
        if seen:
            out.append("✓ warehouse na Enter zareagoval → tento režim funguje"
                       + (f" (poznal bych chybu: „{err}“)" if err else " – ale hlášku jsem nepoznal jako chybu, "
                          "pošli ji, doplním slova"))
        elif unlocked:
            out.append("✓ warehouse kartu přijal (pole se odemklo) – POZOR, karta byla asi platná")
        else:
            out.append("? žádná reakce – Enter asi nedošel. Zkus to znovu s --rezim keyboard pro srovnání.")
        out.append(f"  placeholder „{cfg.get('placeholder', 'Select...')}“ viditelný přes UIA: "
                   f"{self.count_name(doc, cfg.get('placeholder', 'Select...'))}×")
        return out

    # ---------------------------------------------------------- postup ---
    def assign(self, card, job):
        """Celé přihlášení. Na konci (úspěch i chyba) nechá okno Activity Sheet v popředí."""
        self._win = None
        try:
            return self._assign(card, job)
        finally:
            if self._win is not None:
                self.activate(self._win)

    def _assign(self, card, job):
        cfg = self.cfg
        step = self.at("hledám warehouse")
        win, doc = None, None
        deadline = time.time() + cfg["timeout_start"]
        while time.time() < deadline:
            win, doc = self.find_warehouse()
            if doc and (self.field(doc, cfg["card_field"]).Exists(0, 0)
                        or self.start_button(doc).Exists(0, 0)):
                break
            time.sleep(0.4)
        else:
            if not win:
                raise Fail("error", "Nenašel jsem otevřené okno Activity Sheet s warehouse. "
                                    "Je otevřené v Edge a je zapnutá přístupnost (--force-renderer-accessibility)?", step)
            raise Fail("error", f"Warehouse se nenačetl, nebo v něm chybí tlačítko „{cfg['start_button']}“. "
                                "Možná je potřeba se do warehouse přihlásit.", step)

        self._win = win
        # 1) formulář – pokud už otevřený není, zmáčknout Start
        step = self.at("otevírám formulář")
        card_edit = self.field(doc, cfg["card_field"])
        if not card_edit.Exists(0, 0):
            btn = self.start_button(doc)
            try:
                btn.GetInvokePattern().Invoke()
            except Exception as e:
                raise Fail("error", f"Tlačítko „{cfg['start_button']}“ nejde zmáčknout ({e}).", step)
            if not card_edit.Exists(cfg["timeout_form"], self.POLL):
                raise Fail("error", "Po zmáčknutí Start se neobjevilo pole pro kartu "
                                    f"(id „{cfg['card_field']}“). Nezměnil se warehouse?", step)

        # 2) karta
        step = self.at("zadávám kartu")
        before = self.texts(doc)
        self.type_into(win, card_edit, card, step)

        # 3) kód práce – opakovaně zkoušet zapsat, dokud se to nepovede (= karta byla přijata)
        step = self.at("ověřuji kartu")
        job_edit = self.field(doc, cfg["job_field"])
        seen = set()
        time.sleep(0.5)
        deadline = time.time() + cfg["timeout_job_unlock"]
        last_problem = ""
        while True:
            new = self.texts(doc) - before
            seen |= new
            _, err = self.classify(new)
            if err:
                raise Fail("error", err, step, sorted(seen))
            if job_edit.Exists(0, 0) and job_edit.IsEnabled:
                try:
                    step = self.at("zadávám kód práce")
                    self.type_into(win, job_edit, job, step)
                    break
                except Fail as f:
                    last_problem = f.message
                    step = self.at("ověřuji kartu")
            if time.time() >= deadline:
                raise Fail("error", "Kód práce nejde zapsat – karta asi nebyla přijata."
                           + (f" ({last_problem})" if last_problem else ""), step, sorted(seen))
            time.sleep(0.3)

        # 4) zmáčknout Confirm (bez fokusu). Výsledek už pomocník neověřuje – ukazuje ho warehouse.
        step = self.at("potvrzuji (Confirm)")
        before |= seen
        btn = doc.ButtonControl(Name=cfg["confirm_button"], searchDepth=40)
        seen = set()
        deadline = time.time() + cfg["timeout_confirm"]
        time.sleep(0.3)
        while True:
            new = self.texts(doc) - before
            seen |= new
            _, err = self.classify(new)
            if err:
                raise Fail("error", err, step, sorted(seen))
            if btn.Exists(0, 0) and btn.IsEnabled:
                break
            if time.time() >= deadline:
                raise Fail("error", f"Po kódu práce se neobjevilo tlačítko „{cfg['confirm_button']}“ – "
                                    "kód práce asi nebyl přijat. Nic jsem nepotvrdil.", step, sorted(seen))
            time.sleep(self.POLL)
        try:
            btn.GetInvokePattern().Invoke()
        except Exception as e:
            raise Fail("error", f"Tlačítko „{cfg['confirm_button']}“ nejde zmáčknout ({e}).", step, sorted(seen))
        return {"result": "ok", "message": "Odesláno – výsledek ukazuje warehouse.", "step": "hotovo",
                "texts": []}


# =================================================================== worker ===
class Worker:
    """Jedno vlákno s inicializovaným UI Automation; operace jdou postupně."""

    def __init__(self, cfg, driver_factory=WarehouseDriver):
        self.cfg = cfg
        self.jobs = queue.Queue()
        self.busy = threading.Lock()
        self.driver_factory = driver_factory
        self.ready = threading.Event()
        self.init_error = None
        self.current_step = None
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(15)

    def _run(self):
        init = None
        try:
            if IS_WIN:
                import uiautomation as auto
                init = auto.UIAutomationInitializerInThread()
            driver = self.driver_factory(self.cfg)
            try:
                driver.on_step = lambda st: setattr(self, "current_step", st)
            except Exception:
                pass
        except Exception as e:
            self.init_error = f"{e}"
            _log("UI Automation nejde spustit:\n" + traceback.format_exc())
            self.ready.set()
            return
        self.ready.set()
        while True:
            card, job, box, done = self.jobs.get()
            self.current_step = "start"
            t0 = time.time()
            try:
                res = driver.assign(card, job)
            except Fail as f:
                res = {"result": f.result, "message": f.message, "step": f.step, "texts": f.texts}
            except Exception as e:
                _log("neočekávaná chyba:\n" + traceback.format_exc())
                res = {"result": "unconfirmed", "message": f"Neočekávaná chyba pomocníka: {e}. "
                                                           "Zkontroluj warehouse.", "step": "?", "texts": []}
            res["ms"] = int((time.time() - t0) * 1000)
            self.current_step = None
            box.append(res)
            done.set()
            _ = init  # drží COM inicializaci po celou dobu vlákna

    def assign(self, card, job, timeout=90):
        if not self.busy.acquire(blocking=False):
            return {"result": "error", "message": "Pomocník právě zpracovává jinou operaci.", "step": "fronta",
                    "texts": [], "busy": True}
        try:
            if self.init_error:
                return {"result": "error", "message": f"UI Automation nefunguje: {self.init_error}",
                        "step": "start", "texts": []}
            box, done = [], threading.Event()
            self.jobs.put((card, job, box, done))
            if not done.wait(timeout):
                return {"result": "unconfirmed", "message": "Operace trvá příliš dlouho. Zkontroluj warehouse.",
                        "step": "timeout", "texts": []}
            return box[0]
        finally:
            self.busy.release()


