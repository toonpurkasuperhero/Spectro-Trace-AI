'use client';

import React, { useState } from 'react';
import {
  Download,
  Share2,
  Monitor,
  Smartphone,
  Square,
  Sparkles,
  Layers,
  Check,
  AlertTriangle,
  ExternalLink,
  X,
  Loader2,
  FileImage
} from 'lucide-react';
import GenerativeBanner from './GenerativeBanner';

interface ExportMenuProps {
  jobId: string;
  module: string;
  currentView?: string;
  availableViews?: string[];
  apiBase?: string;
}

export default function ExportMenu({
  jobId,
  module,
  currentView = 'annotated',
  availableViews = ['raw', 'annotated', 'clean'],
  apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
}: ExportMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [profile, setProfile] = useState<'slide_16x9' | 'mobile_9x16' | 'square_1x1'>('slide_16x9');
  const [fill, setFill] = useState<'blur' | 'solid' | 'generative'>('blur');
  const [view, setView] = useState(currentView);
  const [annotated, setAnnotated] = useState(true);
  const [loading, setLoading] = useState(false);
  const [exportUrl, setExportUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Policy check for generative fill on this module
  const isGenFillAllowed = module === 'print' || (module === 'thermal' && view === 'raw');
  const genFillDenialReason =
    module === 'audio'
      ? 'Generative fill is not permitted on spectrograms (frequency axes cannot be invented).'
      : module === 'specimen'
      ? 'Generative fill is prohibited on medical specimen micrographs.'
      : module === 'thermal'
      ? 'Generative fill is only allowed on visible photographs, not radiometric thermograms.'
      : null;

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${apiBase}/jobs/${jobId}/exports?profile=${profile}&fill=${fill}&view=${view}&annotated=${annotated}`;
      const res = await fetch(url);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Export failed with status ${res.status}`);
      }
      const data = await res.json();
      setExportUrl(data.export_url);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate presentation export';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!exportUrl) return;
    const a = document.createElement('a');
    a.href = exportUrl;
    a.download = `spectrotrace_${module}_${profile}_${Date.now()}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <>
      <button
        onClick={() => {
          setIsOpen(true);
          setExportUrl(null);
          setError(null);
        }}
        className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition shadow-sm"
        title="Export presentation-ready slides or mobile alerts"
      >
        <Share2 size={13} className="text-cyan-400" />
        <span>Export Profile</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <FileImage size={18} className="text-cyan-400" />
                <div>
                  <h3 className="text-sm font-semibold text-white">Export Presentation Profiles</h3>
                  <p className="text-xs text-slate-400">
                    Adapt inspection images to standard display aspect ratios with slide chrome
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5">
              {/* Profile Selection */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  1. Target Canvas & Aspect Ratio
                </label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    onClick={() => { setProfile('slide_16x9'); setExportUrl(null); }}
                    className={`flex flex-col items-center p-3 rounded-xl border text-center transition ${
                      profile === 'slide_16x9'
                        ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <Monitor size={22} className="mb-1.5" />
                    <span className="text-xs font-medium text-white">Slide 16:9</span>
                    <span className="text-[10px] text-slate-500 mt-0.5">1920 × 1080 px</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setProfile('mobile_9x16'); setExportUrl(null); }}
                    className={`flex flex-col items-center p-3 rounded-xl border text-center transition ${
                      profile === 'mobile_9x16'
                        ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <Smartphone size={22} className="mb-1.5" />
                    <span className="text-xs font-medium text-white">Mobile 9:16</span>
                    <span className="text-[10px] text-slate-500 mt-0.5">1080 × 1920 px</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setProfile('square_1x1'); setExportUrl(null); }}
                    className={`flex flex-col items-center p-3 rounded-xl border text-center transition ${
                      profile === 'square_1x1'
                        ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <Square size={22} className="mb-1.5" />
                    <span className="text-xs font-medium text-white">Square 1:1</span>
                    <span className="text-[10px] text-slate-500 mt-0.5">1080 × 1080 px</span>
                  </button>
                </div>
              </div>

              {/* Fill Style */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  2. Background Padding Style
                </label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    onClick={() => { setFill('blur'); setExportUrl(null); }}
                    className={`p-3 rounded-xl border text-left transition ${
                      fill === 'blur'
                        ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                      Ambient Blur
                      <span className="text-[9px] px-1 rounded bg-slate-800 text-slate-300">Default</span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 leading-normal">
                      Deterministic gaussian background fill. Preserves physical honesty.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => { setFill('solid'); setExportUrl(null); }}
                    className={`p-3 rounded-xl border text-left transition ${
                      fill === 'solid'
                        ? 'bg-cyan-500/10 border-cyan-500 text-cyan-300'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-semibold text-white">Solid Charcoal</div>
                    <p className="text-[10px] text-slate-500 mt-1 leading-normal">
                      Clean dark room studio frame (#0B0F14) for technical slide decks.
                    </p>
                  </button>

                  <button
                    type="button"
                    disabled={!isGenFillAllowed}
                    onClick={() => {
                      if (isGenFillAllowed) {
                        setFill('generative');
                        setExportUrl(null);
                      }
                    }}
                    className={`p-3 rounded-xl border text-left transition relative ${
                      !isGenFillAllowed
                        ? 'opacity-40 cursor-not-allowed bg-slate-950/20 border-slate-800 text-slate-600'
                        : fill === 'generative'
                        ? 'bg-purple-900/30 border-purple-500 text-purple-200'
                        : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-semibold text-purple-300 flex items-center gap-1">
                      <Sparkles size={12} className="text-purple-400" />
                      Generative Fill
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 leading-normal">
                      {isGenFillAllowed
                        ? 'Cloudinary AI extends scenery outside the crop boundary.'
                        : 'Blocked by policy for this modality.'}
                    </p>
                  </button>
                </div>

                {!isGenFillAllowed && genFillDenialReason && (
                  <p className="text-[11px] text-amber-400/80 mt-1.5 flex items-center gap-1">
                    <AlertTriangle size={12} className="shrink-0" />
                    <span>{genFillDenialReason}</span>
                  </p>
                )}

                {fill === 'generative' && (
                  <div className="mt-3">
                    <GenerativeBanner
                      message="Background is extended using Cloudinary AI outpainting. Not a measurement, display only."
                      variant="subtle"
                    />
                  </div>
                )}
              </div>

              {/* View & Annotation Toggles */}
              <div className="grid grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Source View
                  </label>
                  <select
                    value={view}
                    onChange={(e) => { setView(e.target.value); setExportUrl(null); }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                  >
                    {availableViews.map((v) => (
                      <option key={v} value={v}>
                        {v.toUpperCase()} View
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col justify-end">
                  <label className="flex items-center gap-2 cursor-pointer pb-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={annotated}
                      onChange={(e) => { setAnnotated(e.target.checked); setExportUrl(null); }}
                      className="rounded border-slate-700 bg-slate-950 text-cyan-500 focus:ring-0"
                    />
                    <span>Include Bounding Boxes & Badges</span>
                  </label>
                </div>
              </div>

              {/* Error Notice */}
              {error && (
                <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs">
                  {error}
                </div>
              )}

              {/* Preview Box if generated */}
              {exportUrl && (
                <div className="border border-slate-800 rounded-xl overflow-hidden bg-black/60 p-2">
                  <div className="flex items-center justify-between px-2 py-1 mb-2 text-[11px] text-slate-400 border-b border-slate-800/60">
                    <span>Export Preview ({profile.replace('_', ' ').toUpperCase()})</span>
                    <span className="text-emerald-400 font-medium">Ready</span>
                  </div>
                  <div className="relative flex items-center justify-center max-h-64 overflow-hidden rounded-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={exportUrl}
                      alt="Export preview"
                      className="max-h-60 object-contain rounded"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">
                Exports include slide chrome with KPI metrics and run provenance
              </span>

              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  Close
                </button>

                {!exportUrl ? (
                  <button
                    type="button"
                    onClick={handleGenerate}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white transition shadow disabled:opacity-50"
                  >
                    {loading ? (
                      <>
                        <Loader2 size={13} className="animate-spin" />
                        <span>Rendering...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles size={13} />
                        <span>Generate Export</span>
                      </>
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleDownload}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition shadow"
                  >
                    <Download size={13} />
                    <span>Download Image</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
