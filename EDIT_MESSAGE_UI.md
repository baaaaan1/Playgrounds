# Edit Message as a Copy

## Layout and Behavior

- Resizable modal dialog: 640 x 480 logical pixels by default; minimum 400 x 420.
- Use the application's themed 42 px title bar, with a close button and no minimize/maximize controls. Do not use system-default input-dialog chrome.
- Content padding: 24 px. Vertical spacing and action-button gap: 12 px.
- Heading: 20 px, weight 600. Labels and helper text: 13 px. Editor: 14 px. Use the application's Segoe UI Variable Text / Segoe UI / Inter / sans-serif stack.
- Explain the scope above the editor: "The original chat stays unchanged. Later messages will not be copied."
- Give the editor an accessible "Message" name, an associated visible label, and the scope description. Preserve plain text, whitespace, and line breaks; never interpret message content as HTML.
- Editor: expanding multiline surface, wrapping long lines and scrolling vertically. Radius: 10 px. Internal padding: 12 px.
- Actions: Cancel followed by Send copy, aligned right. Minimum height: 44 px. Radius: 8 px. Minimum content width: 80 px, with 14 px horizontal padding.
- Initial focus goes to the editor. Enter inserts a newline. Tab moves to Cancel, then Send copy. Ctrl+Enter explicitly submits. Esc, Cancel, and the title-bar close button reject the edit.
- Disable Send copy for empty or whitespace-only input. Keyboard submission uses the same validation. Enter never implicitly activates an action while editing.
- Submitting creates a separate conversation using the existing copy/fork behavior. Canceling never changes the source message or its draft.
- Theme colors are resolved from the active application theme when the modal opens. App-wide QSS controls the surfaces, text, selection, borders, and button states; the title bar receives the same theme tokens.

## Color Palette

| Role / CSS Variable | Qt Token | Light | Dark |
| --- | --- | --- | --- |
| `--edit-bg` | `bg` | `#F6F7FA` | `#0E1014` |
| `--edit-caption-bg` | `bg_alt` | `#EEF0F5` | `#111419` |
| `--edit-surface` | `surface` | `#FFFFFF` | `#171B22` |
| `--edit-hover` | `surface_hover` | `#F1F3F8` | `#1D232E` |
| `--edit-pressed` | `surface_active` | `#E6EAF2` | `#252D3B` |
| `--edit-text` | `text` | `#1A1F2B` | `#E7EAF1` |
| `--edit-muted` | `text_muted` | `#5F6878` | `#8B94A7` |
| `--edit-border` | `control_border` | `#7B8494` | `#707D94` |
| `--edit-shell-border` | `border_strong` | `#CBD2E0` | `#323C4D` |
| `--edit-focus` | `accent_strong` | `#87311C` | `#FF896A` |
| `--edit-primary` | `accent` | `#FF896A` | `#FF896A` |
| `--edit-primary-hover` | `accent_hover` | `#F57D5E` | `#FF9D83` |
| `--edit-on-primary` | `accent_text` | `#241610` | `#241610` |

Disabled actions use `--edit-pressed`, `--edit-muted`, and `--edit-border`. Selected editor text uses `--edit-primary` and `--edit-on-primary`. Primary-button pressed fill equals its hover fill.

Use the stronger control border for interactive controls, not the decorative shell border. Coral is a fill, not small body text on light surfaces. The darker coral companion is the light-mode focus color.

## Contrast Ratios

Computed using WCAG relative luminance for opaque sRGB colors, rounded to two decimals. Thresholds are 4.5:1 for normal text and 3:1 for control boundaries and focus indicators. These checks cover the specified color pairs, not a certification of the application's full accessibility.

| Foreground / Background | Light | Dark | Minimum |
| --- | ---: | ---: | ---: |
| Primary text / panel | 15.38:1 | 15.81:1 | 4.5:1 |
| Helper text / panel | 5.24:1 | 6.25:1 | 4.5:1 |
| Editor text / editor surface | 16.47:1 | 14.34:1 | 4.5:1 |
| Secondary label / hover fill | 14.84:1 | 13.09:1 | 4.5:1 |
| Secondary label / pressed fill | 13.66:1 | 11.49:1 | 4.5:1 |
| Control border / panel | 3.52:1 | 4.58:1 | 3:1 |
| Control border / editor surface | 3.77:1 | 4.15:1 | 3:1 |
| Control border / hover fill | 3.40:1 | 3.79:1 | 3:1 |
| Control border / pressed fill | 3.13:1 | 3.33:1 | 3:1 |
| Editor/secondary focus / panel | 7.88:1 | 8.20:1 | 3:1 |
| Editor/secondary focus / editor surface | 8.45:1 | 7.43:1 | 3:1 |
| Secondary focus / hover fill | 7.61:1 | 6.79:1 | 3:1 |
| Secondary focus / pressed fill | 7.00:1 | 5.96:1 | 3:1 |
| Primary label or selection text / coral fill | 7.55:1 | 7.55:1 | 4.5:1 |
| Primary label / hover or pressed fill | 6.66:1 | 8.69:1 | 4.5:1 |
| Disabled label / disabled fill | 4.66:1 | 4.54:1 | 4.5:1* |

