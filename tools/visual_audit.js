// Visual/glitch audit (see tools/audit_server.py for how to run it). Loads pages in a same-origin iframe at several device sizes and records problems.
// Usage (in the page): window.scAudit({widths: [...], pages: [...], themes: ['light','dark']}) -> Promise<report>
(function () {
  const DEVICES = {
    "se-320": [320, 568], "iphone-375": [375, 667], "iphone16-393": [393, 852], "promax-430": [430, 932],
    "ipad-768": [768, 1024], "laptop-1280": [1280, 800], "wide-1600": [1600, 900],
  };
  const SKIP = /logout|delete|\/tasks\/|\.csv$|\.ics$|\.svg$|\.png$|qr|\/static\/|\/join\/|mailto:|\/photo\/skip/;

  function parseRGB(c) {
    const m = c && c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }
  function lum({ r, g, b }) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  function bgOf(win, el) {
    for (let e = el; e; e = e.parentElement) {
      const cs = win.getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== "none") return null; // gradient/image: skip
      const c = parseRGB(cs.backgroundColor);
      if (c && c.a > 0.9) return c;
    }
    return parseRGB(win.getComputedStyle(win.document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
  }
  const visible = (win, el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    for (let e = el; e; e = e.parentElement) {
      const cs = win.getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return false;
      if (e.hidden) return false;
    }
    return true;
  };
  const label = (el) => {
    const t = (el.getAttribute("aria-label") || el.textContent || el.value || el.name || el.className || el.tagName)
      .toString().replace(/\s+/g, " ").trim();
    return `${el.tagName.toLowerCase()}「${t.slice(0, 40)}」`;
  };

  function load(frame, url) {
    return new Promise((resolve) => {
      const done = () => { clearTimeout(timer); resolve(); };
      const timer = setTimeout(done, 8000);
      frame.onload = () => setTimeout(done, 250);
      frame.src = url;
    });
  }

  function check(frame, device, theme, isMobile) {
    const win = frame.contentWindow, doc = frame.contentDocument, out = [];
    if (!doc || !doc.body) return [{ kind: "no-document" }];
    if (theme) doc.documentElement.setAttribute("data-theme", theme);
    const vw = win.innerWidth, vh = win.innerHeight;
    const add = (kind, detail) => out.push({ kind, detail });
    // 1. sideways scroll
    if (doc.documentElement.scrollWidth > vw + 1) add("sideways-scroll", `${doc.documentElement.scrollWidth} > ${vw}`);
    const all = [...doc.querySelectorAll("body *")].filter((e) => !e.closest("svg") && e.tagName !== "SCRIPT");
    // 2. elements sticking out right edge
    for (const e of all) {
      if (!visible(win, e)) continue;
      const r = e.getBoundingClientRect();
      if (r.right > vw + 2 && win.getComputedStyle(e).position !== "fixed" && !e.closest(".scroll-x, .chip-row, .tabs-scroll, [data-scroll-x]")) {
        let clipped = false;
        for (let p = e.parentElement; p; p = p.parentElement) {
          const o = win.getComputedStyle(p).overflowX;
          if (o === "auto" || o === "scroll" || o === "hidden") { clipped = true; break; }
        }
        if (!clipped) { add("off-screen-right", `${label(e)} right=${Math.round(r.right)}`); }
      }
    }
    // 3. text cut off (overflow hidden/ellipsis with content bigger than box) — only report non-ellipsis clipping
    for (const e of all) {
      const cs = win.getComputedStyle(e);
      if ((cs.overflow === "hidden" || cs.overflowX === "hidden") && e.scrollWidth > e.clientWidth + 2 &&
          cs.textOverflow !== "ellipsis" && e.children.length === 0 && e.textContent.trim() && visible(win, e)) {
        add("text-clipped", label(e));
      }
    }
    // 4. overlapping controls
    const controls = [...doc.querySelectorAll("a, button, input, select, textarea, label.chip-check, summary")]
      .filter((e) => visible(win, e) && !(e.tagName === "INPUT" && ["hidden", "checkbox", "radio"].includes(e.type)));
    const rects = controls.map((e) => e.getBoundingClientRect());
    for (let i = 0; i < controls.length; i++) {
      for (let j = i + 1; j < controls.length; j++) {
        const a = controls[i], b = controls[j];
        if (a.contains(b) || b.contains(a)) continue;
        if (a.closest(".password-wrap") && a.closest(".password-wrap") === b.closest(".password-wrap")) continue; // eye inside the box
        const fixedA = !!a.closest(".help-bubble, .appnav, .topbar"), fixedB = !!b.closest(".help-bubble, .appnav, .topbar");
        if (fixedA !== fixedB) continue; // fixed bubble/nav over scrolling content is by design
        const r = rects[i], s = rects[j];
        const w = Math.min(r.right, s.right) - Math.max(r.left, s.left);
        const h = Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top);
        if (w > 3 && h > 3) add("overlap", `${label(a)} × ${label(b)} (${Math.round(w)}x${Math.round(h)})`);
      }
    }
    // 5. small tap targets on touch sizes
    if (isMobile) {
      for (let i = 0; i < controls.length; i++) {
        const e = controls[i], r = rects[i];
        if (e.tagName === "A" && win.getComputedStyle(e).display === "inline" && e.closest("p, li, small, .muted, .fine-print, footer")) continue; // links inside sentences
        if (e.tagName === "LABEL" || e.tagName === "TEXTAREA") continue;
        if (r.right <= 0 || r.bottom <= 0) continue; // parked off-screen until focused (e.g. "Skip to content")
        if (win.getComputedStyle(e, "::after").position === "absolute") continue; // stretched over its whole card
        if (r.height < 32 || r.width < 24) add("small-tap-target", `${label(e)} ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
    }
    // 6. images
    for (const img of doc.images) {
      if (img.complete && img.naturalWidth === 0 && img.loading !== "lazy") add("broken-image", img.getAttribute("src"));
      if (!img.hasAttribute("alt")) add("img-no-alt", img.getAttribute("src"));
    }
    // 7. contrast of text
    const seen = new Set();
    for (const e of all) {
      if (!e.childNodes.length || ![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
      if (!visible(win, e) || e.closest(".visually-hidden, [aria-hidden=true]")) continue;
      const cs = win.getComputedStyle(e);
      const fg = parseRGB(cs.color), bg = bgOf(win, e);
      if (!fg || !bg) continue;
      const ratio = contrast(fg, bg);
      const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
      const need = size >= 24 || (size >= 18.5 && bold) ? 3 : 4.5;
      if (e.matches("input, textarea, select") ) continue;
      if (e.closest(".brand")) continue;  // the logo (gold "Circle", the owner's pick): logotypes are exempt from contrast rules
      if (ratio < need - 0.05) {
        const key = `${cs.color}|${e.textContent.trim().slice(0, 20)}`;
        if (!seen.has(key)) { seen.add(key); add("low-contrast", `${label(e)} ${ratio.toFixed(2)} (need ${need})`); }
      }
    }
    // 8. repeated adjacent links/buttons with same text & target (repetition)
    const links = [...doc.querySelectorAll("main a[href]")].filter((a) => visible(win, a));
    const byKey = {};
    for (const a of links) {
      const k = `${a.textContent.replace(/\s+/g, " ").trim()}|${a.getAttribute("href")}`;
      if (!a.textContent.trim()) continue;
      byKey[k] = (byKey[k] || 0) + 1;
    }
    for (const [k, n] of Object.entries(byKey)) if (n > 1 && !/^(?:[^|]*\|\/u\/|[^|]*\|\/events\/\d+$|[^|]*\|\/clubs\/\d+$)/.test(k)) add("repeated-link", `${k} ×${n}`);
    // 9. page needs scrolling (height of main content vs viewport) — info only on phones
    const main = doc.querySelector("main");
    if (isMobile && main) {
      const bottom = main.getBoundingClientRect().bottom + win.scrollY;
      if (bottom > vh * 1.02) add("needs-scroll", `${Math.round(bottom)} / ${vh}`);
    }
    // 10. empty headings, duplicated h1
    const h1s = [...doc.querySelectorAll("h1")].filter((h) => visible(win, h));
    if (h1s.length !== 1) add("h1-count", String(h1s.length));
    for (const h of doc.querySelectorAll("h1,h2,h3")) if (visible(win, h) && !h.textContent.trim()) add("empty-heading", h.outerHTML.slice(0, 60));
    // 11. emoji-heavy text (testers said emojis feel AI) — count visible emoji in main
    const text = main ? main.innerText : "";
    const emojis = (text.match(/\p{Extended_Pictographic}/gu) || []).length;
    if (emojis > 12) add("many-emoji", String(emojis));
    // 12. words on the page (target ~30 on phone-first screens) — info
    const words = text.split(/\s+/).filter(Boolean).length;
    if (words > 250) add("wordy", String(words));
    if (theme) doc.documentElement.removeAttribute("data-theme");
    return out;
  }

  async function crawl(start, limit) {
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;left:0;top:0;width:1280px;height:800px;opacity:0;pointer-events:none;";
    document.body.append(frame);
    const seen = new Set(), queue = [...start], pages = [];
    while (queue.length && pages.length < limit) {
      const url = queue.shift();
      if (seen.has(url)) continue;
      seen.add(url);
      await load(frame, url);
      const doc = frame.contentDocument;
      if (!doc) continue;
      const final = frame.contentWindow.location.pathname + frame.contentWindow.location.search;
      if (final !== url && seen.has(final)) continue;
      seen.add(final);
      pages.push(final);
      for (const a of doc.querySelectorAll("a[href]")) {
        const u = new URL(a.getAttribute("href"), frame.contentWindow.location.href);
        if (u.origin !== location.origin || SKIP.test(u.pathname + u.search)) continue;
        // one example per pattern (numbers replaced)
        const key = (u.pathname + u.search).replace(/\d+/g, "N");
        if ([...seen].some((s) => s.replace(/\d+/g, "N") === key) || queue.some((q) => q.replace(/\d+/g, "N") === key)) continue;
        queue.push(u.pathname + u.search);
      }
    }
    frame.remove();
    return pages;
  }

  async function audit(opts) {
    const devices = opts.devices || Object.keys(DEVICES);
    const themes = opts.themes || [null];
    const pages = opts.pages || await crawl(opts.start || ["/"], opts.limit || 80);
    const errors = [];
    const report = {};
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;left:0;top:0;opacity:0;pointer-events:none;border:0;";
    document.body.append(frame);
    for (const device of devices) {
      const [w, h] = DEVICES[device];
      frame.style.width = w + "px"; frame.style.height = h + "px";
      for (const url of pages) {
        await load(frame, url);
        try {
          frame.contentWindow.addEventListener("error", (ev) => errors.push(`${url}: ${ev.message}`));
        } catch (e) { /* ignore */ }
        for (const theme of themes) {
          let issues;
          try { issues = check(frame, device, theme, w < 768); } catch (e) { issues = [{ kind: "audit-crash", detail: String(e) }]; }
          for (const i of issues) {
            const key = `${i.kind}|${url}|${i.detail}`;
            (report[key] = report[key] || { kind: i.kind, url, detail: i.detail, where: [] }).where.push(device + (theme ? "/" + theme : ""));
          }
        }
      }
    }
    frame.remove();
    return { pages, errors, issues: Object.values(report) };
  }
  window.scAudit = audit;
  window.scCrawl = crawl;
})();
