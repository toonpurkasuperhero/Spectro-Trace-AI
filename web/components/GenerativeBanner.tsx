'use client';

import React from 'react';
import { Sparkles, Info } from 'lucide-react';

interface GenerativeBannerProps {
  message?: string;
  variant?: 'banner' | 'pill' | 'subtle';
  className?: string;
}

export const GENERATIVE_DISCLAIMER_TEXT =
  "AI-generated illustration. Not a measurement, not a repair specification, not used by the analysis.";

export default function GenerativeBanner({
  message = GENERATIVE_DISCLAIMER_TEXT,
  variant = 'banner',
  className = ''
}: GenerativeBannerProps) {
  if (variant === 'pill') {
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm ${className}`}>
        <Sparkles size={11} className="text-purple-400" />
        AI-Generated (Display Only)
      </span>
    );
  }

  if (variant === 'subtle') {
    return (
      <div className={`flex items-center gap-2 text-xs text-purple-300/80 bg-purple-950/30 border border-purple-800/40 px-3 py-1.5 rounded-lg ${className}`}>
        <Sparkles size={13} className="text-purple-400 shrink-0" />
        <span>{message}</span>
      </div>
    );
  }

  return (
    <div className={`flex items-start gap-2.5 p-3 rounded-xl bg-purple-950/40 border border-purple-700/50 text-purple-200 text-xs shadow-lg shadow-purple-950/20 ${className}`}>
      <Sparkles size={16} className="text-purple-400 mt-0.5 shrink-0 animate-pulse" />
      <div className="flex-1">
        <div className="font-semibold text-purple-200 flex items-center gap-1.5">
          Generative Display Layer
          <span className="text-[10px] font-normal uppercase tracking-wider px-1.5 py-0.2 rounded bg-purple-900/60 text-purple-300 border border-purple-600/40">
            Non-Measurement
          </span>
        </div>
        <p className="mt-0.5 text-purple-300/90 leading-relaxed">
          {message}
        </p>
      </div>
      <Info size={14} className="text-purple-400/60 shrink-0 mt-0.5" />
    </div>
  );
}
