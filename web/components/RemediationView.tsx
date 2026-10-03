'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  Sliders,
  CheckSquare,
  Square,
  AlertTriangle,
  ShieldCheck,
  RefreshCw,
  Eye,
  Layers,
  SplitSquareVertical,
  HelpCircle,
  ExternalLink,
  ChevronRight
} from 'lucide-react';
import GenerativeBanner from '@/components/GenerativeBanner';

interface Finding {
  id: string;
  label: string;
  short_label?: string;
  region_px: [number, number, number, number];
  severity?: number;
  risk_level?: string;
}

interface BlockedFinding {
  id: string;
  label: string;
  reason?: string;
}

interface RemediationViewProps {
  jobId: string;
  module: string;
  mode?: string;
  findings: Finding[];
  rawImageUrl: string;
  annotatedImageUrl?: string;
  apiBase?: string;
}

export default function RemediationView({
  jobId,
  module,
  mode = '*',
  findings = [],
  rawImageUrl,
  annotatedImageUrl,
  apiBase = 'http://localhost:8000'
}: RemediationViewProps) {
  const [remediationUrl, setRemediationUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFindingIds, setSelectedFindingIds] = useState<string[]>([]);
  const [allowedFindingIds, setAllowedFindingIds] = useState<string[]>([]);
  const [blockedFindings, setBlockedFindings] = useState<BlockedFinding[]>([]);
  
  // Slider state
  const [sliderPos, setSliderPos] = useState<number>(50);
  const [compareMode, setCompareMode] = useState<'slider' | 'remediation_only' | 'raw_only'>('slider');
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef<boolean>(false);

  // Initialize finding selection and fetch view evaluation
  useEffect(() => {
    async function evaluateAndFetch() {
      setLoading(true);
      setError(null);
      try {
        // First check policy evaluation via views endpoint
        const viewRes = await fetch(`${apiBase}/jobs/${jobId}/views`);
        if (!viewRes.ok) {
          throw new Error('Failed to evaluate job remediation availability');
        }
        const viewData = await viewRes.json();
        const eligible = viewData.remediation_status?.eligible_finding_ids || [];
        const blocked = viewData.remediation_status?.blocked_findings || [];
        
        setAllowedFindingIds(eligible);
        setBlockedFindings(blocked);
        setSelectedFindingIds(eligible);

        if (eligible.length === 0) {
          setLoading(false);
          return;
        }

        // Fetch initial remediation with all eligible findings
        await fetchRemediation(eligible);
      } catch (err: any) {
        console.error('Error initializing remediation view:', err);
        setError(err.message || 'Failed to initialize remediation view');
        setLoading(false);
      }
    }

    if (jobId) {
      evaluateAndFetch();
    }
  }, [jobId, apiBase]);

  const fetchRemediation = async (findingIds: string[]) => {
    if (findingIds.length === 0) {
      setRemediationUrl(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/jobs/${jobId}/remediation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          finding_ids: findingIds,
          mode: 'region'
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Remediation generation failed or was blocked by policy');
      }

      const data = await res.json();
      setRemediationUrl(data.remediation_url);
    } catch (err: any) {
      console.error('Remediation error:', err);
      setError(err.message || 'Failed to generate remediation view');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleFinding = (fId: string) => {
    let next: string[];
    if (selectedFindingIds.includes(fId)) {
      next = selectedFindingIds.filter(id => id !== fId);
    } else {
      next = [...selectedFindingIds, fId];
    }
    setSelectedFindingIds(next);
    fetchRemediation(next);
  };

  const handleSelectAll = () => {
    setSelectedFindingIds(allowedFindingIds);
    fetchRemediation(allowedFindingIds);
  };

  const handleDeselectAll = () => {
    setSelectedFindingIds([]);
    setRemediationUrl(null);
  };

  // Drag handlers for compare slider
  const handleMouseDown = () => {
    isDragging.current = true;
  };

  const handleTouchStart = () => {
    isDragging.current = true;
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (!isDragging.current || !containerRef.current || !e.touches[0]) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.touches[0].clientX - rect.left, rect.width));
    setSliderPos((x / rect.width) * 100);
  };

  const isHistology = module === 'specimen' && mode === 'histology';
  const isThermalOrAudio = module === 'thermal' || module === 'audio';

  return (
    <div className="space-y-4">
      {/* 1. Mandatory Generative Disclaimer Banner */}
      <GenerativeBanner />

      {/* Histology Strict Safeguard Notice */}
      {isHistology && (
        <div className="flex items-start gap-2.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs">
          <ShieldCheck size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-amber-300">Histology Clinical Safeguard:</span>{' '}
            Only imaging artifacts (dust, scratches, bubbles, stains) can be cleaned. Biological cellular
            and tissue candidate findings are strictly protected from modification.
          </div>
        </div>
      )}

      {/* Thermal & Audio Policy Exclusion Notice */}
      {isThermalOrAudio && (
        <div className="flex items-start gap-2.5 p-4 rounded-xl bg-slate-900/60 border border-white/10 text-slate-300 text-xs">
          <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-white">Remediation Policy Restriction:</span>{' '}
            {module === 'thermal'
              ? 'Thermal radiometric measurements and thermal anomalies cannot be edited, as removing them misrepresents fundamental heat transfer physics.'
              : 'Generative removal is not applicable to acoustic spectrogram frequencies or time axes.'}
          </div>
        </div>
      )}

      {/* Controls & Defect Toggles Header */}
      {!isThermalOrAudio && (
        <div className="bg-white/[0.03] border border-white/10 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Presentation Mode:
            </span>
            <div className="flex items-center bg-black/40 p-1 rounded-lg border border-white/10">
              <button
                onClick={() => setCompareMode('slider')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'slider'
                    ? 'bg-violet-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <SplitSquareVertical size={12} className="inline mr-1" />
                Compare Slider
              </button>
              <button
                onClick={() => setCompareMode('remediation_only')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'remediation_only'
                    ? 'bg-violet-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Sparkles size={12} className="inline mr-1" />
                Remediated View
              </button>
              <button
                onClick={() => setCompareMode('raw_only')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  compareMode === 'raw_only'
                    ? 'bg-violet-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <Eye size={12} className="inline mr-1" />
                Original (Raw)
              </button>
            </div>
          </div>

          {/* Quick finding count badge & refresh */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">
              Remediating <strong className="text-violet-300">{selectedFindingIds.length}</strong> of{' '}
              {allowedFindingIds.length} eligible defect regions
            </span>
            <button
              onClick={() => fetchRemediation(selectedFindingIds)}
              disabled={loading || selectedFindingIds.length === 0}
              className="p-1.5 rounded-lg border border-white/10 text-slate-400 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-40"
              title="Regenerate view"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin text-violet-400' : ''} />
            </button>
          </div>
        </div>
      )}

      {/* Main Image Comparison Canvas */}
      {!isThermalOrAudio && (
        <div
          ref={containerRef}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onMouseMove={handleMouseMove}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleMouseUp}
          onTouchMove={handleTouchMove}
          className="relative select-none bg-black/60 border border-white/10 rounded-2xl overflow-hidden min-h-[380px] max-h-[560px] flex items-center justify-center cursor-ew-resize"
        >
          {loading && (
            <div className="absolute inset-0 z-30 bg-black/60 backdrop-blur-sm flex flex-col items-center justify-center">
              <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm font-medium text-slate-200">Synthesizing defect-free reconstruction…</p>
              <p className="text-xs text-slate-400 mt-1">Applying region-based generative inpainting</p>
            </div>
          )}

          {error && (
            <div className="text-center p-8 text-rose-400">
              <AlertTriangle size={32} className="mx-auto mb-2 opacity-80" />
              <p className="font-semibold text-sm">{error}</p>
            </div>
          )}

          {/* Case 1: Raw Only */}
          {compareMode === 'raw_only' && rawImageUrl && (
            <div className="w-full h-full flex items-center justify-center">
              <img src={rawImageUrl} alt="Original Raw View" className="max-h-[540px] w-auto object-contain" />
              <span className="absolute top-4 left-4 bg-black/70 text-slate-300 text-xs px-2.5 py-1 rounded-md border border-white/10 font-mono">
                Original (Raw)
              </span>
            </div>
          )}

          {/* Case 2: Remediation Only */}
          {compareMode === 'remediation_only' && (
            <div className="w-full h-full flex items-center justify-center">
              {remediationUrl ? (
                <>
                  <img src={remediationUrl} alt="Remediated View" className="max-h-[540px] w-auto object-contain" />
                  <span className="absolute top-4 right-4 bg-purple-900/80 text-purple-200 text-xs px-2.5 py-1 rounded-md border border-purple-500/40 font-mono flex items-center gap-1.5">
                    <Sparkles size={11} className="text-purple-300" /> Remediated Preview
                  </span>
                </>
              ) : (
                <div className="text-slate-500 text-sm">Select at least one defect to remediate.</div>
              )}
            </div>
          )}

          {/* Case 3: Interactive Slider Compare (Default) */}
          {compareMode === 'slider' && rawImageUrl && (
            <div className="relative w-full h-full min-h-[380px] flex items-center justify-center overflow-hidden">
              {/* Underneath: Remediated image */}
              {remediationUrl ? (
                <img
                  src={remediationUrl}
                  alt="Remediated Defect-Free View"
                  className="w-full h-full object-contain max-h-[540px] pointer-events-none"
                />
              ) : (
                <div className="text-slate-500 text-sm py-24">Select defect regions below to preview remediation</div>
              )}

              {/* Overlaid clipped layer: Original Raw Image */}
              <div
                className="absolute inset-0 overflow-hidden pointer-events-none"
                style={{ width: `${sliderPos}%` }}
              >
                <img
                  src={rawImageUrl}
                  alt="Original Image"
                  className="w-full h-full object-contain max-h-[540px]"
                  style={{
                    width: containerRef.current ? `${containerRef.current.clientWidth}px` : '100%',
                    maxWidth: 'none'
                  }}
                />
              </div>

              {/* Split handle slider line */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-violet-400 shadow-[0_0_12px_rgba(167,139,250,0.8)] pointer-events-none"
                style={{ left: `${sliderPos}%` }}
              >
                <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 rounded-full bg-violet-600 border-2 border-white flex items-center justify-center shadow-xl">
                  <Sliders size={13} className="text-white rotate-90" />
                </div>
              </div>

              {/* Badges on left and right */}
              <div className="absolute top-4 left-4 pointer-events-none bg-black/75 text-slate-300 text-xs px-2.5 py-1 rounded-md border border-white/10 font-mono">
                Original (Raw)
              </div>
              <div className="absolute top-4 right-4 pointer-events-none bg-purple-950/80 text-purple-200 text-xs px-2.5 py-1 rounded-md border border-purple-500/40 font-mono flex items-center gap-1.5">
                <Sparkles size={11} className="text-purple-300" /> Defect Remediated
              </div>
            </div>
          )}
        </div>
      )}

      {/* Per-Finding Toggles & Policy Breakdown */}
      {!isThermalOrAudio && (
        <div className="bg-white/[0.02] border border-white/10 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
              <CheckSquare size={13} className="text-violet-400" />
              Eligible Findings for Removal
            </h4>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSelectAll}
                className="text-[11px] text-violet-400 hover:text-violet-300 underline font-medium"
              >
                Select All
              </button>
              <span className="text-slate-600">·</span>
              <button
                onClick={handleDeselectAll}
                className="text-[11px] text-slate-400 hover:text-slate-300 underline font-medium"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Eligible Findings Checklist */}
          {allowedFindingIds.length === 0 ? (
            <p className="text-xs text-slate-500 py-2">
              No defect findings are eligible for generative removal under the active module policy.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
              {findings
                .filter(f => allowedFindingIds.includes(f.id))
                .map(finding => {
                  const isChecked = selectedFindingIds.includes(finding.id);
                  return (
                    <label
                      key={finding.id}
                      onClick={() => handleToggleFinding(finding.id)}
                      className={`flex items-center gap-2.5 p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
                        isChecked
                          ? 'bg-violet-950/30 border-violet-500/50 text-white'
                          : 'bg-white/[0.02] border-white/5 text-slate-400 hover:border-white/20'
                      }`}
                    >
                      <div className="text-violet-400">
                        {isChecked ? <CheckSquare size={15} /> : <Square size={15} />}
                      </div>
                      <div className="flex-1 truncate">
                        <span className="font-medium text-slate-200 capitalize">
                          {finding.label.replace(/_/g, ' ')}
                        </span>
                        <div className="text-[10px] text-slate-500 font-mono">
                          ROI: [{finding.region_px.join(', ')}]
                        </div>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10 uppercase font-mono">
                        {finding.risk_level || 'Defect'}
                      </span>
                    </label>
                  );
                })}
            </div>
          )}

          {/* Policy-Blocked Findings List */}
          {blockedFindings.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/5">
              <h5 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-emerald-400" />
                Protected by Clinical / Physical Policy (Non-Remediated)
              </h5>
              <div className="space-y-1.5">
                {blockedFindings.map(b => (
                  <div
                    key={b.id}
                    className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-rose-500/5 border border-rose-500/20 text-[11px] text-slate-300"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-rose-300 font-semibold">{b.label}</span>
                      <span className="text-slate-500">—</span>
                      <span className="text-slate-400">{b.reason || 'Prohibited by policy engine'}</span>
                    </div>
                    <span className="text-[10px] uppercase font-mono text-rose-400/80 bg-rose-950/40 px-1.5 py-0.5 rounded border border-rose-800/40">
                      Policy Locked
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