*Disabled controls are exempt from the normal WCAG contrast requirement, but this design retains readable text.

Editor and secondary-action focus replaces the 1 px border with a 2 px `--edit-focus` border. Padding decreases by 1 px on each side to prevent content movement. Primary-action focus uses a 2 px `--edit-on-primary` border: it contrasts with the button fill at 7.55:1 normally, 6.66:1 on light-mode hover, and 8.69:1 on dark-mode hover. In dark mode the coral button fill defines the normal button boundary; its coral border is intentionally the same color as its fill.

## CSS Variables

The application is PyQt6, not a browser: runtime styling is QSS in `app/ui/theme.py`, with `@token` substitution. The following CSS custom properties are an equivalent specification for web implementations; Qt does not consume `var()` or `[data-theme]` selectors.

```css
:root,
[data-theme="light"] {
  color-scheme: light;
  --edit-bg: #f6f7fa;
  --edit-caption-bg: #eef0f5;
  --edit-surface: #ffffff;
  --edit-hover: #f1f3f8;
  --edit-pressed: #e6eaf2;
  --edit-text: #1a1f2b;
  --edit-muted: #5f6878;
  --edit-border: #7b8494;
  --edit-shell-border: #cbd2e0;
  --edit-focus: #87311c;
  --edit-primary: #ff896a;
  --edit-primary-hover: #f57d5e;
  --edit-on-primary: #241610;
}

[data-theme="dark"] {
  color-scheme: dark;
  --edit-bg: #0e1014;
  --edit-caption-bg: #111419;
  --edit-surface: #171b22;
  --edit-hover: #1d232e;
  --edit-pressed: #252d3b;
  --edit-text: #e7eaf1;
  --edit-muted: #8b94a7;
  --edit-border: #707d94;
  --edit-shell-border: #323c4d;
  --edit-focus: #ff896a;
  --edit-primary: #ff896a;
  --edit-primary-hover: #ff9d83;
  --edit-on-primary: #241610;
}

.edit-panel {
  background: var(--edit-bg);
  color: var(--edit-text);
  border: 1px solid var(--edit-shell-border);
  font-family: "Segoe UI Variable Text", "Segoe UI", Inter, sans-serif;
}

.edit-panel__caption { background: var(--edit-caption-bg); }
.edit-panel__help { color: var(--edit-muted); }

.edit-panel textarea,
.edit-panel button {
  box-sizing: border-box;
  background: var(--edit-surface);
  color: var(--edit-text);
  border: 1px solid var(--edit-border);
}

.edit-panel textarea {
  padding: 12px;
  border-radius: 10px;
  font: inherit;
  font-size: 14px;
}

.edit-panel button {
  min-height: 44px;
  min-width: 110px;
  padding: 8px 14px;
  border-radius: 8px;
  font: inherit;
  font-size: 13px;
}

.edit-panel button:hover { background: var(--edit-hover); }
.edit-panel button:active { background: var(--edit-pressed); }

.edit-panel textarea:focus-visible,
.edit-panel button:focus-visible {
  outline: 2px solid var(--edit-focus);
  outline-offset: 2px;
}

.edit-panel .edit-panel__send {
  background: var(--edit-primary);
  color: var(--edit-on-primary);
  border-color: var(--edit-focus);
  font-weight: 600;
}

.edit-panel .edit-panel__send:hover,
.edit-panel .edit-panel__send:active {
  background: var(--edit-primary-hover);
}

.edit-panel .edit-panel__send:focus-visible {
  border: 2px solid var(--edit-on-primary);
  padding: 7px 13px;
}

.edit-panel .edit-panel__send:disabled {
  background: var(--edit-pressed);
  color: var(--edit-muted);
  border-color: var(--edit-border);
  opacity: 1;
  cursor: not-allowed;
}

.edit-panel textarea::selection {
  background: var(--edit-primary);
  color: var(--edit-on-primary);
}
```

The web mapping adds an external `:focus-visible` outline without changing layout. Qt uses the internal border treatment described above because its QSS focus-state support differs from browser CSS.

## Verification

- `tests/test_edit_message_dialog.py`: rendered light/dark colors, editor and action focus, selection palette, hover/disabled states, three window sizes, long-line wrapping, keyboard navigation, blank-input validation, and cancellation.
- `tests/test_theme.py`: normal-text and non-text contrast thresholds across both palettes and interaction states.
- `tests/test_conversation_features.py`: accepted edits create copies without altering the source; canceled edits preserve the original conversation and draft.
