# UI Design System — Backtrade Machine Dashboard

Authoritative guide for UI/UX decisions in `web-dashboard/`.
Describes **what exists today** (current patterns, tokens, building blocks) and **the rules every new feature must follow** so the dashboard stays visually and behaviorally coherent across agent-assisted changes.

> Scope: `web-dashboard/src/` only. Backend and engine UI are not covered (they have no UI).
> Related: [code_conventions.md](code_conventions.md) (naming, FSD placement, testing), [system_architecture.md](system_architecture.md) (data flow).

---

## 1. Design principles

1. **Research tool, not a product** — density and information clarity beat polish. Optimize for traders/operators inspecting numeric data, not casual users.
2. **One page, many widgets** — the dashboard is a single composable page (`DashboardPage`) stacked in a vertical flow. Do not introduce routes, side-nav, or multi-page shells without an explicit request.
3. **Deterministic over decorative** — no non-essential animation, no entrance transitions on data, no surprises on scroll. Motion is used only to telegraph state (hover lift on cards, opacity on disabled fields).
4. **Read-first, then act** — controls (run/stop, save template, delete) are always secondary to the data they operate on. Primary surfaces are Card → CardHeader → CardContent; actions live in `CardHeader.action` or a trailing toolbar.
5. **Semantic color, not decorative color** — colors map to states (success / warning / error / info / neutral) and to strategy modules (per-module accent). Never pick a color "because it looks good."
6. **Explicit disabled state** — when a control cannot be used (run in progress, dependency off, optimize-locked key) it must visibly communicate *why*. Silent disabling is a bug.
7. **Dark for data, light for chrome** — the app shell uses a light gradient background; dense data surfaces (console, node cards, save dialog) use dark panels. Don't mix the two inside the same component.

Anything agents add should be testable against these seven. If a change breaks one of them, push back before implementing.

---

## 2. Tech stack (what you build with)

| Concern | Library | Rule |
|---------|---------|------|
| Component library | **MUI v5** (`@mui/material`) | Default for every interactive control. Do not introduce Chakra, Ant, Radix, Mantine, shadcn, etc. |
| Styling | **Emotion** via MUI `sx` | `sx` for one-offs; `styled()` only when the style is reused across 2+ files. No CSS-in-JS libs beyond Emotion. |
| Global CSS | `src/index.css` only | Global tweaks go into `index.css`. Do not add new `.css` files — scope styles to components. |
| Icons | `@mui/icons-material` | Only. No lucide, heroicons, feather, emoji-as-icon. |
| Primary charts | **Plotly.js** (`react-plotly.js`) | OHLCV, trade scatter, anything with financial x-axis. Lazy-load. |
| Secondary charts | **Recharts** | Simple equity line, pie, bar. Never both libs for the same metric. |
| Drag & drop | `@dnd-kit/*` | Used for template reorder and strategy node reorder. No `react-dnd`, no `react-beautiful-dnd`. |
| Long lists | `react-virtuoso` | Anything over ~200 rows (console, large trade tables). `<Virtuoso>` with `scrollToIndex`. |
| HTTP | `axios` | Only HTTP client. API base from `shared/api/config.ts`. |
| Tests | Vitest + `@testing-library/react` | See §14. |

No theme provider is wired today — MUI's default theme is used with overrides via `index.css` (`.MuiCard-root`, `.MuiButton-root`, etc.) and inline `sx` props. When introducing a `ThemeProvider`, propose it as its own task; don't smuggle one in with a feature PR.

---

## 3. Frontend layers (FSD) — where to put new UI

The repo follows a loose Feature-Sliced Design layout under `web-dashboard/src/`:

```
app/         providers, orchestration, global context (BacktestProvider, ConfigProvider, ...)
pages/       page shells (DashboardPage) — compose widgets, no business logic
widgets/     large self-contained panels (config-panel, results-panel, console-output, backtest-history)
features/    user-facing interactions with their own UI + logic (trade-details modal, backtest-control, config-management)
entities/    reusable domain-specific UI (trade chart, strategy model) — no app/widget imports
shared/      cross-cutting UI (StrategyField, ChartTooltips), api/ config, lib/ utils, model/ types, const/
```

