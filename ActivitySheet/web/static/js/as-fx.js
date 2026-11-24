/* as-fx – canvas efekty Activity Sheet (bez knihoven).
 *
 *   FX.mount(canvas, 'card'|'flow'|'loader'|'source', opts) → ovladač { trigger, reset, set, destroy }
 *   FX.burst(x, y, color)            – výboj částic (úspěch)
 *   FX.fly(fromRects, toRect, color) – částice odletí z prvků do cíle (uložení)
 *
 * Animace běží jen když je stránka vidět. Při „omezit animace“ ve Windows se nic nekreslí
 * (zůstane statická CSS podoba).
 */
var FX = (function () {
  var reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var NOOP = { trigger: function () {}, reset: function () {}, set: function () {}, destroy: function () {} };

  function rand(a, b) { return a + Math.random() * (b - a); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function ease(t) { return t < 0 ? 0 : t > 1 ? 1 : 1 - Math.pow(1 - t, 3); }
  function hexA(hex, a) {
    var h = (hex || '#0d6efd').replace('#', '');
    if (h.length === 3) h = h.replace(/./g, '$&$&');
    var n = parseInt(h, 16);
    return 'rgba(' + (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function rr(g, x, y, w, h, r) {
    g.beginPath();
    if (g.roundRect) g.roundRect(x, y, w, h, r); else g.rect(x, y, w, h);
  }

  function samplePoints(w, h, draw, step) {
    var c = document.createElement('canvas');
    c.width = Math.max(1, Math.ceil(w)); c.height = Math.max(1, Math.ceil(h));
    var g = c.getContext('2d');
    draw(g);
    var d = g.getImageData(0, 0, c.width, c.height).data, pts = [];
    for (var y = 0; y < c.height; y += step) for (var x = 0; x < c.width; x += step) {
      if (d[(y * c.width + x) * 4 + 3] > 128) pts.push({ x: x, y: y });
    }
    return pts;
  }

  function setup(canvas) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = canvas.clientWidth || canvas.width, h = canvas.clientHeight || canvas.height;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    var g = canvas.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { g: g, w: w, h: h };
  }

  function loop(canvas, fn) {
    var alive = true, last = performance.now();
    function tick(now) {
      if (!alive) return;
      var dt = Math.min(0.05, (now - last) / 1000); last = now;
      // kreslit jen když je stránka i prvek vidět (offsetParent = null u display:none)
      if (!document.hidden && (!canvas || canvas.offsetParent !== null)) fn(dt);
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
    return function () { alive = false; };
  }

  // ------------------------------------------------------------ karta (čeká na kartu)
  function card(canvas, o) {
    var S = setup(canvas), g = S.g, W = S.w, H = S.h;
    var accent = o.accent || '#0d6efd';
    var cw = Math.min(190, W * 0.7), ch = cw * 0.63, cx = W / 2 - cw / 2, cy = H / 2 - ch / 2;
    var pts = samplePoints(W, H, function (c) {
      c.strokeStyle = '#000'; c.lineWidth = 3;
      rr(c, cx, cy, cw, ch, 14); c.stroke();
      c.fillStyle = '#000'; c.fillRect(cx + cw * 0.1, cy + ch * 0.2, cw * 0.17, ch * 0.2);
      c.fillRect(cx + cw * 0.1, cy + ch * 0.66, cw * 0.58, 6); c.fillRect(cx + cw * 0.1, cy + ch * 0.8, cw * 0.37, 6);
    }, 3);
    var P = pts.map(function (p) {
      return { x: p.x + rand(-160, 160), y: p.y + rand(-80, 80), hx: p.x, hy: p.y, fly: false, t: 0, a: 1 };
    });
    var beam = 0, flying = false;
    function trigger() {
      if (flying) return;
      flying = true;
      P.forEach(function (p) {
        p.fly = true; p.t = -rand(0, 0.25) - (p.hx - cx) / cw * 0.2;
        p.sx = p.x; p.sy = p.y;
        p.ex = W / 2 + rand(-W * 0.35, W * 0.35); p.ey = H + rand(10, 40);       // dolů do warehouse
        p.cx = lerp(p.sx, p.ex, 0.5) + rand(-40, 40); p.cy = Math.min(p.sy, p.ey) - rand(10, 60);
      });
    }
    function reset() {
      flying = false;
      P.forEach(function (p) { p.fly = false; p.a = 1; p.x = p.hx + rand(-160, 160); p.y = p.hy + rand(-80, 80); });
    }
    var stop = loop(canvas, function (dt) {
      beam += dt * 0.9;
      g.clearRect(0, 0, W, H);
      var beamY = cy + (Math.sin(beam * 2) * 0.5 + 0.5) * ch;
      P.forEach(function (p) {
        if (p.fly) {
          p.t += dt * 1.2;
          var t = ease(Math.max(0, Math.min(1, p.t))), u = 1 - t;
          p.x = u * u * p.sx + 2 * u * t * p.cx + t * t * p.ex;
          p.y = u * u * p.sy + 2 * u * t * p.cy + t * t * p.ey;
          p.a = Math.max(0, 1 - Math.max(0, p.t - 0.6) * 2.5);
        } else {
          p.x += (p.hx - p.x) * Math.min(1, dt * 7);
          p.y += (p.hy - p.y) * Math.min(1, dt * 7);
        }
        if (p.a <= 0) return;
        g.globalAlpha = p.a;
        g.fillStyle = p.fly || Math.abs(p.y - beamY) < 7 ? accent : '#1f2937';
        g.fillRect(p.x - 1.2, p.y - 1.2, 2.4, 2.4);
      });
      g.globalAlpha = 1;
      if (!flying) {
        var grd = g.createLinearGradient(0, beamY - 8, 0, beamY + 8);
        grd.addColorStop(0, hexA(accent, 0)); grd.addColorStop(0.5, hexA(accent, 0.3)); grd.addColorStop(1, hexA(accent, 0));
        g.fillStyle = grd; g.fillRect(cx - 18, beamY - 8, cw + 36, 16);
        g.fillStyle = accent; g.fillRect(cx - 18, beamY - 1, cw + 36, 2);
      }
    });
    return { trigger: trigger, reset: reset, set: function (a) { accent = a || accent; }, destroy: stop };
  }

  // --------------------------------------------- proud dat mezi kroky (nad DOM ukazatelem)
  function flow(canvas, o) {
    var S = setup(canvas), g = S.g, W = S.w, H = S.h, P = [];
    var stop = loop(canvas, function (dt) {
      if (canvas.clientWidth && Math.abs(canvas.clientWidth - W) > 2) { S = setup(canvas); g = S.g; W = S.w; H = S.h; }
      g.clearRect(0, 0, W, H);
      var seg = o.getSegment && o.getSegment();                // {x1,y,x2} v souřadnicích canvasu
      if (seg && Math.random() < 0.75) P.push({ x: seg.x1, y: seg.y + rand(-3, 3), to: seg.x2, v: rand(110, 190), a: 1 });
      P.forEach(function (p) {
        p.x += p.v * dt;
        if (p.x > p.to) p.a -= dt * 5;
        g.fillStyle = hexA(o.color || '#0d6efd', Math.max(0, p.a));
        g.fillRect(p.x - 2, p.y - 2, 4, 4);
      });
      P = P.filter(function (p) { return p.a > 0; });
    });
    return { trigger: function () {}, reset: function () { P = []; }, set: function () {}, destroy: stop };
  }

  // --------------------------------------------------------------------- načítání
  function loader(canvas, o) {
    var S = setup(canvas), g = S.g, W = S.w, H = S.h, time = 0;
    var bars = [3, 2, 5, 2, 3, 6, 2, 4, 2, 3, 5, 2, 6, 3, 2, 4];
    var k = Math.min(W, H) / 110;
    var color = o.color || '#0d6efd';
    var stop = loop(canvas, function (dt) {
      time += dt;
      g.clearRect(0, 0, W, H);
      var m = Math.sin(time * 1.6) * 0.5 + 0.5; m = m * m * (3 - 2 * m);
      var cx = W / 2, cy = H / 2, R = 34 * k, n = bars.length;
      var total = bars.reduce(function (a, b) { return a + (b + 3) * k; }, 0);
      var x = cx - total / 2;
      bars.forEach(function (w, i) {
        var bw = w * k, lx = x + bw / 2; x += (w + 3) * k;
        var a = i / n * Math.PI * 2 + time * 2.6;
        var px = lerp(lx, cx + Math.cos(a) * R, m), py = lerp(cy, cy + Math.sin(a) * R, m);
        var len = lerp(44 * k, 12 * k, m);
        g.save(); g.translate(px, py); g.rotate(lerp(0, a + Math.PI / 2, m));
        g.fillStyle = m > 0.5 ? hexA(color, 0.35 + 0.65 * ((i / n + time * 0.45) % 1)) : '#1f2937';
        g.fillRect(-bw / 2, -len / 2, Math.max(1, bw), len); g.restore();
      });
    });
    return { trigger: function () {}, reset: function () {}, set: function () {}, destroy: stop };
  }

  // ---------------------------------------------------------- zdroj server ↔ tento PC
  function icon(g, kind, x, y, col) {
    g.save(); g.translate(x, y); g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 2.2; g.lineJoin = 'round';
    if (kind === 'server') {
      for (var i = 0; i < 3; i++) { g.strokeRect(-18, -21 + i * 14, 36, 11); g.fillRect(9, -17.5 + i * 14, 3.5, 3.5); }
    } else {
      g.strokeRect(-21, -18, 42, 27); g.beginPath(); g.moveTo(-8, 17); g.lineTo(8, 17); g.moveTo(0, 9); g.lineTo(0, 17); g.stroke();
    }
    g.restore();
  }
  function source(canvas, o) {
    // Ze serveru: proud teče server → PC. Vlastní: proud se zastaví (co je na cestě, doteče
    // do PC a zhasne), server zešedne a PC dostane kroužek. Nic neteče zpět na server.
    var S = setup(canvas), g = S.g, W = S.w, H = S.h, P = [], dir = o.dir || 1, pulse = 0, ring = dir > 0 ? 0 : 1;
    var ax = 34, bx = W - 34, cy = H / 2 - 4;
    var stop = loop(canvas, function (dt) {
      pulse = Math.max(0, pulse - dt);
      var srvOn = dir > 0;
      ring += (srvOn ? -1 : 1) * dt * 2.5; ring = Math.max(0, Math.min(1, ring));
      g.clearRect(0, 0, W, H);
      icon(g, 'server', ax, cy, srvOn ? '#0d6efd' : '#adb5bd');
      icon(g, 'pc', bx, cy, srvOn ? '#495057' : '#0ca678');
      if (srvOn && Math.random() < (pulse > 0 ? 1 : 0.5)) P.push({ t: 0, off: rand(-6, 6) });
      P.forEach(function (p) {
        p.t += dt * (srvOn ? (pulse > 0 ? 1.2 : 0.75) : 0.55);       // po zastavení jen dobíhá
        var t = Math.min(1, p.t);
        var x = lerp(ax + 26, bx - 28, t), y = cy + p.off - Math.sin(t * Math.PI) * 14;
        var a = Math.sin(t * Math.PI) * (srvOn ? 1 : 0.6);
        g.fillStyle = hexA('#0d6efd', a);
        g.fillRect(x - 1.4, y - 1.4, 2.8, 2.8);
      });
      P = P.filter(function (p) { return p.t < 1; });
      if (ring > 0) {                                        // vlastní seznam: kroužek kolem PC
        g.strokeStyle = hexA('#0ca678', ring * (0.25 + Math.sin(performance.now() / 400) * 0.1)); g.lineWidth = 2;
        g.beginPath(); g.arc(bx, cy - 2, 22 + ring * 8, 0, Math.PI * 2); g.stroke();
      }
    });
    return {
      trigger: function () {}, reset: function () {},
      set: function (d) { if (d !== dir) { dir = d; if (d > 0) pulse = 1.2; } },
      destroy: stop
    };
  }

  // ---------------------------------------------------- dočasná vrstva přes celou stránku
  function overlay(duration, draw) {
    if (reduce) return;
    var c = document.createElement('canvas');
    c.setAttribute('aria-hidden', 'true');
    c.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:30000';
    document.body.appendChild(c);
    var S = setup(c), t = 0;
    var stop = loop(null, function (dt) {
      t += dt;
      S.g.clearRect(0, 0, S.w, S.h);
      draw(S.g, dt, t);
      if (t > duration) { stop(); c.remove(); }
    });
  }

  function burst(x, y, color) {
    var P = [];
    for (var i = 0; i < 150; i++) {
      var a = rand(0, Math.PI * 2), v = rand(90, 360);
      P.push({ x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 80, life: rand(0.7, 1.5),
               c: Math.random() < 0.72 ? (color || '#2b8a3e') : '#ffd43b', s: rand(2, 4.5) });
    }
    overlay(1.6, function (g, dt, t) {
      P.forEach(function (p) {
        if (t > p.life) return;
        p.vy += 340 * dt; p.vx *= 0.99; p.x += p.vx * dt; p.y += p.vy * dt;
        g.globalAlpha = Math.max(0, 1 - t / p.life); g.fillStyle = p.c; g.fillRect(p.x, p.y, p.s, p.s);
      });
      g.globalAlpha = 1;
    });
  }

  function fly(fromRects, to, color) {
    var P = [];
    var tx = to.left + to.width / 2, ty = to.top + to.height / 2;
    fromRects.slice(0, 12).forEach(function (r) {
      var n = Math.min(60, Math.max(18, Math.round(r.width / 12)));
      for (var i = 0; i < n; i++) {
        var sx = rand(r.left, r.right), sy = rand(r.top, r.bottom);
        P.push({ sx: sx, sy: sy, cx: lerp(sx, tx, 0.5) + rand(-60, 60), cy: Math.min(sy, ty) - rand(40, 140), d: rand(0, 0.3) });
      }
    });
    overlay(1.5, function (g, dt, t) {
      P.forEach(function (p) {
        var k = ease((t - p.d) / 1.0);
        if (k <= 0) return;
        var u = 1 - k, x = u * u * p.sx + 2 * u * k * p.cx + k * k * tx, y = u * u * p.sy + 2 * u * k * p.cy + k * k * ty;
        g.globalAlpha = k >= 1 ? 0 : 1 - Math.max(0, k - 0.85) * 6;
        g.fillStyle = color || '#0d6efd'; g.fillRect(x - 1.6, y - 1.6, 3.2, 3.2);
      });
      g.globalAlpha = 1;
    });
  }

  var scenes = { card: card, flow: flow, loader: loader, source: source };
  return {
    reduce: reduce,
    mount: function (canvas, scene, opts) {
      if (reduce || !canvas || !scenes[scene]) return NOOP;
      try { return scenes[scene](canvas, opts || {}); } catch (e) { return NOOP; }
    },
    burst: function (x, y, c) { try { burst(x, y, c); } catch (e) { /* jen efekt */ } },
    fly: function (f, t, c) { try { fly(f, t, c); } catch (e) { /* jen efekt */ } }
  };
})();
