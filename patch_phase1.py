#!/usr/bin/env python3
"""Phase 1 — standalone Sparkle Layer for Sticker Slop Studio.

- createSparkleLayer(): new layer type with stars/dust/color data model
- renderSparkleLayer(): seeded RNG field rendered to its own offscreen canvas,
  loop-safe twinkle (life = (time/proj.dur*twinkle + phase) % 1), then through
  Phase 0's compositeLayerEffects() (mask/erase/adjustments come free)
- renderLayers() + getLayerDimensions() branches
- UI: ADD SPARKLE FIELD button + inspector panel with live bindings
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "index.html"
src = open(PATH, encoding="utf-8").read()

def sub_exact(s, old, new, count=1, label=""):
    c = s.count(old)
    assert c == count, f"[{label}] anchor count {c} != {count}: {old[:70]!r}"
    return s.replace(old, new)

# ============================================================
# 1. createSparkleLayer() — after createMediaLayer
# ============================================================
create_fn = '''    anims: []
  };
}

// --------------------------------------------------------
// SPARKLE FIELD LAYER (PHASE 1)
// --------------------------------------------------------
function createSparkleLayer() {
  return {
    id: genId(), type: 'sparkle', name: 'Sparkle Field',
    visible: true, locked: false,
    x: appState.proj.w / 2, y: appState.proj.h / 2,
    scaleX: 1, scaleY: 1, rotation: 0, opacity: 1, blendMode: 'source-over',

    w: 300, h: 300,          // the field's own box, independent of scaleX/Y
    seed: 1337,               // reproducible

    stars: {
      count: 40,
      sizeMin: 4, sizeMax: 12,     // size jitter
      shape: 'burst',               // v1: burst only. v2: dot | diamond | mixed
      twinkleSpeed: 1               // twinkles per full project loop
    },
    dust: { count: 80, size: 2 },

    color: {
      mode: 'rainbow',              // single | palette | rainbow
      single: '#ffffff',
      palette: ['#ff3fd0', '#d9b3ff', '#2fe3ff'],  // 2-6 colors, weighted pick
      weights: null                 // null = reuse GLITTER_WEIGHTS falloff
    },
    colorJitter: 0.15,              // hue wiggle per-sparkle, even in single-color mode
    brightnessJitter: 0.25,         // independent lightness variance per-sparkle

    parentLayerId: null,
    anims: [],
    mask: { en: false, type: 'circle', invert: false, feather: 0, scale: 1, offsetX: 0, offsetY: 0, rot: 0, rx: 1, ry: 1, width: 0.85, height: 0.85, radius: 0, linePos: 0, lineAngle: 0, starPoints: 5, starDepth: 0.5, triType: 'equilateral', triApex: 0, polySides: 6, flowerPetals: 8, flowerDepth: 0.65 },
    glitch: { en: false, rgbDist: 6, slice: 4 },
    adj: { b: 0, c: 0, s: 1, h: 0, vib: 0, temp: 0, tint: 0, exp: 0, gamma: 1, targetHue: 'all', targetCenter: 60, targetShift: 0, targetSat: 1, targetLight: 0, targetRange: 45 }
  };
}
window.createSparkleLayer = createSparkleLayer;

// --------------------------------------------------------
// MASK & SHAPE CUTOUT PATH SYSTEM'''

old = '''    anims: []
  };
}

// --------------------------------------------------------
// MASK & SHAPE CUTOUT PATH SYSTEM'''
src = sub_exact(src, old, create_fn, 1, "createSparkleLayer")

# ============================================================
# 2. renderLayers() branch
# ============================================================
old = """    if (l.type === 'text') renderTextLayer(targetCtx, l, time);
    else if (l.type === 'media') renderMediaLayer(targetCtx, l, time);"""
new = """    if (l.type === 'text') renderTextLayer(targetCtx, l, time);
    else if (l.type === 'media') renderMediaLayer(targetCtx, l, time);
    else if (l.type === 'sparkle') renderSparkleLayer(targetCtx, l, time);"""
src = sub_exact(src, old, new, 1, "renderLayers branch")

# ============================================================
# 3. getLayerDimensions() branch
# ============================================================
old = """  }
  return { boxW, boxH };"""
new = """  } else if (l.type === 'sparkle') {
    boxW = l.w || 300;
    boxH = l.h || 300;
  }
  return { boxW, boxH };"""
src = sub_exact(src, old, new, 1, "getLayerDimensions branch")

# ============================================================
# 4. renderSparkleLayer() — before LAYER STACK OPERATIONS header
# ============================================================
render_fn = '''// --------------------------------------------------------
// SPARKLE FIELD RENDERER (PHASE 1)
// Seeded stars + dust on the layer's own w x h box. Loop-safe twinkle:
// life = (time / proj.dur * twinkleSpeed + phase) % 1 — driven by the project
// loop, so exported GIFs/loops wrap seamlessly. Runs through the Phase 0
// unified pipeline, so mask / erase / adjustments / glitch work for free.
// --------------------------------------------------------
function renderSparkleLayer(ctx, l, time) {
  const w = Math.max(1, Math.round(l.w || 300));
  const h = Math.max(1, Math.round(l.h || 300));
  const off = document.createElement('canvas');
  off.width = w; off.height = h;
  const octx = off.getContext('2d', { willReadFrequently: true });

  const seed = (typeof l.seed === 'number') ? l.seed : 1337;
  const rnd = mulberry32(seed + 54321);
  const dur = (appState.proj && appState.proj.dur) ? appState.proj.dur : 6;
  const loopT = dur > 0 ? (((time / dur) % 1) + 1) % 1 : 0;

  const starsCfg = l.stars || {};
  const dustCfg = l.dust || {};
  const colCfg = l.color || {};
  const mode = colCfg.mode || 'rainbow';
  const palette = (Array.isArray(colCfg.palette) && colCfg.palette.length >= 2)
    ? colCfg.palette : ['#ff3fd0', '#d9b3ff', '#2fe3ff'];
  const weights = Array.isArray(colCfg.weights) ? colCfg.weights : GLITTER_WEIGHTS;
  const hueJitter = (typeof l.colorJitter === 'number') ? l.colorJitter : 0.15;
  const briJitter = (typeof l.brightnessJitter === 'number') ? l.brightnessJitter : 0.25;
  const twinkle = Math.max(0.1, (starsCfg.twinkleSpeed !== undefined ? starsCfg.twinkleSpeed : 1));

  const hexToHslArr = (hex) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return [0, 0, 100];
    const v = parseInt(m[1], 16);
    return rgbToHsl((v >> 16) & 255, (v >> 8) & 255, v & 255);
  };

  // Color per sparkle: rainbow-by-position, single, or weighted palette pick
  // (GLITTER_WEIGHTS falloff) — plus independent hue & brightness jitter.
  const resolveColor = (sx, sy, rPick, rHue, rBri, baseSat, baseLight) => {
    let hue, sat, light;
    if (mode === 'rainbow') {
      hue = ((sx / Math.max(1, w)) * 330 + (sy / Math.max(1, h)) * 30) % 360;
      sat = baseSat; light = baseLight;
    } else {
      let hex = colCfg.single || '#ffffff';
      if (mode === 'palette') {
        hex = palette[palette.length - 1];
        let acc = 0;
        for (let i = 0; i < palette.length; i++) {
          acc += (weights[i] !== undefined ? weights[i] : 0);
          if (rPick < acc) { hex = palette[i]; break; }
        }
      }
      const hsl = hexToHslArr(hex);
      hue = hsl[0]; sat = hsl[1] * 100; light = hsl[2] * 100;
    }
    if (hueJitter > 0) hue = (hue + (rHue - 0.5) * hueJitter * 360 + 720) % 360;
    if (briJitter > 0) light = Math.max(8, Math.min(100, light * (1 + (rBri - 0.5) * 2 * briJitter)));
    return 'hsl(' + Math.round(hue) + ', ' + Math.round(sat) + '%, ' + Math.round(light) + '%)';
  };

  // Stars (burst shape) — all RNG consumed before any continue, so positions
  // stay stable as stars twinkle in and out.
  const starsCount = Math.max(0, Math.floor(starsCfg.count || 0));
  const sizeMin = starsCfg.sizeMin !== undefined ? starsCfg.sizeMin : 4;
  const sizeMax = starsCfg.sizeMax !== undefined ? starsCfg.sizeMax : 12;
  for (let i = 0; i < starsCount; i++) {
    const sx = Math.floor(rnd() * w);
    const sy = Math.floor(rnd() * h);
    const phase = rnd();
    const span = Math.max(1, sizeMax - sizeMin + 1);
    const maxR = sizeMin + Math.floor(rnd() * span);
    const rPick = rnd(), rHue = rnd(), rBri = rnd();

    const life = (loopT * twinkle + phase) % 1;
    const scl = 1 - Math.abs(life * 2 - 1);
    const r = Math.round(maxR * scl);
    if (r <= 0) continue;

    octx.fillStyle = resolveColor(sx, sy, rPick, rHue, rBri, 100, 75);
    const armW = Math.max(2, Math.floor(r / 3));
    octx.fillRect(sx - r, sy - Math.floor(armW / 2), r * 2, armW);
    octx.fillRect(sx - Math.floor(armW / 2), sy - r, armW, r * 2);
    const diag = Math.round(r * 0.55);
    const dotS = Math.max(1, Math.floor(armW * 0.8));
    octx.fillRect(sx - diag, sy - diag, dotS, dotS);
    octx.fillRect(sx + diag, sy - diag, dotS, dotS);
    octx.fillRect(sx - diag, sy + diag, dotS, dotS);
    octx.fillRect(sx + diag, sy + diag, dotS, dotS);
    octx.fillStyle = '#ffffff';
    octx.fillRect(sx - 1, sy - 1, 2, 2);
  }

  // Dust — quick motes that fade out early in the loop
  const dustCount = Math.max(0, Math.floor(dustCfg.count || 0));
  const dustSize = Math.max(1, Math.floor(dustCfg.size !== undefined ? dustCfg.size : 2));
  for (let j = 0; j < dustCount; j++) {
    const dx = Math.floor(rnd() * w);
    const dy = Math.floor(rnd() * h);
    const dPhase = rnd();
    const rPick = rnd(), rHue = rnd(), rBri = rnd();

    const dLife = (loopT * twinkle + dPhase) % 1;
    if (dLife > 0.45) continue;

    octx.fillStyle = resolveColor(dx, dy, rPick, rHue, rBri, 100, 80);
    octx.fillRect(dx, dy, dustSize, dustSize);
  }

  // Phase 0 unified pipeline: adjustments -> mask -> erase -> glitch.
  // skipGlitter: the glitter engine has no source canvas for sparkle layers
  // and would composite an empty frame — the field IS the sparkle effect.
  compositeLayerEffects(off, l, time, ctx, { skipGlitter: true });
}
window.renderSparkleLayer = renderSparkleLayer;

// --------------------------------------------------------
// LAYER STACK OPERATIONS'''
old = '''// --------------------------------------------------------
// LAYER STACK OPERATIONS'''
src = sub_exact(src, old, render_fn, 1, "renderSparkleLayer")

# ============================================================
# 5. ADD SPARKLE FIELD button (toolbar)
# ============================================================
old = '''        <input type="file" id="file-media" style="display:none" accept="image/*,image/gif" multiple>
      </div>'''
new = '''        <input type="file" id="file-media" style="display:none" accept="image/*,image/gif" multiple>
      </div>
      <div class="panel-section" style="padding: 0 12px 6px 12px; display:flex; gap:6px;">
        <button id="btn-add-sparkle-layer" style="flex:1; background: linear-gradient(135deg, #ffc61a, #ff3fd0); color:#1a1a1a; font-weight:800; font-size:11px; border:1px solid #ffe694;" title="Add a standalone animated sparkle field layer (mask/erase-ready)">✨ ADD SPARKLE FIELD</button>
      </div>'''
src = sub_exact(src, old, new, 1, "toolbar button")

# ============================================================
# 6. Button handler — after btn-add-text handler
# ============================================================
old = """document.getElementById('btn-add-media').onclick = () => document.getElementById('file-media').click();"""
new = """document.getElementById('btn-add-media').onclick = () => document.getElementById('file-media').click();