**Import rule:** a lower layer cannot import from a higher layer. `shared` cannot import `widgets`; `entities` cannot import `features`; etc. Same-layer cross-imports are allowed between sibling slices only when unavoidable — prefer lifting the shared piece into the next lower layer.

**Where does new UI go?**

| Kind of new UI | Layer | Example path |
|---|---|---|
| A new settings tab or panel on the dashboard | `widgets/<slug>/ui/<Widget>.tsx` | `widgets/risk-panel/ui/RiskPanel.tsx` |
| A small modal/flow tied to one interaction | `features/<slug>/ui/<Feature>.tsx` | `features/trade-details/ui/TradeDetailsModal.tsx` |
| A domain chart or visualization reused in 2+ widgets | `entities/<domain>/ui/<Component>.tsx` | `entities/trade/ui/TradeAnalysisChart.tsx` |
| A generic input/control reused across layers | `shared/ui/<Component>/<Component>.tsx` | `shared/ui/StrategyField/StrategyField.tsx` |

Every widget/feature folder also has at minimum a `ui/` subfolder; heavier slices also carry `model/`, `api/`, `lib/` for types, HTTP, helpers (see `widgets/backtest-history/`).

---

## 4. Design tokens

These tokens describe what the app uses *today*. Reuse them — do not invent new ones without explicit approval.

### 4.1 Colors

**App shell (light, decorative):**
- Page background: `linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)` (defined in `index.css`)
- Header band: `linear-gradient(to right, #2d2d2d, #5a5a5a, #7a7a7a)` with `border: 1px solid rgba(255,255,255,0.08)`
- Scrollbar thumb: `#ccc` → `#999` hover

**Semantic states (MUI palette keys — prefer these over hex):**

| Meaning | MUI token | Hex in code |
|---|---|---|
| Primary action / info | `primary.main` | `#1976d2` |
| Positive / running backtest | `success.main` | `#2e7d32` / `#4caf50` |
| Warning / live mode | `warning.main` | `#ed6c02` / `#ffa500` |
| Error / destructive | `error.main` | `#d32f2f` / `#f44336` / `#ff6b6b` |
| Informational text | `info.main` | `#00bfff` / `#64b5f6` |
| Neutral text | `text.secondary` | — |
| Subtle border | `rgba(255,255,255,0.12)` (dark cards) / `#e0e0e0` (light) |

**Mode identity (tabs, run controls):**
- **Backtest:** green (`#2e7d32`), icon `PlayArrow`, card tint `rgba(46,125,50,0.04)` with border `rgba(46,125,50,0.25)`
- **Live:** orange (`#ed6c02`), icon `FlashOn`, card tint `rgba(237,108,2,0.04)` with border `rgba(237,108,2,0.25)`
- **Optimize:** blue `#1565c0` / `#0d47a1`, icon `Tune`

**Strategy module accents** (used on node cards in ConfigPanel — keep stable so returning users recognize modules):

| Module | Accent |
|---|---|
| Market Context / Structure & POI | `#4fc3f7` |
| FVG | `#81c784` |
| Liquidity Sweep | `#ffb74d` |
| CHoCH | `#ba68c8` |
| Displacement | `#ef5350` |
| Entry | `#64b5f6` |
| Stop Loss | `#90a4ae` |
| Take Profit | `#ffd54f` |
| Risk | `#4db6ac` |
| Core node | `#90caf9` (inside radial `rgba(33,150,243,0.14)` halo) |

When adding a new module node, either reuse an existing accent for a sibling concept or add a new one in a separate color-palette review — don't pick ad hoc.

**Console palette (dark terminal surface):**
- Background `#0b0b0b`, border `1px solid #333` / `#1a1a1a`
- Default text `#00ff00`
- `error` `#ff6b6b`, `warning` `#ffa500`, `success` `#4caf50`, `info` `#00bfff`, `signal` `#ff00ff` (bold)
- Inset shadow `inset 0 2px 4px rgba(0,0,0,0.5)`

### 4.2 Typography

