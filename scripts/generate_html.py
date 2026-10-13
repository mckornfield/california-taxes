"""Generate index.html (repo root, for GitHub Pages) from all executed notebooks."""

import base64
import json
import re
import struct
import uuid
from pathlib import Path


# Plotly 6.x serializes numeric arrays as base64-encoded binary (bdata/dtype).
# Plotly.js in the browser cannot decode this format, so we convert back to
# plain lists here before writing the HTML.
_DTYPE_FMT = {
    "f8": ("d", 8),
    "f4": ("f", 4),
    "i4": ("i", 4),
    "i2": ("h", 2),
    "i1": ("b", 1),
    "u4": ("I", 4),
    "u2": ("H", 2),
    "u1": ("B", 1),
    "i8": ("q", 8),
    "u8": ("Q", 8),
}


def _decode_bdata(obj):
    """Recursively decode Plotly 6.x bdata binary arrays to plain lists."""
    if isinstance(obj, dict):
        if "bdata" in obj and "dtype" in obj:
            dtype = obj["dtype"]
            raw = base64.b64decode(obj["bdata"])
            if dtype in _DTYPE_FMT:
                fmt_char, size = _DTYPE_FMT[dtype]
                n = len(raw) // size
                return [_round(v) for v in struct.unpack(f"<{n}{fmt_char}", raw)]
            return obj
        return {k: _decode_bdata(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_bdata(item) for item in obj]
    return _round(obj)


def _round(v):
    """5 significant digits: plenty for charts, keeps the page a fraction of the size."""
    return float(f"{v:.5g}") if isinstance(v, float) else v

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS_DIR = ROOT / "notebooks"

SECTIONS = [
    ("State government", [
        "01_state_data_overview.ipynb",
        "02_state_revenue.ipynb",
        "03_state_spending.ipynb",
        "04_state_revenue_vs_spending.ipynb",
    ]),
    ("Local government", [
        "05_local_revenue.ipynb",
        "06_local_taxes.ipynb",
        "07_local_spending.ipynb",
        "08_school_districts.ipynb",
        "09_county_maps.ipynb",
    ]),
    ("Putting it together", [
        "10_tax_burden.ipynb",
    ]),
    ("Property tax and Proposition 13", [
        "11_property_assessed_values.ipynb",
    ]),
    ("Federal dollars", [
        "12_federal_dollars.ipynb",
    ]),
    ("Explore", [
        "13_city_county_explorer.ipynb",
    ]),
]


def _inline(text: str) -> str:
    """Minimal inline markdown: **bold**, `code`, [text](url)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)


def extract_outputs(nb_path: Path) -> str:
    nb = json.loads(nb_path.read_text())
    parts = []
    for cell in nb.get("cells", []):
        if cell["cell_type"] == "markdown":
            source = _inline("".join(cell.get("source", [])))
            html_lines = []
            in_list = False
            for line in source.split("\n"):
                if line.startswith("- "):
                    if not in_list:
                        html_lines.append("<ul>")
                        in_list = True
                    html_lines.append(f"<li>{line[2:]}</li>")
                else:
                    if in_list:
                        html_lines.append("</ul>")
                        in_list = False
                    if line.startswith("### "):
                        html_lines.append(f"<h4>{line[4:]}</h4>")
                    elif line.startswith("## "):
                        html_lines.append(f"<h3>{line[3:]}</h3>")
                    elif line.startswith("# "):
                        html_lines.append(f"<h2>{line[2:]}</h2>")
                    elif line.startswith("**") and line.endswith("**") and len(line) > 4:
                        html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
                    elif line.strip():
                        html_lines.append(f"<p>{line}</p>")
            if in_list:
                html_lines.append("</ul>")
            parts.append("\n".join(html_lines))
            continue

        if cell["cell_type"] != "code":
            continue

        for output in cell.get("outputs", []):
            otype = output.get("output_type", "")
            if otype in ("display_data", "execute_result"):
                data = output.get("data", {})
                if "application/vnd.plotly.v1+json" in data:
                    plotly_data = data["application/vnd.plotly.v1+json"]
                    div_id = f"plotly-{uuid.uuid4().hex[:12]}"
                    fig_data = _decode_bdata(plotly_data.get("data", []))
                    fig_json = json.dumps(fig_data, separators=(",", ":")).replace("</script>", r"<\/script>")
                    layout = _decode_bdata(plotly_data.get("layout", {}))
                    layout.setdefault("autosize", True)
                    height = int(layout.get("height") or 560)
                    layout_json = json.dumps(layout, separators=(",", ":")).replace("</script>", r"<\/script>")
                    parts.append(
                        f'<div id="{div_id}" style="width:100%;height:{height}px;"></div>\n'
                        f"<script>Plotly.newPlot('{div_id}', {fig_json}, {layout_json}, "
                        f"{{responsive: true}}).then(fitMobile);</script>"
                    )
                elif "text/html" in data:
                    parts.append("".join(data["text/html"]))
                elif "text/plain" in data:
                    text = "".join(data["text/plain"])
                    parts.append(f"<pre>{text}</pre>")
            elif otype == "stream":
                text = "".join(output.get("text", []))
                if text.strip():
                    parts.append(f"<pre>{text}</pre>")
    return "\n".join(parts)


PLOTLY_JS = "https://cdn.plot.ly/plotly-3.0.1.min.js"

# On narrow screens the right-hand legend squeezes the plot and the toggle buttons run off screen:
# move the legend under the chart, turn button rows into a dropdown, and undo it when the screen widens.
FIT_MOBILE_JS = """
function wrapText(t, n) {  // break at spaces so a line has at most ~n characters
  var words = t.split(' '), lines = [], cur = '';
  words.forEach(function (w) {
    if ((cur + ' ' + w).trim().length > n && cur) { lines.push(cur); cur = w; } else { cur = (cur + ' ' + w).trim(); }
  });
  lines.push(cur);
  return lines;
}
function mobileTitle(t0, width) {  // 'Title<br><sup>Subtitle</sup>' -> wrapped lines
  var parts = t0.split('<br><sup>'), head = wrapText(parts[0], Math.floor(width / 9)), sub = [];
  if (parts[1]) sub = wrapText(parts[1].replace('</sup>', ''), Math.floor(width / 6.3));
  var text = head.join('<br>') + (sub.length ? '<br><sup>' + sub.join('</sup><br><sup>') + '</sup>' : '');
  return { text: text, lines: head.length + sub.length };
}
function fitMobile(gd) {
  var narrow = gd.clientWidth < 640;
  if (gd._narrow === narrow) return;
  if (gd._h0 === undefined) {  // remember the desktop layout the first time
    gd._h0 = parseInt(gd.style.height, 10) || 560;
    gd._l0 = (gd.layout.margin || {}).l;
    gd._t0 = (gd.layout.margin || {}).t;
    gd._title0 = (gd.layout.title || {}).text;
    gd._btn = (gd.layout.updatemenus || []).map(function (m, i) { return m.type === 'buttons' ? i : -1; }).filter(function (i) { return i >= 0; });
  }
  var first = gd._narrow === undefined;
  gd._narrow = narrow;
  if (first && !narrow) return;
  var u = {};
  if (narrow) {
    u['legend.orientation'] = 'h'; u['legend.x'] = 0; u['legend.y'] = -0.2; u['legend.yanchor'] = 'top';
    u['margin.r'] = 10; u['margin.l'] = 55; u['margin.b'] = 230;
    if (gd._title0) {
      var mt = mobileTitle(gd._title0, gd.clientWidth);
      u['title.text'] = mt.text; u['title.y'] = 0.98; u['title.pad.t'] = 8;
      u['margin.t'] = (gd._t0 || 90) + Math.max(0, mt.lines - 2) * 17;
    }
    gd.style.height = (gd._h0 + 170) + 'px';
  } else {
    u['legend.orientation'] = 'v'; u['legend.x'] = 1.01; u['legend.y'] = 1; u['legend.yanchor'] = 'auto';
    u['margin.r'] = 20; u['margin.l'] = gd._l0 || 60; u['margin.b'] = 60;
    if (gd._title0) { u['title.text'] = gd._title0; u['title.y'] = 0.97; u['title.pad.t'] = 0; u['margin.t'] = gd._t0 || 90; }
    gd.style.height = gd._h0 + 'px';
  }
  // Plotly leaves the old button row in the DOM if a menu's type changes in place, so clear the menus first.
  var menus = JSON.parse(JSON.stringify(gd.layout.updatemenus || []));
  gd._btn.forEach(function (i) {
    menus[i].type = narrow ? 'dropdown' : 'buttons';
    menus[i].direction = narrow ? 'down' : 'right';
  });
  var p = Plotly.relayout(gd, u);
  if (gd._btn.length) {
    p = p.then(function () { return Plotly.relayout(gd, { updatemenus: [] }); })
         .then(function () { return Plotly.relayout(gd, { updatemenus: menus }); });
  }
  p.then(function () { Plotly.Plots.resize(gd); });
}
window.addEventListener('resize', function () {
  document.querySelectorAll('.js-plotly-plot').forEach(fitMobile);
});
"""

TITLE = "California Taxes: Where the Money Comes From and Where It Goes"
INTRO = (
    "Historical California tax revenue and spending, state and local. Every chart is built from "
    "public data fetched by the scripts in <code>scripts/</code>; see the "
    "<a href=\"https://github.com/mckornfield/california-taxes\">repository</a> for sources and methods. "
    "Dollar amounts are by fiscal year (ending June 30). Use the buttons above each chart to switch between "
    "nominal dollars, inflation-adjusted dollars, per-person, and share-of-total views."
)


def build_html(sections: list) -> str:
    nav = "".join(f'<li><a href="#section-{i}">{t}</a></li>' for i, (t, _) in enumerate(sections))
    blocks = []
    for i, (title, notebooks) in enumerate(sections):
        block = f'<section id="section-{i}"><h2>{title}</h2>'
        for nb_name in notebooks:
            nb_path = NOTEBOOKS_DIR / nb_name
            if not nb_path.exists():
                block += f"<p><em>{nb_name} not yet executed.</em></p>"
                continue
            block += extract_outputs(nb_path)
        blocks.append(block + "</section>")
    content = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{TITLE}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>\U0001F4B0</text></svg>">
<script src="{PLOTLY_JS}"></script>
<script>{FIT_MOBILE_JS}</script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; color: #333; }}
  h2 {{ border-bottom: 2px solid #4e79a7; padding-bottom: 8px; margin-top: 40px; }}
  h3 {{ color: #2c5f8a; margin-top: 30px; }}
  nav ul {{ list-style: none; padding: 0; display: flex; gap: 16px; flex-wrap: wrap; }}
  nav a {{ color: #4e79a7; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  li {{ margin: 4px 0; }}
  @media (max-width: 600px) {{ body {{ padding: 12px 16px; }} }}
</style>
</head>
<body>
<h1>{TITLE}</h1>
<p>{INTRO}</p>
<nav><ul>{nav}</ul></nav>
{content}
</body>
</html>"""


def main():
    html = build_html(SECTIONS)
    out = ROOT / "index.html"
    out.write_text(html)
    print(f"Report written to {out} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
