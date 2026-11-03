# Frames

A frame is a folder `thumbs-batch --frame` reads. `cart/` is the default: the Arcade's cart cover.

## frame.png

- A square PNG, as big as `size` in frame.json (512 for `cart`; 1024 suits a retina frame).
- Transparent where the screenshot shows through: the window.
- Everything else is yours: border, handle, logo, badges.
- No name or version on it. thumbs-batch draws those, so one frame serves every version.

## frame.json

| Key | What it sets |
| --- | --- |
| `size` | The frame's width and height in pixels; the thumbnail is the same. |
| `background` | Drawn first, under the screenshot. |
| `window` | `x`, `y`, `w`, `h`: where the screenshot goes. It is cropped to fill it. |
| `title` | Where the name goes: `x`, `y`, `font` (a CSS font), `fill`, `stroke`, `strokeWidth`, `align`. `split` breaks the name onto two lines at its last such character; `lineHeight` spaces them. |
| `version` | Where the version goes, the same keys as `title`. `short: true` writes up to four characters as they are, else the number it ends with. |

Drawing order: background, screenshot, frame.png, title, version.
