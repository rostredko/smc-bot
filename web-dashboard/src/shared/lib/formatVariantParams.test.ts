import { describe, it, expect } from 'vitest';
import { formatVariantParamsShort, variantParamsToTemplateName } from './formatVariantParams';

describe('formatVariantParamsShort', () => {
    it('formats opt params in order rr, slb, tsd', () => {
        expect(formatVariantParamsShort({
            risk_reward_ratio: 2.5,
            sl_buffer_atr: 1,
            trailing_stop_distance: 0.02,
        })).toBe('rr 2.5 slb 1 tsd 0.02');
    });

    it('returns "-" for null or undefined', () => {
        expect(formatVariantParamsShort(null)).toBe('-');
        expect(formatVariantParamsShort(undefined)).toBe('-');
    });

    it('returns "-" for empty object', () => {
        expect(formatVariantParamsShort({})).toBe('-');
    });

    it('uses first 3 keys when opt params absent', () => {
        expect(formatVariantParamsShort({ a: 1, b: 2, c: 3 })).toBe('a 1 b 2 c 3');
    });
});

describe('variantParamsToTemplateName', () => {
    it('produces valid template name from opt params', () => {
        expect(variantParamsToTemplateName({
            risk_reward_ratio: 2.5,
            sl_buffer_atr: 1,
            trailing_stop_distance: 0.02,
        })).toBe('rr_2_5_slb_1_tsd_0_02');
    });

    it('returns empty string for null', () => {
        expect(variantParamsToTemplateName(null)).toBe('');
    });
});
