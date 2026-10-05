'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft, Upload, Flame, Mic, Box, Microscope, ChevronRight,
  CheckCircle2, AlertCircle, Loader2, Play, FileImage, FileAudio,
  Info, Zap
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

// ── Module registry ───────────────────────────────────────────────────────────
const MODULES = [
  {
    id: 'thermal', name: 'Thermal Radiometry', domain: 'Civil / Building Inspection',
    icon: Flame, color: 'from-orange-500 to-amber-500', border: 'border-orange-500/30',
    bg: 'bg-orange-500/10',
    accepts: '.csv,.npy,.jpg,.jpeg,.png,.tiff',
    acceptTypes: ['text/csv', 'image/jpeg', 'image/png', 'image/tiff', 'application/octet-stream'],
    description: 'Radiometric FLIR CSV / NPY, non-radiometric thermal JPG with temp range, or paired visible+thermal.',
    calibrationFields: [
      { id: 'min_temp_c', label: 'Min Temp (°C)', type: 'number', defaultVal: '10' },
      { id: 'max_temp_c', label: 'Max Temp (°C)', type: 'number', defaultVal: '80' },
      { id: 'ambient_c',  label: 'Ambient Ref (°C)', type: 'number', defaultVal: '20' },
    ],
    sampleFile: { name: 'sample_radiometric_matrix.csv', type: 'text/csv' },
  },
  {
    id: 'audio', name: 'Forensic Audio', domain: 'Bio-acoustics / Splice Detection',
    icon: Mic, color: 'from-blue-500 to-cyan-500', border: 'border-blue-500/30',
    bg: 'bg-blue-500/10',
    accepts: '.wav,.mp3,.flac,.m4a',
    acceptTypes: ['audio/wav', 'audio/mpeg', 'audio/flac', 'audio/mp4'],
    description: 'WAV/MP3 speech or ambient audio. Hum detection, spectral flux splice analysis, and Mel spectrograms.',
    calibrationFields: [
      { id: 'sample_rate', label: 'Sample Rate (Hz)', type: 'number', defaultVal: '16000' },
    ],
    sampleFile: { name: 'sample_forensic_audio.wav', type: 'audio/wav' },
  },
  {
    id: 'print', name: '3D Print Defect', domain: 'Additive Manufacturing',
    icon: Box, color: 'from-purple-500 to-violet-500', border: 'border-purple-500/30',
    bg: 'bg-purple-500/10',
    accepts: '.jpg,.jpeg,.png,.tiff',
    acceptTypes: ['image/jpeg', 'image/png', 'image/tiff'],
    description: 'Per-layer bed camera photo. Optionally provide a reference "golden" layer for comparison.',
    calibrationFields: [
      { id: 'layer_index', label: 'Layer Index', type: 'number', defaultVal: '1' },
      { id: 'mm_per_px', label: 'mm / px', type: 'number', defaultVal: '0.05' },
    ],
    sampleFile: { name: 'sample_print_layer.jpg', type: 'image/jpeg' },
  },
  {
    id: 'specimen', name: 'SpecimenTrace', domain: 'Histopathology / Materials Science',
    icon: Microscope, color: 'from-emerald-500 to-teal-500', border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/10',
    accepts: '.jpg,.jpeg,.png,.tiff',
    acceptTypes: ['image/jpeg', 'image/png', 'image/tiff'],
    description: 'H&E patches, whole-slide crops, or metallography micrographs. Public de-identified data only.',
    calibrationFields: [
      { id: 'um_per_px', label: 'µm / px', type: 'number', defaultVal: '0.5' },
      { id: 'mode', label: 'Mode', type: 'select', options: ['histology', 'materials'], defaultVal: 'histology' },
    ],
    sampleFile: { name: 'sample_he_patch.jpg', type: 'image/jpeg' },
  },
];

type ModuleConfig = typeof MODULES[0];

