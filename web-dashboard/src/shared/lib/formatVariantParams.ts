/** Abbreviations for optimize params (fits in Params column). */
const PARAM_ABBREV: Record<string, string> = {
  risk_reward_ratio: 'rr',
  sl_buffer_atr: 'slb',
  trailing_stop_distance: 'tsd',
  risk_per_trade: 'rpt',
  atr_period: 'atr',
};

/** Opt params in display order (agreed: rr, slb, tsd). */
const OPT_PARAM_KEYS = ['risk_reward_ratio', 'sl_buffer_atr', 'trailing_stop_distance'] as const;

function getOptParamKeys(params: Record<string, unknown>): string[] {
  const ordered = OPT_PARAM_KEYS.filter((k) => k in params);
  return ordered.length > 0 ? ordered : Object.keys(params).slice(0, 3);
}

/**
 * Short display string for variant params, e.g. "rr 2.5 slb 1.5 tsd 0.04".
 * Uses opt params (risk_reward_ratio, sl_buffer_atr, trailing_stop_distance) when present.
 */
export function formatVariantParamsShort(params: Record<string, unknown> | null | undefined): string {
  if (!params || typeof params !== 'object') return '-';
  const keys = getOptParamKeys(params);
  const parts = keys.map((k) => {
    const abbr = PARAM_ABBREV[k] ?? k.slice(0, 3);
    const v = params[k];
    return `${abbr} ${v}`;
  });
  return parts.length ? parts.join(' ') : '-';
}

/**
 * Template name from variant params (valid: letters, numbers, dashes, underscores).
 * e.g. "rr_2_5_slb_1_5_tsd_0_04"
 * Uses opt params when present.
 */
export function variantParamsToTemplateName(params: Record<string, unknown> | null | undefined): string {
  if (!params || typeof params !== 'object') return '';
  const keys = getOptParamKeys(params);
  const parts = keys.map((k) => {
    const abbr = PARAM_ABBREV[k] ?? k.slice(0, 3);
    const v = String(params[k] ?? '').replace(/[^a-zA-Z0-9._-]/g, '_').replace(/\./g, '_');
    return `${abbr}_${v}`;
  });
  return parts.join('_');
}
