# Design

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="logo/logo-dark.svg">
    <img src="logo/logo.svg" alt="time machine logo: an article page with a history clock" width="112">
  </picture>
</p>

Everything visual, kept apart from the code. The page itself uses its own copy of the logo, `app/logo.svg`.

[← Back to the README](../README.md)

| Folder | What | Made with |
|---|---|---|
| <img src="icons/folder.svg" width="24" height="24" alt="" align="absmiddle"> [`logo/`](logo) | the logo in colour, dark, black and white, and a PNG | SVG paths |
| <img src="icons/search.svg" width="24" height="24" alt="" align="absmiddle"> [`icons/`](icons) | the icons of the README and `docs/details.md` | `node design/make_icons.mjs`, from [Kubai Icons](https://github.com/kubai087/kubai-icons) (MIT, see [`icons/LICENSE`](icons/LICENSE)) |
| <img src="icons/layers.svg" width="24" height="24" alt="" align="absmiddle"> [`uml/`](uml) | the class diagram and the object diagram of the data model | `python3 design/draw_uml.py` |
| <img src="icons/monitor.svg" width="24" height="24" alt="" align="absmiddle"> [`screenshots/`](screenshots) | the page, in light and dark | taken from the running page |

## Colours

They come from the page (`app/style.css`), so the README, the diagrams and the page look like one thing.

| Colour | Hex | Used for |
|---|---|---|
| majorelle | `#4436C8` | the clock, most icons |
| saffron | `#C98A12` | measurements and tools |
| red | `#B03E33` | bugs and warnings |
| green | `#23775A` | checks and tests |

## Redraw

```sh
python3 design/draw_uml.py      # after a schema change
node design/make_icons.mjs      # needs Kubai Icons cloned to ~/.claude/skills/kubai-icons
```
