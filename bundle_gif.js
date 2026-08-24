import esbuild from 'esbuild';
import fs from 'fs';

if (!fs.existsSync('public')) {
  fs.mkdirSync('public', { recursive: true });
}

await esbuild.build({
  entryPoints: ['src/gif-bundle-entry.js'],
  bundle: true,
  format: 'esm',
  outfile: 'public/gif-bundle.js'
});

console.log('Successfully bundled public/gif-bundle.js, size:', fs.statSync('public/gif-bundle.js').size);