- Font family: system stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, …`) from `index.css`; monospace `'Courier New', Menlo, Monaco, Consolas`.
- Page title: `<Typography variant="h5" component="h1">` with `fontWeight: 600`, white text on header band.
- Section title: `<Typography variant="h6">` with `fontWeight: 600–700`. Inside a node card bump to `fontWeight: 700`; for the core node `h5` + `fontWeight: 800`.
- Body: default. Captions / helper text: `<Typography variant="caption">` or `variant="body2"` with `color: 'text.secondary'`.
- Numeric metrics: `<Typography variant="h6">` colored by sign — `success.main` if `value >= 0`, `error.main` otherwise (see Performance Metrics tiles in `ResultsPanel`).

### 4.3 Spacing

Use MUI spacing units (1 unit = 8px). Direct pixel values only for `height` on scrollable panes (console `height: 400`).

- Page outer padding: `py: { xs: 2, sm: 4 }` and `px: { xs: 1.5, sm: 3 }`.
- Grid container spacing: `{ xs: 2, sm: 3 }` at page level, `2` inside widgets, `1.5` inside dense node cards.
- Card header → content gap: `pb: 0.5` on header, `pt: 1.25` on content.
- Button padding: default MUI; icon-only controls use `size="small"` + `IconButton`.

### 4.4 Radii & elevation

Defined in `index.css` and reused inline:

- Cards: `borderRadius: 12px` (global override); elevated node cards: `borderRadius: 3` or `4` (`24–32px`).
- Paper blocks: `borderRadius: 8px` default; header band and tab bar: `borderRadius: 3`.
- Buttons: `borderRadius: 6px`; Chips: `borderRadius: 20px`; Accordion: `borderRadius: 8`.
- Shadows: cards `0 8px 24px rgba(0,0,0,0.08)` (hover `0 12px 32px rgba(0,0,0,0.12)`); node cards `0 18px 40px rgba(0,0,0,0.18)` (hover `0 22px 48px rgba(0,0,0,0.22)`); console `inset 0 2px 8px rgba(0,0,0,0.5)`.

### 4.5 Motion

- Card/button transitions: `transition: 'all 0.3s ease'` or `'box-shadow 0.2s ease'`. Node cards use `160ms ease` for opacity/transform/box-shadow.
- Hover lift on node cards: `transform: translateY(-2px)`. **Never** put `transform` on plain `.MuiCard-root` (see the comment in `index.css` — transform triggers repaint during scroll and caused jank).
- Disabled fields animate opacity only (`opacity: 0.6` with `transition: opacity 150ms ease`). No size changes on disable.

---

## 5. Layout patterns

### 5.1 Page shell

`pages/dashboard/ui/DashboardPage.tsx` defines the canonical page structure. Any new page should follow the same scaffold:

```tsx
<Container maxWidth="xl" sx={{ py: { xs: 2, sm: 4 }, px: { xs: 1.5, sm: 3 } }}>
  <Paper /* header band: gradient + logo tile + subtitle + WS indicator */ />
  <Paper sx={{ mb: 2 }}> <Tabs /* mode switcher */ /> </Paper>
  <Grid container spacing={{ xs: 2, sm: 3 }}>
    <Grid item xs={12}> <ConfigPanel /> </Grid>
    <Grid item xs={12}> <ConsoleOutput /> </Grid>
    <ResultsPanel />                     {/* renders its own Grid items */}
    <Grid item xs={12} mt={3}>
      <Suspense fallback={null}><BacktestHistoryList /></Suspense>
    </Grid>
  </Grid>
