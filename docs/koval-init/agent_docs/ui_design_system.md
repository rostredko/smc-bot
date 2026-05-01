# UI Design System — Koval

## Stack

- MUI v5 (`@mui/material`) + Emotion
- react-flow (`@xyflow/react`) for Block Builder canvas
- Plotly.js for charts
- Vite + TypeScript

## Theme

Dark theme by default. Configure in `dashboard/src/app/providers/ThemeProvider.tsx`.

```tsx
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#f5a623' },   // amber — "forge" color
    secondary: { main: '#4fc3f7' }, // light blue
    background: {
      default: '#0d1117',
      paper: '#161b22',
    },
  },
})
```

## Block Builder color tokens

Each block category has a header color:

| Category | Color | Token |
|----------|-------|-------|
| `signal` | Green | `#2e7d32` |
| `filter` | Blue | `#1565c0` |
| `entry` | Amber | `#f57f17` |
| `exit` | Red | `#c62828` |
| `risk` | Purple | `#6a1b9a` |

Use via CSS variables on `BlockNode.tsx`:
```tsx
const CATEGORY_COLORS = {
  signal: '#2e7d32',
  filter: '#1565c0',
  entry: '#f57f17',
  exit: '#c62828',
  risk: '#6a1b9a',
}
```

## JSON Schema → Form mapping (SchemaForm.tsx)

| JSON Schema type | MUI component |
|-----------------|---------------|
| `integer` + `minimum` + `maximum` | `Slider` |
| `number` + `minimum` + `maximum` | `Slider` (step 0.1) |
| `boolean` | `Switch` |
| `string` + `enum` | `Select` |
| `string` (free) | `TextField` |
| `object` | `Accordion` section |

## Component rules

- Use `sx` prop for one-off styles
- Use `styled()` only for components used in 2+ files
- No hardcoded color hex values outside the theme and design tokens above
- No inline `style={{}}` — always `sx`

## File naming

- Components: `PascalCase.tsx`
- Hooks: `useCamelCase.ts`
- Utilities: `camelCase.ts`
- Feature directories: `kebab-case/`
