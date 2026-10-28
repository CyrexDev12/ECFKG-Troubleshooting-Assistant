import { build } from 'esbuild';
await build({entryPoints:['src/editor.jsx'], bundle:true, format:'esm', minify:true,
  outfile:'../ecfkg/editor_assets/editor.js', define:{'process.env.NODE_ENV':'"production"'},
  target:['es2020'], legalComments:'linked'});
