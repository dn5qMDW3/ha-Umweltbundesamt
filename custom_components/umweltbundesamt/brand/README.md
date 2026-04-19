# Brand assets

Placeholder icon shipped with the integration. Note that **Home Assistant
does not render icons from this directory** — HA and HACS resolve
integration icons from the global
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo.
These files are here for use in the repository README and documentation.

## `icon.svg` / `icon.png`

Source is `air-filter` from [Material Design Icons](https://pictogrammers.com/library/mdi/icon/air-filter/)
by the Pictogrammers project, licensed under the Apache License 2.0. The
icon is used as a neutral stand-in for an air-quality sensor; it does not
imply endorsement by the Umweltbundesamt.

`icon.png` is a 256×256 rasterization of `icon.svg` with the path tinted in
`#008A37` (UBA green). Regenerate with:

```bash
.venv/bin/pip install cairosvg
.venv/bin/python - <<'PY'
import cairosvg
src = open('icon.svg').read().replace('<path ', '<path fill="#008A37" ')
cairosvg.svg2png(bytestring=src.encode(),
                 output_width=256, output_height=256,
                 write_to='icon.png')
PY
```
