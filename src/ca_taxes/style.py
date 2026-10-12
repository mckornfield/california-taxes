"""Shared Plotly look and the toggleable stacked-area chart used by most notebooks."""
import pandas as pd
import plotly.graph_objects as go

from .deflate import LAST_ACTUAL_FY, base_fy

# Tableau-ish categorical palette, readable on white; reused in a fixed order per chart.
PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
           "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac", "#86bcb6", "#d4a6c8", "#8cd17d", "#499894"]
SOURCE_NOTE = "Source: California Legislative Analyst's Office (from DOF / State Controller data)"


def base_layout(fig: go.Figure, title: str, subtitle: str = "", height: int = 560) -> go.Figure:
    t = f"{title}<br><sup>{subtitle}</sup>" if subtitle else title
    fig.update_layout(title=dict(text=t, x=0.01, y=0.97, yanchor="top"), height=height,
                      template="plotly_white", hovermode="x unified",
                      margin=dict(l=60, r=20, t=140 if fig.layout.updatemenus else 90, b=60), legend=dict(orientation="v", x=1.01),
                      font=dict(family="-apple-system, Segoe UI, sans-serif", size=13))
    return fig


def stacked_area_toggle(df: pd.DataFrame, group: str, title: str, subtitle: str = "",
                        order: list[str] | None = None, breaks: dict[float, str] | None = None) -> go.Figure:
    """Stacked area of `group` over fy with a view toggle.

    df needs columns fy, `group`, nominal_b, real_b, real_pc (see deflate.add_views).
    Views: nominal $B, real $B, real $ per person, share of total.
    """
    b = base_fy()
    views = [("Nominal ($B)", "nominal_b", "$B", "$,.1f"),
             (f"Real, {b} dollars ($B)", "real_b", "$B", "$,.1f"),
             (f"Real per person ({b} $)", "real_pc", "$ per person", "$,.0f"),
             ("Share of total (%)", "share", "%", ".1f")]
    wide = {v: df.pivot_table(index="fy", columns=group, values=v, aggfunc="sum").fillna(0)
            for v in ("nominal_b", "real_b", "real_pc")}
    cols = order or list(wide["nominal_b"].sum().sort_values(ascending=False).index)
    wide["share"] = wide["nominal_b"][cols].div(wide["nominal_b"][cols].sum(axis=1), axis=0) * 100
    fig = go.Figure()
    for vi, (_, key, _, fmt) in enumerate(views):
        for ci, c in enumerate(cols):
            fig.add_trace(go.Scatter(
                x=wide[key].index, y=wide[key][c], name=c, stackgroup="one", mode="lines",
                line=dict(width=0.5, color=PALETTE[ci % len(PALETTE)]), legendgroup=c,
                showlegend=(vi == 0), visible=(vi == 0),
                hovertemplate=f"%{{y:{fmt[1:] if fmt.startswith('$') else fmt}}}", ))
    n = len(cols)
    buttons = []
    for vi, (label, _, ytitle, _) in enumerate(views):
        vis = [i // n == vi for i in range(n * len(views))]
        buttons.append(dict(label=label, method="update",
                            args=[{"visible": vis, "showlegend": vis}, {"yaxis.title.text": ytitle}]))  # legend follows the visible view
    fig.update_layout(updatemenus=[dict(type="buttons", direction="right", buttons=buttons,
                                        x=0, y=1.0, xanchor="left", yanchor="bottom", showactive=True)],
                      yaxis_title="$B", xaxis_title="Fiscal year (ending June 30)")
    base_layout(fig, title, subtitle or SOURCE_NOTE)
    x1 = float(wide["nominal_b"].index.max())
    if x1 > LAST_ACTUAL_FY:  # state series run into budget estimates; local data end at actuals
        fig.add_vrect(x0=LAST_ACTUAL_FY + 0.5, x1=x1, fillcolor="grey", opacity=0.12, line_width=0,
                      annotation_text="estimate", annotation_position="top left")
    for x, text in (breaks or {}).items():
        fig.add_vline(x=x, line_dash="dot", line_color="grey", annotation_text=text,
                      annotation_position="bottom left")
    return fig
