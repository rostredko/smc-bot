import { describe, expect, it } from 'vitest';

import { getConsoleLinePresentation } from './getConsoleLinePresentation';

describe('getConsoleLinePresentation', () => {
    it('marks generated signals in blue and starts a new block', () => {
        const style = getConsoleLinePresentation('[run] [2026-03-01 04:00:00] SIGNAL GENERATED: SHORT Entry=67588.30');

        expect(style.color).toBe('#00bfff');
        expect(style.margin).toBe('8px 0 0 0');
    });

    it('renders signal thoughts as nested colored context lines', () => {
        const style = getConsoleLinePresentation('[run] [2026-03-01 04:00:00] SIGNAL THESIS: Trigger: Bearish Pinbar');

        expect(style.color).toBe('#7fe7c4');
        expect(style.borderLeft).toBe('2px solid #1b6b5a');
        expect(style.paddingLeft).toBe('12px');
    });

    it('marks losing closed trades in red', () => {
        const style = getConsoleLinePresentation('[run] [2026-03-01 19:00:00] TRADE CLOSED [#8]: PnL: -152.41 (-5.39%)');

        expect(style.color).toBe('#ff4444');
        expect(style.fontWeight).toBe('bold');
        expect(style.borderBottom).toBe('1px dashed #333');
    });

    it('keeps system lines neutral by default', () => {
        const style = getConsoleLinePresentation('[run] [2026-03-01 18:00:00] FUNDING CREDIT: 0.56 on notional 5582.33 at rate 0.000100');

        expect(style.color).toBe('#aaaaaa');
        expect(style.borderLeft).toBe('none');
    });
});