</Container>
```

Rules:
- Page container is always `maxWidth="xl"`. Do not add a second `Container`.
- Use MUI `Grid` (v5 `item` / `container` API). Do not switch to `Grid2` / `Unstable_Grid2` without a repo-wide migration.
- Widgets either take a full `Grid item xs={12}` or render their own `Grid item` nodes (see `ResultsPanel`) — pick one per widget.
- The header band always shows: app icon tile, title with version, subtitle with `Timeline` icon, and the WebSocket status dot (green/red with glow).

### 5.2 Tabs (run modes)

Mode switching (Backtest / Live) uses `<Tabs>` with:
- `TabIndicatorProps`: height `3`, rounded top, color matching the active mode (green/orange).
- `<Tab>` uses `icon` + `iconPosition="start"` + `textTransform: 'none'` + `fontWeight: 600`.
- Inactive color: `text.secondary`; active: mode color.

If you add a third mode tab, it must follow this exact shape and contribute a color to §4.1.

### 5.3 Grid densities

| Surface | Grid spacing | Item span |
|---|---|---|
| Page-level widgets | `spacing={{ xs: 2, sm: 3 }}` | `xs={12}` (full width) |
| Performance metric tiles | `spacing={2}` | `xs={6} md={2}` (6 tiles in a row on desktop) |
| Fields inside a node card | `spacing={1.5}` | `xs={12} md={6}` for numeric; `xs={12}` or `md={12}` for toggles (compact `md={6}`) |
| Form section inside Accordion | `spacing={2}` | same as above |

---

## 6. Component patterns (building blocks)

### 6.1 Card (primary container)

Every widget panel is a `<Card>` from MUI. Global overrides in `index.css` set rounded corners + soft shadow + hover shadow. Inside a card use:

```
<Card>
  <CardHeader
    title={/* string or <Typography> */}
    subheader={/* optional */}
    action={/* optional IconButton(s) */}
  />
  <CardContent>
    {/* content */}
  </CardContent>
</Card>
```

Do not replace `CardHeader` with hand-rolled flex rows unless you need a custom layout (e.g., title + chip row + status — see `StrategyNodeCard` in `ConfigPanel`).

**Variants in use:**
- Default `<Card>` — standard widget panel (results, history, console, config).
- `<Card variant="outlined">` with `borderRadius: 3` — node cards (per-module settings). Carries left accent bar (`::before` 4px bar colored by module), hover lift, dim-when-inactive.
- `<Card variant="outlined">` with tinted background — mode-scoped sections (`bgcolor: 'rgba(46,125,50,0.04)'` for backtest section, `rgba(237,108,2,0.04)` for live).

### 6.2 CardHeader action

Small, reversible actions live in `CardHeader.action` as `<IconButton size="small">` with a `MuiTooltip` wrapping each button. Examples: "Copy results to JSON" (`ContentCopy`), "Refresh history" (`Refresh`).

Destructive actions (delete template, delete history item) always require user confirmation (Dialog) — see §6.6.

### 6.3 Chips

Used as: status badges (inside node card headers), dependency indicators (which filter is off), and quick-info pills (`Entry: market`, `Active Modules: 4`). Rules:
- `<Chip size="small">` everywhere. Default height is fine; for extra-dense rows use `height: 22`, `fontSize: '0.72rem'`.
- Status chip in a node card header: filled variant tinted `${accent}1f`, text in `${accent}`, border `${accent}44`, `fontWeight: 700`.
- Dependency chip: `variant="outlined"`, text `text.secondary`, border `rgba(255,255,255,0.15)` (dark card) or `divider` (light card).
- Best-variant highlight in a table: `sx={{ bgcolor: 'rgba(76,175,80,0.15)' }}` on the `<TableRow>` (see Optimization Results).

### 6.4 Buttons

- Default: `<Button variant="outlined" size="small">` for secondary actions (Clear, Copy, Save).
- Primary CTA (Start Backtest, Save template): `<Button variant="contained" color="primary">`.
- Destructive (Delete template/run): `<IconButton color="error" size="small">` with `<DeleteOutline />` and an accessible `title`.
- Button text is sentence case, no trailing period. Global CSS removes uppercase.
- Always pair icon-only buttons with `title=` or wrap in `<MuiTooltip>`.

### 6.5 Form fields

**Always** use the shared `<StrategyField>` (`shared/ui/StrategyField/StrategyField.tsx`) for any field bound to the strategy config schema. It handles:
- Boolean → `<Switch>` with `FormControlLabel`.
- Enum (`schema.options`) → `<TextField select>` with `<MenuItem>`s.
- Number/text → `<TextField>` with proper `type` and float parsing.
- Tooltip via `TOOLTIP_HINTS[key]` (see `shared/const/tooltips.ts`) wrapping the whole field.
- `error`, `helperText`, `dependencyText`, `isDependent` (dim to 0.6 opacity) for disabled/dependent states.

**Do not** hand-roll a `<TextField>` for strategy params. Extend `StrategyField` if a new field type is genuinely needed.

General-run-config fields (non-schema): build with raw MUI `<TextField>` / `<Autocomplete>` but wrap the label in a `<MuiTooltip title={TOOLTIP_HINTS[key] || ...}>` so keyboard users get the same hint.

### 6.6 Dialogs

Save/confirm dialogs follow a single pattern (see Save Configuration Template in `ResultsPanel`):

```tsx
<Dialog open={...} onClose={...} PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#fff' } }}>
  <DialogTitle sx={{ borderBottom: '1px solid #333' }}>Title</DialogTitle>
  <DialogContent sx={{ mt: 2 }}>
    <DialogContentText sx={{ mb: 2, color: '#aaa' }}>One-line rationale</DialogContentText>
    <TextField autoFocus margin="dense" /* ... */ />
  </DialogContent>
  <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
    <Button onClick={close} sx={{ color: '#aaa' }}>Cancel</Button>
    <Button onClick={confirm} color="primary" variant="contained">Save</Button>
  </DialogActions>
