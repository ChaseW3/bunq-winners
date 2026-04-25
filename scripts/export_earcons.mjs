/**
 * Export earcons to WAV files using pure math (no Web Audio API).
 * Usage: node scripts/export_earcons.mjs
 */
import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, '..', 'frontend', 'audio');
const SR = 44100;

function encodeWav(samples) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, SR, true);
  view.setUint32(28, SR * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return Buffer.from(buffer);
}

function sine(t, freq) { return Math.sin(2 * Math.PI * freq * t); }
function saw(t, freq) { return 2 * ((freq * t) % 1) - 1; }
function lerp(a, b, t) { return a + (b - a) * t; }

function generate(duration, fn) {
  const n = Math.ceil(SR * duration);
  const samples = new Float32Array(n);
  for (let i = 0; i < n; i++) samples[i] = fn(i / SR);
  return samples;
}

const earcons = {
  greeting: generate(0.55, t => {
    const freq = lerp(523, 784, Math.min(t / 0.3, 1));
    const vol = t < 0.5 ? lerp(0.3, 0, t / 0.5) : 0;
    return sine(t, freq) * vol;
  }),
  'mic-on': generate(0.2, t => {
    const vol = t < 0.15 ? lerp(0.2, 0, t / 0.15) : 0;
    return sine(t, 880) * vol;
  }),
  'mic-off': generate(0.15, t => {
    const vol = t < 0.12 ? lerp(0.15, 0, t / 0.12) : 0;
    return sine(t, 660) * vol;
  }),
  thinking: generate(4.1, t => {
    const cycle = (t % 0.5) / 0.5;
    const vol = cycle < 0.5 ? lerp(0.08, 0.02, cycle * 2) : lerp(0.02, 0.08, (cycle - 0.5) * 2);
    const fade = t < 4 ? 1 : lerp(1, 0, (t - 4) / 0.1);
    return sine(t, 440) * vol * fade;
  }),
  success: generate(0.5, t => {
    const freq = t < 0.15 ? 659 : 880;
    const vol = lerp(0.25, 0, t / 0.45);
    return t < 0.45 ? sine(t, freq) * vol : 0;
  }),
  error: generate(0.45, t => {
    const vol = t < 0.4 ? lerp(0.2, 0, t / 0.4) : 0;
    return saw(t, 220) * vol;
  }),
  tap: generate(0.12, t => {
    const vol = t < 0.08 ? lerp(0.15, 0, t / 0.08) : 0;
    return sine(t, 600) * vol;
  }),
  unlock: generate(0.55, t => {
    const freq = t < 0.12 ? 523 : t < 0.24 ? 659 : 784;
    const vol = lerp(0.25, 0, t / 0.5);
    return t < 0.5 ? sine(t, freq) * vol : 0;
  }),
};

console.log('Exporting earcons to frontend/audio/...');
for (const [name, samples] of Object.entries(earcons)) {
  const wav = encodeWav(samples);
  const path = join(OUT, `${name}.wav`);
  writeFileSync(path, wav);
  console.log(`  ${name}.wav  (${(wav.length / 1024).toFixed(1)} KB)`);
}
console.log('Done.');
