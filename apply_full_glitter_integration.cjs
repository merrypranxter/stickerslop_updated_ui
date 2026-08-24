const fs = require('fs');

let html = fs.readFileSync('index.html', 'utf8');

// Replace renderTextLayer with full glitter support
const startTextRenderMarker = 'function renderTextLayer(ctx, l, time) {';
const endTextRenderMarker = 'function renderMediaLayer(ctx, l, time) {';

const textRenderSection = html.substring(
  html.indexOf(startTextRenderMarker),
  html.indexOf(endTextRenderMarker)
);

const newTextAndMediaRenderSection = `function renderTextLayer(ctx, l, time) {
  let maxWidth = 0;
  let totalHeight = 0;
  l.lines.forEach(line => {
    let fbold = line.fbold ? 'bold ' : '';
    let fital = line.fital ? 'italic ' : '';
    let fontStr = getFontFallback(line.font);
    ctx.font = \`\${fital}\${fbold}\${line.size}px \${fontStr}\`;
    
    let text = line.text || '';
    if (line.tcase === 'uppercase') text = text.toUpperCase();
    if (line.tcase === 'lowercase') text = text.toLowerCase();
    if (line.tcase === 'titlecase') text = text.replace(/\\\\b\\\\w/g, c => c.toUpperCase());
    line._renderText = text;
    
    let cw = text.split('').map(c => (ctx.measureText(c).width * (line.sx || 1)) + parseFloat(line.spacing));
    let lineW = cw.reduce((a,b)=>a+b, 0) - parseFloat(line.spacing);
    line._renderW = lineW;
    line._cw = cw;
    if (lineW > maxWidth) maxWidth = lineW;
    totalHeight += (line.size * (line.sy || 1));
  });

  // 1. Sticker Plate Rendering
  if (l.plate && l.plate.en) {
    const pad = l.plate.pad || 0;
    const r = l.plate.r || 0;
    const px = -maxWidth/2 - pad;
    const ry = -l.lines[0].size/2 - pad; 
    const rw = maxWidth + pad*2;
    const rh = totalHeight + pad*2;
    
    ctx.save();
    ctx.fillStyle = l.plate.c;
    ctx.beginPath();
    ctx.roundRect(px, ry, rw, rh, r);
    ctx.fill();
    ctx.restore();
  }

  // 2. SPEC COMPLIANT 2007 GLITTER ENGINE PASS
  if (l.fillType === 'glitter') {
    const frames = getLayerGlitterFrames(l, maxWidth, totalHeight);
    const delayMs = (l.glitter && l.glitter.delayMs) ? l.glitter.delayMs : 110;
    const numFrames = (l.glitter && l.glitter.frames) ? l.glitter.frames : 3;
    const frameIndex = Math.floor((time * 1000) / delayMs) % numFrames;
    const activeFrame = frames[frameIndex] || frames[0];
    if (activeFrame) {
      ctx.save();
      ctx.drawImage(activeFrame, -activeFrame.width / 2, -activeFrame.height / 2);
      ctx.restore();
      return;
    }
  }
  
  let mainMaterial = l.fillSolid || '#ffffff';
  
  if (l.fillType === 'gradient' || l.fillType === 'rainbow') {
     let colors = [];
     if (l.fillType === 'rainbow' || (l.grad && l.grad.p === 'rainbow')) {
         colors = ['#ff0000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#ff00ff'];
     } else if (l.grad) {
         colors = [l.grad.c1, l.grad.c2, l.grad.c3].filter(Boolean);
         if (colors.length < 2) colors = ['#ff0000', '#0000ff'];
     } else {
         colors = ['#ff0000', '#0000ff'];
     }
     let angle = l.grad ? l.grad.a : 90;
     let speed = l.grad ? l.grad.s : 2;
     mainMaterial = getLoopingGradient(ctx, angle, maxWidth, totalHeight, colors, (time * speed * 0.1) % 1);
  } else if (l.fillType === 'noise') {
     let c1 = l.noise ? l.noise.c1 : '#000000';
     let c2 = l.noise ? l.noise.c2 : '#ffffff';
     let size = l.noise ? l.noise.size : 2;
     let speed = l.noise ? l.noise.s : 1;
     mainMaterial = getNoisePattern(ctx, c1, c2, size, speed, time);
  } else if (l.fillType === 'pixels') {
     let c1 = l.px ? l.px.c1 : '#ff00ff';
     let c2 = l.px ? l.px.c2 : '#00ffff';
     let c3 = l.px ? l.px.c3 : '#ffff00';
     let size = l.px ? l.px.size : 16;
     let speed = l.px ? l.px.s : 2;
     mainMaterial = getPixelsPattern(ctx, c1, c2, c3, size, speed, time);
  } else if (l.fillType === 'scanlines') {
     let c1 = l.sl ? l.sl.c1 : '#000000';
     let c2 = l.sl ? l.sl.c2 : '#00ff00';
     let size = l.sl ? l.sl.size : 4;
     let speed = l.sl ? l.sl.s : 2;
     mainMaterial = getScanlinesPattern(ctx, c1, c2, size, speed, time);
  } else if (l.fillType === 'image' || l.fillType === 'video') {
     const asset = appState.assets[l.textureId];
     if (asset) {
         let imgSource = null;
         if (asset.type === 'image' && asset.img) {
             imgSource = asset.img;
         } else if (asset.type === 'video' && asset.el && asset.el.readyState >= 2) {
             imgSource = asset.el;
         } else if (asset.type === 'gif' && asset.frames && asset.frames.length > 0) {
             const tot = asset.totalDurationMs || asset.frames.reduce((sum, f) => sum + (f.delay || 100), 0) || 1000;
             let t = (time * 1000) % tot;
             let cur = 0;
             for (let f of asset.frames) {
                 cur += (f.delay || 100);
                 if (cur >= t) { imgSource = f.canvas; break; }
             }
             if (!imgSource) imgSource = asset.frames[asset.frames.length - 1].canvas;
         }
         
         if (imgSource) {
             mainMaterial = ctx.createPattern(imgSource, 'repeat');
         }
     }
  }

  const drawPass = (colorOverride, offsetX, offsetY, isExtrude = false) => {
    ctx.save();
    ctx.translate(offsetX, offsetY);
    
    let charGlobalIndex = 0;
    
    l.lines.forEach((line, lIdx) => {
      let fbold = line.fbold ? 'bold ' : '';
      let fital = line.fital ? 'italic ' : '';
      let fontStr = getFontFallback(line.font);
      ctx.font = \`\${fital}\${fbold}\${line.size}px \${fontStr}\`;
      ctx.textBaseline = 'middle'; 
      ctx.textAlign = 'center';
      
      let chars = (line._renderText || line.text || '').split('');
      let cw = line._cw || chars.map(c => ctx.measureText(c).width + parseFloat(line.spacing));
      let tw = cw.reduce((a,b)=>a+b, 0) - parseFloat(line.spacing);
      
      let cx = -tw/2;
      
      chars.forEach((c, i) => {
        let charOffsetY = parseFloat(line.vOffset) || 0;
        let charScaleY = 1;
        let charScaleX = 1;
        
        if (l.motion && l.motion.type !== 'none') {
           const t = time * l.motion.speed - charGlobalIndex * l.motion.stagger;
           if (l.motion.type === 'wave') {
              charOffsetY += Math.sin(t) * l.motion.amt;
           } else if (l.motion.type === 'bounce') {
              charOffsetY -= Math.abs(Math.sin(t)) * l.motion.amt;
              if (Math.abs(Math.sin(t)) < 0.2) {
                 const stretch = 1 - (Math.abs(Math.sin(t)) * 5);
                 charScaleY = 1 - (stretch * 0.3);
                 charScaleX = 1 + (stretch * 0.2);
              }
           }
        }

        ctx.save();
        const charDrawX = cx + cw[i]/2 - parseFloat(line.spacing)/2;
        ctx.translate(charDrawX, charOffsetY);
        ctx.scale(charScaleX, charScaleY);
        
        let fill = mainMaterial;
        if (colorOverride) {
          fill = colorOverride;
        }
        ctx.fillStyle = fill;
        
        if (l.shb > 0 && !colorOverride && !isExtrude) {
          ctx.shadowOffsetX = l.shx; ctx.shadowOffsetY = l.shy;
          ctx.shadowBlur = l.shb; ctx.shadowColor = l.shc;
        }
        
        if (l.s3w > 0) {
          ctx.lineWidth = parseInt(l.s1w) + parseInt(l.s2w)*2 + parseInt(l.s3w)*2;
          ctx.strokeStyle = colorOverride ? colorOverride : (l.s3mat ? mainMaterial : l.s3c); 
          ctx.strokeText(c, 0, 0);
          ctx.shadowColor = 'transparent'; 
        }
        if (l.s2w > 0) {
          ctx.lineWidth = parseInt(l.s1w) + parseInt(l.s2w)*2;
          ctx.strokeStyle = colorOverride ? colorOverride : (l.s2mat ? mainMaterial : l.s2c); 
          ctx.strokeText(c, 0, 0);
          ctx.shadowColor = 'transparent'; 
        }
        if (l.s1w > 0) {
          ctx.lineWidth = l.s1w; 
          ctx.strokeStyle = colorOverride ? colorOverride : (l.s1mat ? mainMaterial : l.s1c); 
          ctx.strokeText(c, 0, 0);
          ctx.shadowColor = 'transparent';
        }
        
        ctx.fillText(c, 0, 0);
        ctx.restore();
        
        cx += cw[i];
        charGlobalIndex++;
      });
      ctx.translate(0, line.size * (line.sy || 1));
    });
    ctx.restore();
  };

  if (l.extrude && l.extrude.en) {
    const steps = l.extrude.d || 10;
    const stepX = l.extrude.x || 0;
    const stepY = l.extrude.y || 0;
    const color = l.extrude.c || '#000000';
    for (let s = steps; s >= 1; s--) {
       drawPass(color, stepX * s, stepY * s, true);
    }
  }

  if (l.glitch && l.glitch.en) {
    const dist = parseFloat(l.glitch.rgbDist) || 5;
    const timeJitter = Math.random() > 0.8 ? (Math.random()-0.5) * dist : 0;
    
    ctx.globalAlpha = 0.8;
    drawPass('#00ffff', -dist + timeJitter, timeJitter);
    drawPass('#ff0044', dist - timeJitter, -timeJitter);
    ctx.globalAlpha = 1.0;
    
    drawPass(null, timeJitter * 0.5, 0);
  } else {
    drawPass(null, 0, 0);
  }
}

function renderMediaLayer(ctx, l, time) {
  const asset = appState.assets[l.assetId];
  if (!asset) return;
  
  let imgSource = null;
  if (asset.type === 'image') imgSource = asset.img;
  if (asset.type === 'gif' && asset.frames && asset.frames.length > 0) {
    const tot = asset.totalDurationMs || asset.frames.reduce((sum, f) => sum + (f.delay || 100), 0) || 1000;
    const speed = l.speed || 1;
    let t = ((time * 1000 * speed) % tot + tot) % tot;
    if (l.reverse) {
      t = tot - t;
    }
    let cur = 0;
    for (let f of asset.frames) {
      cur += (f.delay || 100);
      if (cur >= t) {
        imgSource = f.canvas;
        break;
      }
    }
    if (!imgSource) imgSource = asset.frames[asset.frames.length - 1].canvas;
  }
  if (asset.type === 'video' && asset.el && asset.el.readyState >= 2) {
    imgSource = asset.el;
  }

  if (!imgSource) return;

  const w = imgSource.width || 300;
  const h = imgSource.height || 300;

  const offCanvas = document.createElement('canvas');
  offCanvas.width = w;
  offCanvas.height = h;
  const offCtx = offCanvas.getContext('2d', { willReadFrequently: true });
  offCtx.drawImage(imgSource, 0, 0, w, h);

  if (l.chroma && l.chroma.en) {
    const imgData = offCtx.getImageData(0, 0, w, h);
    const data = imgData.data;
    const targetR = parseInt(l.chroma.c.slice(1,3), 16) || 0;
    const targetG = parseInt(l.chroma.c.slice(3,5), 16) || 0;
    const targetB = parseInt(l.chroma.c.slice(5,7), 16) || 0;
    const tol = (l.chroma.t !== undefined ? l.chroma.t : 0.1) * 255;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i+1], b = data[i+2];
      const dist = Math.sqrt((r-targetR)**2 + (g-targetG)**2 + (b-targetB)**2);
      if (dist < tol) {
        data[i+3] = 0;
      }
    }
    offCtx.putImageData(imgData, 0, 0);
  }

  if (l.adj || l.crust) {
    const imgData = offCtx.getImageData(0, 0, w, h);
    const data = imgData.data;
    const bAdj = l.adj ? (l.adj.b || 0) : 0;
    const cAdj = l.adj ? (l.adj.c || 0) : 0;
    const sAdj = l.adj ? (l.adj.s !== undefined ? l.adj.s : 1) : 1;
    const posterize = l.crust ? (l.crust.p || 255) : 255;
    const noiseAmt = l.crust ? (l.crust.n || 0) : 0;

    for (let i = 0; i < data.length; i += 4) {
      if (data[i+3] < 10) continue;
      let r = data[i], g = data[i+1], b = data[i+2];
      r += bAdj; g += bAdj; b += bAdj;
      if (cAdj !== 0) {
        const factor = (259 * (cAdj + 255)) / (255 * (259 - cAdj));
        r = factor * (r - 128) + 128;
        g = factor * (g - 128) + 128;
        b = factor * (b - 128) + 128;
      }
      if (sAdj !== 1) {
        const gray = 0.2989 * r + 0.5870 * g + 0.1140 * b;
        r = gray + sAdj * (r - gray);
        g = gray + sAdj * (g - gray);
        b = gray + sAdj * (b - gray);
      }
      if (posterize < 255) {
        const step = 255 / Math.max(2, posterize);
        r = Math.floor(r / step) * step;
        g = Math.floor(g / step) * step;
        b = Math.floor(b / step) * step;
      }
      if (noiseAmt > 0) {
        const n = (Math.random() - 0.5) * noiseAmt;
        r += n; g += n; b += n;
      }
      data[i] = Math.max(0, Math.min(255, r));
      data[i+1] = Math.max(0, Math.min(255, g));
      data[i+2] = Math.max(0, Math.min(255, b));
    }
    offCtx.putImageData(imgData, 0, 0);
  }

  // 2007 GLITTER BEDAZZLE ENGINE PASS FOR MEDIA
  if (l.glitter && l.glitter.en) {
    const frames = getLayerGlitterFrames(l, w, h, offCanvas);
    const delayMs = l.glitter.delayMs || 110;
    const numFrames = l.glitter.frames || 3;
    const frameIndex = Math.floor((time * 1000) / delayMs) % numFrames;
    const activeFrame = frames[frameIndex] || frames[0];
    if (activeFrame) {
      ctx.save();
      ctx.drawImage(activeFrame, -activeFrame.width / 2, -activeFrame.height / 2);
      ctx.restore();
      return;
    }
  }

  ctx.save();
  ctx.drawImage(offCanvas, -w/2, -h/2, w, h);
  ctx.restore();
}
`;

html = html.replace(textRenderSection, newTextAndMediaRenderSection);

fs.writeFileSync('index.html', html, 'utf8');
console.log('Successfully updated renderTextLayer and renderMediaLayer');
