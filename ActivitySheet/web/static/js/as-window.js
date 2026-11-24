/* as-window – Activity Sheet má jen jedno okno. Když v trayi zvolíš Správu nebo Nastavení
 * a okno už je otevřené, program ho jen přenese do popředí a tady se přepne stránka.
 * Stránka může nastavit window.asBusy = () => true (probíhá přihlášení, neuložené změny). */
(function () {
  let last = null;
  async function check() {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/window', { cache: 'no-store' });
      if (!r.ok) return;
      const w = await r.json();
      if (last === null) { last = w.id; return; }        // stav při načtení stránky = nic nedělat
      if (w.id === last) return;
      last = w.id;
      if (!w.path || w.path === location.pathname) return;
      if (typeof window.asBusy === 'function' && window.asBusy()) return;
      location.href = w.path;
    } catch (e) { /* program neběží – nevadí */ }
  }
  check();
  setInterval(check, 1000);
  document.addEventListener('visibilitychange', check);
})();