</Dialog>
```

Rules:
- Dark paper (`#1e1e1e`) for all confirm/save dialogs.
- Destructive confirms (`delete run`, `drop template`) must use `color="error"` on the confirm button and include the item name verbatim in the body text. Never auto-confirm.
- Validation errors show via `TextField`'s `error` + `helperText`, not as a separate alert.

### 6.7 Tables

`MuiTableCell` is globally padded `12px 16px` and `<TableHead>` cells are bold on `#f5f5f5` (index.css).

Rules:
- Use `<TableContainer>` + `<Table size="small">` for dense trade/variant tables.
- Right-align action columns (`<TableCell align="right">`) and keep them to icon buttons only.
- Sortable headers use a text button with `<ArrowUpward />` / `<ArrowDownward />` (see `BacktestHistoryList`).
- Large tables (console, big trade logs) must switch to `react-virtuoso` rather than rendering thousands of rows.

### 6.8 Accordion

Used for collapsing secondary strategy sections and advanced parameters. Respect global overrides: no shadow, 1px border `#e0e0e0`, `borderRadius: 8`, `marginBottom: 12`, `::before` hidden. Title: `<Typography variant="h6">`. Do not nest accordions more than one level.

### 6.9 Console / terminal surface

`widgets/console-output/ui/ConsoleOutput.tsx` is the canonical dark terminal. Do not duplicate it. Key specs:
- Container: `height: 400`, `bgcolor: #0b0b0b`, `color: #00ff00`, `border: 1px solid #333`, `fontFamily: monospace`, `fontSize: 0.875rem`.
- Rendering: `<Virtuoso>` with `scrollToIndex` for auto-follow; toggle via "Stick to bottom" checkbox.
- Line colors derived from `getConsoleLinePresentation(line)`; the palette in §4.1 is the full set — don't add new line categories without updating that helper.
- Toolbar (Clear / Copy) lives above the pane as `<Button size="small" variant="outlined">`.

### 6.10 Tooltips

- Hover hints on fields: `<MuiTooltip title={...} arrow placement="top">` wrapping the control.
- Strategy field hints come from `shared/const/tooltips.ts` (`TOOLTIP_HINTS[key]`). If you add a strategy parameter, add its tooltip there in the same change.
- Status indicator tooltips on icon dots (WebSocket, etc.): `arrow` + plain-English state (e.g. "WebSocket Connected").

---

## 7. Charts

### 7.1 Plotly.js — primary

Use Plotly for: OHLCV candlestick, trade scatter on price, Market-Structure overlays, any view with a financial x-axis. Always lazy-load to keep initial JS bundle small:

```ts
const TradeOHLCVChart = lazy(() => import('../../../entities/trade/ui/TradeOHLCVChart'));
```

Wrap in `<Suspense fallback={null}>` (or a small spinner if the first paint matters). Match series colors to §4.1 semantic palette.

### 7.2 Recharts — secondary

Use for: equity curve line, win/loss pie, simple bar. Wrap every chart in `<ResponsiveContainer width="100%" height={N}>`.

Rules:
- Disable entry animation (`isAnimationActive={false}`) — it interferes with streaming updates and is noise on static results.
- Use the shared `<CustomTooltip>` / `<CustomPieTooltip>` from `shared/ui/ChartTooltips.tsx`, not ad-hoc per-chart tooltips.
- Wrap chart components in `React.memo` so parent re-renders don't thrash Recharts (see `MemoizedLineChart`, `MemoizedPieChart` in `ResultsPanel`).
- Do not mix Plotly and Recharts in the same visual (e.g., an equity line next to a price chart).

