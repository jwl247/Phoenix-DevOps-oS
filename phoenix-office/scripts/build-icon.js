// One-off build step: crop assets/phoenix-logo.png (838x519, full-bleed bird
// art) to a square center crop and resize to 1024x1024, so electron-builder
// can auto-generate .ico/.icns/.png icon sets from a single source file.
// Run via the electron binary (needs app.whenReady, not plain node):
//   node_modules/.bin/electron scripts/build-icon.js
const { app, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(() => {
  const srcPath = path.join(__dirname, '..', 'assets', 'phoenix-logo.png');
  const src = nativeImage.createFromPath(srcPath);
  const { width, height } = src.getSize();
  if (!width || !height) {
    console.error('Failed to load', srcPath);
    process.exit(1);
  }

  const side = Math.min(width, height);
  const x = Math.round((width - side) / 2);
  const y = Math.round((height - side) / 2);
  const cropped = src.crop({ x, y, width: side, height: side });
  const resized = cropped.resize({ width: 1024, height: 1024, quality: 'best' });

  const outDir = path.join(__dirname, '..', 'build');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'icon.png');
  fs.writeFileSync(outPath, resized.toPNG());

  console.log(`wrote ${outPath} (${resized.getSize().width}x${resized.getSize().height}, cropped from ${width}x${height} source)`);
  process.exit(0);
});
