# EdgeVest brand assets

Drop this `brand/` folder into your app (e.g. `public/brand/` or `src/assets/brand/`).

## Files

| File | Use |
|---|---|
| `lockup-stacked.svg` | Primary logo. Mark / EdgeVest / tagline. Min width **96px**. |
| `lockup-stacked-reversed.svg` | Same, on dark or blue backgrounds. |
| `lockup-horizontal.svg` | Headers, navbars, email signatures. Min width **180px**. |
| `icon-tile.svg` | App icon, PWA icon, social avatar (square, slate). |
| `icon-tile-blue.svg` | Alternate square icon on signal blue. |
| `mark.svg` | Mark only, no tile. Min **26px**. |
| `mark-white.svg` | Mark only, for dark backgrounds. |
| `mark-mono-ink.svg` / `mark-mono-white.svg` | Single-colour: print, embroidery, stamps, favicon at tiny sizes. |
| `tokens.css` | Colour + type variables. |

## Referring to it in code

```html
<link rel="stylesheet" href="/brand/tokens.css" />

<!-- navbar -->
<img src="/brand/lockup-horizontal.svg" alt="EdgeVest" height="40" />

<!-- favicon + app icon -->
<link rel="icon" type="image/svg+xml" href="/brand/mark-mono-ink.svg" />
<link rel="apple-touch-icon" href="/brand/icon-tile.svg" />
```

React / Next:

```jsx
import Logo from './assets/brand/lockup-horizontal.svg';
<img src={Logo} alt="EdgeVest" className="h-10" />
```

Inline it (so it inherits `currentColor` and never flashes) by pasting the contents of `mark-mono-ink.svg` and swapping every `fill` to `currentColor`.

## Fonts

Sora 500/700 (wordmark) and IBM Plex Mono 400 (tagline), both on Google Fonts:

```html
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;700&family=IBM+Plex+Mono:wght@400&display=swap" rel="stylesheet" />
```

The SVG lockups reference these families by name — install them or the text falls back. If you can't guarantee the fonts, ask for outlined copies of the lockups.

## Colours

- Slate ink `#101821` — wordmark, tile, text
- Signal blue `#1F7FD0` — accent, the two rising candles
- Blue light `#5098E2` — candles on dark
- Bar grey `#7F8B98` — the down candle
- Paper `#F7F6F3` — page background

## Rules

- Clear space: one tile width on every side.
- Never re-space the three lines, recolour candles individually, or set the tagline in anything but Plex Mono uppercase.
- On photography, use the reversed lockup over a solid slate scrim — never straight on the image.
