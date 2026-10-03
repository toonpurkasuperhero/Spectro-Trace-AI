'use client';

import React from 'react';
import { Eye, Layers, Wand2, Sparkles, Lock, ZoomIn, Flame, Scissors, Zap } from 'lucide-react';

// All Cloudinary AI-powered view modes
export type ViewMode =
  | 'raw'
  | 'annotated'
  | 'clean'          // e_gen_restore (AI restoration)
  | 'enhanced'       // e_improve
  | 'upscaled'       // e_upscale
  | 'heatmap'        // tint gradient map
  | 'subject_isolated' // e_background_removal (print/specimen)
  | 'waveform'       // fl_waveform (audio)
  | 'spectrogram_annotated' // audio spectrogram with overlays
  | 'remediation';   // e_gen_remove (Feature A)

interface TabDef {
  id: ViewMode;
  label: string;
  icon: React.ReactNode;
  modules?: string[];    // if set, only show for these module ids
  cldBadge?: boolean;    // show "CLD AI" pill
}

interface ViewTabsProps {
  currentView: ViewMode;
  onViewChange: (view: ViewMode) => void;
  remediationAllowed: boolean;
  remediationReason?: string | null;
  module: string;
  availableViews?: string[]; // keys present in job.assets.views
}

const ALL_TABS: TabDef[] = [
  { id: 'raw',      label: 'Raw',       icon: <Eye size={12} /> },
  { id: 'annotated', label: 'Annotated', icon: <Layers size={12} /> },
  {
    id: 'clean',
    label: 'AI Restore',
    icon: <Wand2 size={12} />,
    cldBadge: true,
  },
  {
    id: 'enhanced',
    label: 'Enhanced',
    icon: <Zap size={12} />,
    cldBadge: true,
  },
  {
    id: 'upscaled',
    label: '4× Upscale',
    icon: <ZoomIn size={12} />,
    cldBadge: true,
  },
  {
    id: 'heatmap',
    label: 'Heatmap',
    icon: <Flame size={12} />,
    modules: ['thermal', 'print', 'specimen'],
    cldBadge: true,
  },
  {
    id: 'subject_isolated',
    label: 'Isolated',
    icon: <Scissors size={12} />,
    modules: ['print', 'specimen'],
    cldBadge: true,
  },
  {
    id: 'waveform',
    label: 'Waveform',
    icon: <Eye size={12} />,
    modules: ['audio'],
    cldBadge: true,
  },
];

export default function ViewTabs({
  currentView,
  onViewChange,
  remediationAllowed,
  remediationReason,
  module,
  availableViews = [],
}: ViewTabsProps) {
  const visibleTabs = ALL_TABS.filter((tab) => {
    if (tab.modules && !tab.modules.includes(module)) return false;
    // Only show a tab if the view is available in the job assets (or it's always-on base view)
    const alwaysOn = ['raw', 'annotated', 'clean', 'enhanced', 'upscaled'];
    if (!alwaysOn.includes(tab.id) && availableViews.length > 0 && !availableViews.includes(tab.id)) return false;
    return true;
  });

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {visibleTabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onViewChange(tab.id)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
            currentView === tab.id
              ? 'bg-violet-600/30 border-violet-500/50 text-violet-300 shadow-sm'
              : 'bg-white/5 border-white/10 text-slate-400 hover:text-white hover:bg-white/10'
          }`}
        >
          {tab.icon}
          {tab.label}
          {tab.cldBadge && (
            <span className="text-[9px] px-1 py-0.5 rounded bg-cyan-900/50 text-cyan-400 border border-cyan-700/40 font-mono tracking-wide ml-0.5">
              CLD
            </span>
          )}
        </button>
      ))}

      {/* Feature A: Remediation Tab — e_gen_remove */}
      <button
        onClick={() => { if (remediationAllowed) onViewChange('remediation'); }}
        disabled={!remediationAllowed}
        title={
          !remediationAllowed
            ? remediationReason || 'Generative remediation is disabled by policy'
            : 'Cloudinary e_gen_remove: AI-illustrated defect-free preview'
        }
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
          currentView === 'remediation'
            ? 'bg-purple-600/30 border-purple-500/60 text-purple-300 shadow-sm'
            : remediationAllowed
            ? 'bg-purple-950/20 border-purple-800/40 text-purple-300 hover:bg-purple-900/30 hover:border-purple-600/50'
            : 'bg-white/[0.02] border-white/5 text-slate-600 cursor-not-allowed'
        }`}
      >
        <Sparkles size={12} className={remediationAllowed ? 'text-purple-400' : 'text-slate-600'} />
        <span>Remediation</span>
        {remediationAllowed ? (
          <span className="text-[9px] px-1 py-0.5 rounded bg-purple-900/50 text-purple-400 border border-purple-700/40 font-mono tracking-wide">
            CLD
          </span>
        ) : (
          <Lock size={10} className="text-slate-600" />
        )}
      </button>

      {!remediationAllowed && (
        <span className="text-[10px] text-slate-500 hidden sm:inline-block ml-1 italic font-mono">
          ({module === 'thermal' ? 'Radiometric Policy' : module === 'audio' ? 'Acoustic Policy' : 'No eligible defects'})
        </span>
      )}
    </div>
  );
}