document.getElementById('btn-add-sparkle-layer').onclick = () => {
  pushUndoState('Add Sparkle Layer');
  const newL = createSparkleLayer();
  appState.layers.unshift(newL);
  appState.selectedId = newL.id;
  appState.selectedIds.clear();
  appState.selectedIds.add(newL.id);
  updateUI();

  const propTab = document.querySelector('.dock-tab[data-panel="panel-props"]');
  if (propTab && !propTab.classList.contains('active')) propTab.click();
};"""
src = sub_exact(src, old, new, 1, "button handler")

# ============================================================
# 7. Panel visibility toggle in renderProperties
# ============================================================
old = """  if (mediaPanel) mediaPanel.style.display = l.type === 'media' ? 'flex' : 'none';"""
new = """  if (mediaPanel) mediaPanel.style.display = l.type === 'media' ? 'flex' : 'none';
  const sparklePanel = document.getElementById('content-sparkle');
  if (sparklePanel) sparklePanel.style.display = l.type === 'sparkle' ? 'flex' : 'none';"""
src = sub_exact(src, old, new, 1, "panel toggle")

# ============================================================
# 8. Sparkle inspector panel HTML — before content-media
# ============================================================
sparkle_panel = '''          <div id="content-sparkle" style="display:none; flex-direction:column; gap:10px;">
            <h4 style="margin:0;">✨ SPARKLE FIELD</h4>
            <div class="prop-row"><label>Field Width</label><input type="number" min="20" max="2048" step="10" id="sp-w"></div>
            <div class="prop-row"><label>Field Height</label><input type="number" min="20" max="2048" step="10" id="sp-h"></div>
            <div class="prop-row"><label>Seed</label><input type="number" min="1" max="999999" step="1" id="sp-seed"></div>
            <button id="btn-sp-reroll" class="win-btn" style="width:100%; padding:4px; font-weight:800; cursor:pointer;">🎲 Reroll Seed</button>
            <hr>
            <h4 style="margin:0;">⭐ STARS</h4>
            <div class="prop-row"><label>Count</label><input type="range" min="0" max="200" step="1" id="sp-star-count" style="flex:1;"><span id="sp-star-count-val" class="glitter-val-badge">40</span></div>
            <div class="prop-row"><label>Size Min</label><input type="range" min="1" max="40" step="1" id="sp-star-min" style="flex:1;"><span id="sp-star-min-val" class="glitter-val-badge">4</span></div>
            <div class="prop-row"><label>Size Max</label><input type="range" min="1" max="60" step="1" id="sp-star-max" style="flex:1;"><span id="sp-star-max-val" class="glitter-val-badge">12</span></div>
            <div class="prop-row"><label>Twinkle Speed</label><input type="range" min="0.1" max="6" step="0.1" id="sp-star-twin" style="flex:1;"><span id="sp-star-twin-val" class="glitter-val-badge">1.0</span></div>
            <hr>
            <h4 style="margin:0;">🌫️ DUST</h4>
            <div class="prop-row"><label>Count</label><input type="range" min="0" max="400" step="1" id="sp-dust-count" style="flex:1;"><span id="sp-dust-count-val" class="glitter-val-badge">80</span></div>
            <div class="prop-row"><label>Size</label><input type="range" min="1" max="8" step="1" id="sp-dust-size" style="flex:1;"><span id="sp-dust-size-val" class="glitter-val-badge">2</span></div>
            <hr>
            <h4 style="margin:0;">🎨 COLORS</h4>
            <div class="prop-row"><label>Mode</label>
              <select id="sp-color-mode" style="flex:1;">
                <option value="rainbow">🌈 Rainbow (by position)</option>
                <option value="single">🎨 Single Color</option>
                <option value="palette">🎭 Weighted Palette</option>
              </select>
            </div>
            <div class="prop-row" id="sp-row-single"><label>Color</label><input type="color" id="sp-color-single" value="#ffffff"></div>
            <div class="prop-row" id="sp-row-palette"><label>Palette</label><select id="sp-color-palette" style="flex:1;"></select></div>
            <div class="prop-row"><label>Hue Jitter</label><input type="range" min="0" max="1" step="0.01" id="sp-hue-jit" style="flex:1;"><span id="sp-hue-jit-val" class="glitter-val-badge">0.15</span></div>
            <div class="prop-row"><label>Brightness Jitter</label><input type="range" min="0" max="1" step="0.01" id="sp-bri-jit" style="flex:1;"><span id="sp-bri-jit-val" class="glitter-val-badge">0.25</span></div>
            <div style="font-size:9.5px; color:#888; line-height:1.3;">Shape masks, erase, glitch &amp; color adjust all apply to this field via the shared compositing pipeline — use the Mask / Color inspector sections below.</div>
          </div>

          <div id="content-media" style="display:none; flex-direction:column; gap:10px;">'''
old = '''          <div id="content-media" style="display:none; flex-direction:column; gap:10px;">'''
src = sub_exact(src, old, sparkle_panel, 1, "sparkle panel html")

# ============================================================
# 9. Sparkle property bindings — after media bindings block
# ============================================================
old = """    updateGlitterFrameStrip(l, 'media-glit-frame-strip', appState.time);
  }
  
  // Anims List"""
