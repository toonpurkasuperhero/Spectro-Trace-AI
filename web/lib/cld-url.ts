/**
 * SpectroTrace AI - Cloudinary URL Builder (Frontend)
 * Mirrors backend URL generation to allow dynamic client-side layer manipulation,
 * opacity sliders, view toggles, and tiling without roundtrips.
 */

export interface FindingBox {
  id: string;
  label: string;
  short_label?: string;
  region_px: [number, number, number, number]; // [x, y, w, h]
  risk_level: 'low' | 'medium' | 'high';
}

const COLOR_MAP: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'yellow',
};

/**
 * Builds dynamic URL for view switching (raw, annotated, cosmetic) and opacity adjustment.
 */
export function buildViewUrl(params: {
  cloudName: string;
  publicId: string;
  resourceType?: 'image' | 'video';
  viewMode: 'raw' | 'annotated' | 'clean';
  opacity?: number;
  findings?: FindingBox[];
  overlayAsset?: string;
}): string {
  const {
    cloudName,
    publicId,
    resourceType = 'image',
    viewMode,
    opacity = 40,
    findings = [],
    overlayAsset = 'sys:pixel',
  } = params;

  const base = `https://res.cloudinary.com/${cloudName}/${resourceType}/authenticated`;
  const cleanPid = publicId.startsWith('/') ? publicId.slice(1) : publicId;

  if (viewMode === 'raw') {
    return `${base}/f_auto,q_auto/${cleanPid}`;
  }

  if (viewMode === 'clean') {
    // Cosmetic view with enhancement/cleanup
    return `${base}/e_gen_restore/f_auto,q_auto/${cleanPid}`;
  }

  // Annotated view with URL-composed finding boxes and text labels
  const transformParts: string[] = ['f_auto,q_auto'];

  for (const f of findings) {
    const [x, y, w, h] = f.region_px;
    const color = COLOR_MAP[f.risk_level] || 'yellow';
    const label = encodeURIComponent(f.short_label || f.label);

    // Bounding box rectangle layer
    transformParts.push(
      `l_${overlayAsset},w_${w},h_${h},c_scale,e_colorize:100,co_${color},o_${opacity}/fl_layer_apply,g_north_west,x_${x},y_${y}`
    );

    // Text label layer
    transformParts.push(
      `l_text:Arial_14_bold:${label},co_white,b_rgb:000000a0/fl_layer_apply,g_north_west,x_${x},y_${Math.max(
        0,
        y - 20
      )}`
    );
  }

  return `${base}/${transformParts.join('/')}/${cleanPid}`;
}

/**
 * Builds tile crop URL for deep zoom
 */
export function buildTileUrl(params: {
  cloudName: string;
  publicId: string;
  x: number;
  y: number;
  width: number;
  height: number;
}): string {
  const { cloudName, publicId, x, y, width, height } = params;
  const base = `https://res.cloudinary.com/${cloudName}/image/authenticated`;
  const cleanPid = publicId.startsWith('/') ? publicId.slice(1) : publicId;
  return `${base}/c_crop,x_${x},y_${y},w_${width},h_${height},f_auto,q_auto/${cleanPid}`;
}

/**
 * Builds visible + thermal opacity fusion URL
 */
export function buildFusedUrl(params: {
  cloudName: string;
  visiblePublicId: string;
  thermalPublicId: string;
  opacity: number;
}): string {
  const { cloudName, visiblePublicId, thermalPublicId, opacity } = params;
  const base = `https://res.cloudinary.com/${cloudName}/image/authenticated`;
  const cleanVis = visiblePublicId.startsWith('/') ? visiblePublicId.slice(1) : visiblePublicId;
  // In Cloudinary overlays, folder slashes become colons
  const cldOverlay = thermalPublicId.replace(/\//g, ':');
  return `${base}/l_${cldOverlay},o_${opacity}/fl_layer_apply,g_center,f_auto,q_auto/${cleanVis}`;
}