// ── Drop zone ─────────────────────────────────────────────────────────────────
function DropZone({
  module, onFile,
}: { module: ModuleConfig; onFile: (f: File) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  }, [onFile]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
        dragging
          ? 'border-violet-500 bg-violet-500/10'
          : 'border-white/15 hover:border-white/30 hover:bg-white/[0.02]'
      }`}
    >
      <input
        ref={inputRef} type="file" className="hidden"
        accept={module.accepts}
        onChange={e => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      <div className={`w-14 h-14 mx-auto rounded-2xl flex items-center justify-center mb-4 bg-gradient-to-br ${module.color}`}>
        <Upload size={22} className="text-white" />
      </div>
      <p className="text-white font-medium mb-1">Drop file here or click to browse</p>
      <p className="text-slate-500 text-sm">{module.accepts.split(',').join(' · ')}</p>
    </div>
  );
}

// ── Calibration form ──────────────────────────────────────────────────────────
function CalibrationForm({
  fields, values, onChange,
}: {
  fields: ModuleConfig['calibrationFields'];
  values: Record<string, string>;
  onChange: (id: string, val: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {fields.map(f => (
        <div key={f.id}>
          <label className="block text-xs text-slate-400 mb-1">{f.label}</label>
          {f.type === 'select' ? (
            <select
              value={values[f.id] || f.defaultVal}
              onChange={e => onChange(f.id, e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-violet-500/50"
            >
              {(f as { options?: string[] }).options?.map(o => (
                <option key={o} value={o} className="bg-slate-900 capitalize">{o}</option>
              ))}
            </select>
          ) : (
            <input
              type={f.type} value={values[f.id] || f.defaultVal}
              onChange={e => onChange(f.id, e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-violet-500/50"
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Synthetic sample generator ─────────────────────────────────────────────────
function generateSyntheticFile(module: ModuleConfig): File {
  let content = '';
  let type = 'text/plain';

  if (module.id === 'thermal') {
    // 10×10 CSV temperature matrix
    const rows = Array.from({ length: 10 }, (_, r) =>
      Array.from({ length: 10 }, (_, c) => (20 + Math.random() * 5 + (r === 5 && c === 5 ? 35 : 0)).toFixed(1)).join(',')
    );
    content = rows.join('\n');
    type = 'text/csv';
  } else {
    content = `Synthetic ${module.name} sample — replace with real data`;
    type = 'text/plain';
  }

  return new File([content], module.sampleFile.name, { type });
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function UploadPage() {
  const router = useRouter();
  const [selectedModule, setSelectedModule] = useState<ModuleConfig>(MODULES[0]);
  const [file, setFile] = useState<File | null>(null);
  const [calValues, setCalValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<'idle' | 'uploading' | 'queued' | 'error'>('idle');
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string>('');

  const handleModule = (m: ModuleConfig) => {
    setSelectedModule(m);
    setFile(null);
    setStatus('idle');
    setError('');
  };

  const handleSubmit = async () => {
    if (!file) return;
    setStatus('uploading');
    setError('');

    try {
      const form = new FormData();
      form.append('module', selectedModule.id);
      form.append('file', file);
      // Attach calibration values as JSON field
      form.append('calibration', JSON.stringify(calValues));

      const res = await fetch(`${API_BASE}/jobs/run-local`, { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Server error');
      }
      const data = await res.json();
      setJobId(data.job_id);
      setStatus('queued');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
      setStatus('error');
    }
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-white">
      {/* Nav */}
      <div className="border-b border-white/10 bg-[#0d1424]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-4">
          <button onClick={() => router.push('/')} className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors text-sm">
            <ArrowLeft size={16} /> Dashboard
          </button>
          <div className="h-4 w-px bg-white/20" />
          <span className="font-semibold">New Analysis</span>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">

        {/* Module picker */}
        <div>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Select Module</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {MODULES.map(m => {
              const Icon = m.icon;
              const active = selectedModule.id === m.id;
              return (
                <button
                  key={m.id} onClick={() => handleModule(m)}
                  className={`p-4 rounded-2xl border text-left transition-all ${
                    active
                      ? `${m.border} ${m.bg} ring-1 ring-white/20`
                      : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
                  }`}
                >
                  <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${m.color} flex items-center justify-center mb-3`}>
                    <Icon size={16} className="text-white" />
                  </div>
                  <p className="font-medium text-sm text-white">{m.name}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{m.domain}</p>
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Left: file upload */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Upload File</h2>

            {/* Module description */}
            <div className="flex items-start gap-2 px-3 py-2.5 bg-white/[0.03] border border-white/10 rounded-xl text-xs text-slate-400">
              <Info size={12} className="mt-0.5 shrink-0 text-slate-500" />
              {selectedModule.description}
            </div>

            {file ? (
              <div className={`border rounded-2xl p-5 flex items-center gap-4 ${selectedModule.border} ${selectedModule.bg}`}>
                {file.type.startsWith('audio') ? <FileAudio size={28} className="text-blue-400" /> : <FileImage size={28} className="text-violet-400" />}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white truncate">{file.name}</p>
                  <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
                <button onClick={() => setFile(null)} className="text-slate-500 hover:text-rose-400 text-xs">Remove</button>
              </div>
            ) : (
              <DropZone module={selectedModule} onFile={setFile} />
            )}

            {/* Quick-start sample button */}
            <button
              onClick={() => setFile(generateSyntheticFile(selectedModule))}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-white/10 text-xs text-slate-400 hover:text-white hover:border-white/20 hover:bg-white/5 transition-all"
            >
              <Zap size={12} /> Use Synthetic Sample Data
            </button>
          </div>

          {/* Right: calibration + submit */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Calibration</h2>

            <CalibrationForm
              fields={selectedModule.calibrationFields}
              values={calValues}
              onChange={(id, val) => setCalValues(prev => ({ ...prev, [id]: val }))}
            />

            <div className="border border-white/10 rounded-xl p-4 bg-white/[0.02] text-xs text-slate-500 space-y-1">
              <p className="text-slate-400 font-medium mb-2 flex items-center gap-1.5"><Info size={11} /> How it works</p>
              <p>1. File is submitted to the analysis API</p>
              <p>2. Pipeline runs: Encode → Measure → Vision → Publish</p>
              <p>3. Results appear in the run detail page</p>
              <p className="mt-1 text-slate-600 font-mono truncate">API: {API_BASE}</p>
            </div>

            {error && (
              <div className="flex flex-col gap-1.5 px-3 py-2.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400">
                <div className="flex items-start gap-2">
                  <AlertCircle size={12} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
                {(error.toLowerCase().includes('failed to fetch') || error.toLowerCase().includes('network error')) && (
                  <p className="text-rose-300/70 pl-4">
                    {API_BASE.includes('localhost')
                      ? '⚠ NEXT_PUBLIC_API_BASE is not set — set it in your Vercel project settings to your backend URL (e.g. https://your-api.onrender.com)'
                      : `Cannot reach backend at ${API_BASE}. Check that the server is running and ALLOWED_ORIGINS includes your frontend URL.`
                    }
                  </p>
                )}
              </div>
            )}

            {status === 'queued' && jobId && (
              <div className="flex flex-col gap-2 px-4 py-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={13} />
                  <span className="font-medium">Analysis queued!</span>
                </div>
                <button
                  onClick={() => router.push(`/runs/${encodeURIComponent(jobId)}`)}
                  className="flex items-center gap-1.5 text-emerald-400 hover:text-white transition-colors underline underline-offset-2 w-fit"
                >
                  View run {jobId} <ChevronRight size={11} />
                </button>
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!file || status === 'uploading' || status === 'queued'}
              className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white shadow-lg shadow-violet-900/40"
            >
              {status === 'uploading' ? (
                <><Loader2 size={16} className="animate-spin" /> Uploading…</>
              ) : status === 'queued' ? (
                <><CheckCircle2 size={16} /> Queued</>
              ) : (
                <><Play size={16} /> Run Analysis</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