new = """    updateGlitterFrameStrip(l, 'media-glit-frame-strip', appState.time);
  }

  if (l.type === 'sparkle') {
    if (!l.stars) l.stars = { count: 40, sizeMin: 4, sizeMax: 12, shape: 'burst', twinkleSpeed: 1 };
    if (!l.dust) l.dust = { count: 80, size: 2 };
    if (!l.color) l.color = { mode: 'rainbow', single: '#ffffff', palette: ['#ff3fd0', '#d9b3ff', '#2fe3ff'], weights: null };

    const spBind = (id, obj, key, badgeId, oneDecimal) => {
      const el = document.getElementById(id);
      if (!el) return;
      const badge = badgeId ? document.getElementById(badgeId) : null;
      const v = obj[key] !== undefined ? obj[key] : 0;
      el.value = v;
      if (badge) badge.innerText = (oneDecimal && typeof v === 'number') ? v.toFixed(1) : v;
      el.oninput = e => {
        const p = parseFloat(e.target.value);
        obj[key] = isNaN(p) ? 0 : p;
        if (badge) badge.innerText = oneDecimal ? obj[key].toFixed(1) : obj[key];
        renderFrame(appState.time);
      };
    };

    spBind('sp-w', l, 'w');
    spBind('sp-h', l, 'h');
    spBind('sp-seed', l, 'seed');
    spBind('sp-star-count', l.stars, 'count', 'sp-star-count-val');
    spBind('sp-star-min', l.stars, 'sizeMin', 'sp-star-min-val');
    spBind('sp-star-max', l.stars, 'sizeMax', 'sp-star-max-val');
    spBind('sp-star-twin', l.stars, 'twinkleSpeed', 'sp-star-twin-val', true);
    spBind('sp-dust-count', l.dust, 'count', 'sp-dust-count-val');
    spBind('sp-dust-size', l.dust, 'size', 'sp-dust-size-val');
    spBind('sp-hue-jit', l, 'colorJitter', 'sp-hue-jit-val');
    spBind('sp-bri-jit', l, 'brightnessJitter', 'sp-bri-jit-val');

    const spReroll = document.getElementById('btn-sp-reroll');
    if (spReroll) spReroll.onclick = () => {
      l.seed = Math.floor(Math.random() * 900000) + 1000;
      const si = document.getElementById('sp-seed');
      if (si) si.value = l.seed;
      renderFrame(appState.time);
    };

    const spModeSel = document.getElementById('sp-color-mode');
    const spSingleRow = document.getElementById('sp-row-single');
    const spPaletteRow = document.getElementById('sp-row-palette');
    const syncSpColorRows = () => {
      if (spSingleRow) spSingleRow.style.display = l.color.mode === 'single' ? 'flex' : 'none';
      if (spPaletteRow) spPaletteRow.style.display = l.color.mode === 'palette' ? 'flex' : 'none';
    };
    if (spModeSel) {
      spModeSel.value = l.color.mode || 'rainbow';
      spModeSel.onchange = e => { l.color.mode = e.target.value; syncSpColorRows(); renderFrame(appState.time); };
    }
    syncSpColorRows();

    const spSingle = document.getElementById('sp-color-single');
    if (spSingle) {
      spSingle.value = l.color.single || '#ffffff';
      spSingle.oninput = e => { l.color.single = e.target.value; renderFrame(appState.time); };
    }

    const spPal = document.getElementById('sp-color-palette');
    if (spPal) {
      if (!spPal.options.length) {
        Object.keys(GLITTER_PALETTES).forEach(k => {
          if (k === 'rainbow') return;
          const opt = document.createElement('option');
          opt.value = k; opt.innerText = k;
          spPal.appendChild(opt);
        });
      }
      spPal.onchange = e => {
        const cols = GLITTER_PALETTES[e.target.value];
        if (Array.isArray(cols)) { l.color.palette = cols.slice(); renderFrame(appState.time); }
      };
    }
  }

  // Anims List"""
src = sub_exact(src, old, new, 1, "sparkle bindings")

# ============================================================
open(PATH, "w", encoding="utf-8").write(src)
print("OK — Phase 1 patch applied,", len(src), "chars")
