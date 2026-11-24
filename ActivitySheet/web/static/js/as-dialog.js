/* Activity Sheet – vlastní potvrzovací okno místo systémového confirm().
 *
 *   const ok = await asConfirm({
 *     title: 'Smazat sekci?', message: 'Text…',
 *     confirmText: 'Smazat', cancelText: 'Zrušit',
 *     tone: 'danger' | 'primary' | 'warning', icon: 'trash' | 'swap' | 'question' | 'upload' | 'alert'
 *   });
 *
 * Esc = zrušit, Enter = potvrdit, fokus zůstává uvnitř okna.
 */
(function () {
  const ICONS = {
    trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
    swap: '<path d="M7 7h11l-3-3"/><path d="M17 17H6l3 3"/>',
    question: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17h.01"/>',
    upload: '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M5 20h14"/>',
    alert: '<path d="M12 3l9 16H3z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>'
  };
  const TONES = {
    primary: { c: '#0d6efd', bg: '#e7f0ff' },
    danger: { c: '#c92a2a', bg: '#fff0f0' },
    warning: { c: '#e67700', bg: '#fff4e6' }
  };

  const css = `
  .asd-backdrop { position: fixed; inset: 0; z-index: 20000; display: flex; align-items: center; justify-content: center;
    padding: 16px; background: rgba(15, 23, 42, .45); backdrop-filter: blur(6px); opacity: 0; transition: opacity .18s ease; }
  .asd-backdrop.on { opacity: 1; }
  .asd-card { width: min(440px, 100%); background: #fff; border-radius: 18px; box-shadow: 0 30px 80px rgba(15, 23, 42, .35);
    padding: 24px 24px 20px; font-family: 'Inter', system-ui, sans-serif; color: #212529;
    transform: translateY(14px) scale(.96); opacity: 0; transition: transform .26s cubic-bezier(.2, 1.3, .4, 1), opacity .18s ease; }
  .asd-backdrop.on .asd-card { transform: none; opacity: 1; }
  .asd-head { display: flex; gap: 14px; align-items: flex-start; }
  .asd-icon { width: 46px; height: 46px; flex: 0 0 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center; }
  .asd-backdrop.on .asd-icon { animation: asdPop .4s .08s cubic-bezier(.2, 1.6, .4, 1) both; }
  .asd-title { margin: 2px 0 6px; font-size: 18px; font-weight: 700; letter-spacing: -.2px; }
  .asd-msg { margin: 0; font-size: 14px; line-height: 1.55; color: #495057; white-space: pre-line; }
  .asd-list { margin: 10px 0 0; padding: 10px 12px 10px 28px; border-radius: 10px; background: #f8f9fa; font-size: 13px; color: #343a40; max-height: 180px; overflow: auto; }
  .asd-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 22px; flex-wrap: wrap; }
  .asd-btn { min-height: 44px; padding: 0 18px; border-radius: 11px; font: 600 14px 'Inter', system-ui, sans-serif; cursor: pointer;
    border: 1px solid #ced4da; background: #fff; color: #212529; transition: filter .15s, background .15s, transform .1s; }
  .asd-btn:hover { background: #f1f3f5; }
  .asd-btn:active { transform: scale(.97); }
  .asd-btn.go { border-color: transparent; color: #fff; }
  .asd-btn.go:hover { filter: brightness(.93); }
  .asd-btn:focus-visible { outline: 3px solid rgba(13, 110, 253, .35); outline-offset: 2px; }
  @keyframes asdPop { 0% { transform: scale(.4) rotate(-12deg); } 100% { transform: none; } }
  @media (prefers-reduced-motion: reduce) { .asd-card, .asd-backdrop { transition: none; } .asd-icon { animation: none !important; } }`;

  function ensureStyle() {
    if (document.getElementById('asd-style')) return;
    const st = document.createElement('style');
    st.id = 'asd-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function svg(name, color) {
    return `<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.question}</svg>`;
  }

  window.asConfirm = function (opts = {}) {
    ensureStyle();
    const tone = TONES[opts.tone] || TONES.primary;
    const prevFocus = document.activeElement;
    return new Promise((resolve) => {
      const bd = document.createElement('div');
      bd.className = 'asd-backdrop';
      const card = document.createElement('div');
      card.className = 'asd-card';
      card.setAttribute('role', 'alertdialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-labelledby', 'asd-title');
      card.setAttribute('aria-describedby', 'asd-msg');

      const head = document.createElement('div');
      head.className = 'asd-head';
      const ic = document.createElement('div');
      ic.className = 'asd-icon';
      ic.style.background = tone.bg;
      ic.innerHTML = svg(opts.icon || 'question', tone.c);
      const txt = document.createElement('div');
      const h = document.createElement('h2');
      h.className = 'asd-title'; h.id = 'asd-title'; h.textContent = opts.title || 'Opravdu?';
      const p = document.createElement('p');
      p.className = 'asd-msg'; p.id = 'asd-msg'; p.textContent = opts.message || '';
      txt.append(h, p);
      if (Array.isArray(opts.list) && opts.list.length) {
        const ul = document.createElement('ul');
        ul.className = 'asd-list';
        opts.list.forEach((t) => { const li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
        txt.appendChild(ul);
      }
      head.append(ic, txt);

      const actions = document.createElement('div');
      actions.className = 'asd-actions';
      const no = document.createElement('button');
      no.type = 'button'; no.className = 'asd-btn'; no.textContent = opts.cancelText || 'Zrušit';
      const yes = document.createElement('button');
      yes.type = 'button'; yes.className = 'asd-btn go'; yes.textContent = opts.confirmText || 'Pokračovat';
      yes.style.background = tone.c;
      actions.append(no, yes);
      card.append(head, actions);
      bd.appendChild(card);
      document.body.appendChild(bd);
      requestAnimationFrame(() => bd.classList.add('on'));
      setTimeout(() => (opts.tone === 'danger' ? no : yes).focus(), 30);

      const done = (val) => {
        document.removeEventListener('keydown', onKey, true);
        bd.classList.remove('on');
        setTimeout(() => bd.remove(), 200);
        if (prevFocus && prevFocus.focus) prevFocus.focus({ preventScroll: true });
        resolve(val);
      };
      const onKey = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(false); }
        else if (e.key === 'Tab') {                       // fokus jen uvnitř okna
          e.preventDefault();
          (document.activeElement === yes ? no : yes).focus();
        }
      };
      document.addEventListener('keydown', onKey, true);
      no.addEventListener('click', () => done(false));
      yes.addEventListener('click', () => done(true));
      bd.addEventListener('mousedown', (e) => { if (e.target === bd) done(false); });
    });
  };
})();