---

## 8. Helper text, tooltips, and empty states

- Empty states are plain `<Typography variant="body2" color="text.secondary">` inside the otherwise-rendered container (e.g., "No output yet. Start a backtest to see live results."). No illustrations, no call-to-action card.
- Helper text is terse and lives on the field itself (`helperText` prop) or as a `<Typography variant="caption" color="text.secondary">` immediately beneath the control.
- Dependency notes (what must be toggled to enable this field) go in `dependencyText` on `<StrategyField>` and also as a dashed-border info box at the card level (see `StrategyNodeCard` — `border: '1px dashed rgba(255,255,255,0.14)'`).

---

## 9. Disabled / dependency / running states

This is where a lot of agent-written UI gets sloppy. Follow these rules:

1. **Config fields during a run** — `configDisabled = isConfigDisabled || isRunning || isLiveRunning`. Apply to every field. Do not let an input be edited while a backtest or live session is active.
2. **Optimize-locked keys** — when `run_mode === 'optimize'`, the 3 `OPTIMIZE_PARAM_KEYS` become disabled in General Settings and are editable only in the Optimize section. Preserve this contract.
3. **Dependency dimming** — when a parent switch is off, descendant fields use `opacity: 0.6` via `StrategyField`'s `isDependent` and show a `dependencyText` line explaining "Enabled by <parent toggle label>". Don't hide the field — dim it so the user learns the relationship.
4. **Destructive buttons** — disabled while a run is active; a live run ignores "Stop" if `isLiveStopping` is already true; button text changes to `Stopping…` while in flight.
5. **Never silently swallow inputs** — if a field is disabled for any reason other than the mode, the tooltip/helper must say why.

---

## 10. Real-time status & indicators

- **WebSocket pill** — 12×12 dot in the page header, green/red with a matching glow (`0 0 8px rgba(…)`). Source: `useConsoleContext().websocketConnected`. Never add another WS indicator — reuse this one.
- **Progress bars** — `<LinearProgress variant="determinate" value={progress} />` with global `borderRadius: 3, height: 6`. Show only during active runs; remove once status flips to `completed` or `cancelled`.
- **Best-variant highlight** — in optimization tables the top row uses `bgcolor: 'rgba(76,175,80,0.15)'`. The summary sentence under the table title lists Sharpe / PF / Max DD / Trades / Win Rate / PnL in that order.

---

## 11. Responsiveness

Breakpoints in use today (MUI default):
- `xs` <600 · `sm` ≥600 · `md` ≥900 · `lg` ≥1200 · `xl` ≥1536

Patterns:
- Header band collapses: `flexDirection: { xs: 'column', sm: 'row' }`, gaps `2`.
- Grid items: dense numeric data uses `xs={6} md={2}`; form fields `xs={12} md={6}`; full-width widgets `xs={12}`.
- Console shrinks `height` to `300` under `max-width: 768px` via `index.css`.
- Do not introduce new breakpoints or custom media queries outside `index.css`.

---

## 12. Accessibility

- Every `<IconButton>` must have a `title`, or be wrapped in `<MuiTooltip>` that provides it. Screen readers rely on this.
- Interactive elements use native MUI components (Button, Switch, Checkbox, Tab) — do not swap them for clickable `<div>`s.
- Color alone cannot signal state — status chips always carry a label (`Running`, `Live`, `Optimize`). Red/green indicators always have a tooltip with the text state.
- Modal dialogs auto-focus the first meaningful control (`autoFocus` on the template-name field). Close on ESC (MUI default).
- Keyboard users: `@dnd-kit/core` is configured with `KeyboardSensor` + `sortableKeyboardCoordinates`. Preserve this when adding new sortable lists.

---

## 13. Performance

The dashboard is running during live/backtest sessions — UI must not stutter:

- **Avoid transforms on scroll-heavy surfaces.** `.MuiCard-root` intentionally has no `transform` on hover (comment in `index.css` is the source of truth — do not reintroduce it).
- **Memoize chart wrappers** with `React.memo` and pass stable data refs. Use `useMemo` for derived data (`equityData`, `pieData`).
- **Lazy-load heavy trees**: history list, trade modal, OHLCV chart are behind `lazy(() => import(...))` with `<Suspense fallback={null}>`. New multi-chart widgets must do the same.
- **Virtualize long lists** (`react-virtuoso` — console today, trade logs tomorrow).
- **Defer polling while invisible** — see `shouldIgnoreTransientFetchError` in `BacktestHistoryList`. Use `document.visibilityState` guards when adding new polling loops.
- **Debounce or guard duplicate fetches** via refs (`lastHistorySyncRunRef`) — copy that pattern when adding new sync loops.

---

## 14. Testing UI

- Co-locate tests: `*.test.tsx` beside the component.
- Use `@testing-library/react`. Prefer `getByRole` / `getByLabelText` / `getByText` over `getByTestId`. Add `aria-label` to controls whose role+name is otherwise ambiguous.
- Mock network with `vi.mock('…/api/historyApi')` (see existing history tests). Never let a UI test hit a real HTTP endpoint.
- For providers, render the component inside the same provider stack used in `App.tsx` (`BacktestProvider`) — existing tests show the pattern.
- Every new `widgets/*`, `features/*`, and shared `ui/*` component ships with at least one test: happy path + one error/disabled state.

---

## 15. Anti-patterns (stop signs)

| ✗ Don't | ✓ Do |
|---|---|
| Introduce a new component library (Chakra, Radix, shadcn, etc.) | Extend MUI v5; add one-off styles via `sx`. |
| Write `<div className="my-card">` with hand-rolled CSS | Use `<Card><CardHeader/><CardContent/></Card>`. |
| Hardcode colors for states (`#00c853` for success) | Use `success.main` / `error.main` / the module accent map. |
| Add a global CSS file per component | Use `sx` / `styled()`, or extend `index.css` if truly global. |
| Fetch data inside a deeply nested child component | Fetch in the widget/page level and pass data down. |
| Disable a control without explaining why | Provide `dependencyText` or a tooltip stating the cause. |
| Add an entrance animation on data load | Keep data surfaces deterministic; animate state only (hover, disabled). |
| Mix Plotly and Recharts on the same visual | Pick one per visualization; Plotly for price, Recharts for simple aggregates. |
| Create a new page route to add a feature | Add a `widget` or `feature` under the existing single `DashboardPage`. |
| Hide a disabled field | Dim (`opacity: 0.6`) and keep it visible so users learn dependencies. |

---

## 16. Checklist for any new UI work

Before claiming a UI task done, verify:

- [ ] The change lives in the correct FSD layer (§3) and respects import direction.
- [ ] Every new interactive control is an MUI component (§2).
- [ ] Colors come from the palette (§4.1) — semantic tokens preferred over hex.
- [ ] Spacing, radii, shadows match §4.3–4.4. No ad-hoc `px` unless it's a fixed viewport pane.
- [ ] Form fields for strategy schema use `<StrategyField>` with tooltips from `TOOLTIP_HINTS`.
- [ ] Disabled / dependency / running states follow §9 — no silent disabling.
- [ ] New tooltips are added to `shared/const/tooltips.ts` in the same change.
- [ ] Destructive actions are gated by a confirm Dialog styled per §6.6.
- [ ] Heavy trees use `lazy` + `Suspense`; long lists use Virtuoso; charts are memoized.
- [ ] New API calls flow through `shared/api/config.ts#API_BASE` and use `axios`.
- [ ] Tests co-located (`*.test.tsx`) cover one happy path + one disabled/error state.
- [ ] No new global CSS file; `index.css` untouched unless the change is genuinely global.
- [ ] No new dependency added to `package.json` without an explicit request.

If any box is unchecked, call it out in the task report rather than silently shipping.

---

## 17. When rules should evolve

This doc is meant to harden the current UI. If a new feature *needs* to break a rule (e.g., a real preferences page that justifies a second route, a color-scheme refactor, adding a `ThemeProvider`), write a short proposal in `docs/plans/YYYY-MM-DD-<task>.md` that lists:

1. Which rule this doc it violates.
2. Why the rule no longer fits.
3. What the replacement rule is and which existing surfaces migrate.

Do not silently drift. Drift is how dashboards end up looking like five different products glued together.
