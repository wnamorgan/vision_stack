import os
import requests
import logging
import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State


CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT"))
DASH_PORT = int(os.getenv("DASH_PORT", "8081"))

# IMPORTANT: This must be reachable by the *browser*, not just the Dash container.
# Example: http://192.168.1.46:8000
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "http://127.0.0.1:8000")

DEFAULT_W = int(os.getenv("RTP_WIDTH", "1280"))
DEFAULT_H = int(os.getenv("RTP_HEIGHT", "720"))


def run():
    app = dash.Dash(__name__)
    logging.getLogger("werkzeug").disabled = True

    # --- styling (dark, clean) ---
    panel_style = {
        "backgroundColor": "#0b0b0b",
        "color": "#eaeaea",
        "height": "100vh",
        "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    }
    card_style = {
        "backgroundColor": "#111",
        "border": "1px solid #222",
        "borderRadius": "14px",
        "padding": "14px",
        "marginBottom": "12px",
        "boxShadow": "0 6px 18px rgba(0,0,0,0.35)",
    }
    label_style = {"fontSize": "12px", "opacity": "0.85", "marginBottom": "6px"}
    mono_style = {
        "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "fontSize": "12px",
        "opacity": "0.95",
        "whiteSpace": "pre-wrap",
        "wordBreak": "break-word",
    }

    def slider_block(title: str, slider_id: str, default: float):
        return html.Div(
            [
                html.Div(title, style=label_style),
                dcc.Slider(
                    id=slider_id,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    value=default,
                    marks=None,
                    tooltip={"placement": "bottom", "always_visible": False},
                    updatemode="drag",
                ),
            ],
            style={"flex": "1", "minWidth": "180px"},
        )

    # Layout: match the old split behavior (controls ~34%, video ~65%)
    app.layout = html.Div(
        style=panel_style,
        children=[
            # LEFT: controls
            html.Div(
                style={
                    "width": "34%",
                    "display": "inline-block",
                    "verticalAlign": "top",
                    "padding": "16px",
                    "boxSizing": "border-box",
                    "height": "100vh",
                    "overflowY": "auto",
                    "borderRight": "1px solid #1f1f1f",
                },
                children=[
                    html.Div("GCS Controls", style={"fontSize": "18px", "fontWeight": "700", "marginBottom": "10px"}),
                    html.Div(
                        style=card_style,
                        children=[
                            html.Div("Connection", style={"fontWeight": "650", "marginBottom": "8px"}),
                            html.Button(
                                "Stream Video",
                                id="stream_btn",
                                style={"padding": "10px 12px", "borderRadius": "10px"},
                            ),
                            html.Div(id="stream_status", style={"marginTop": "10px", **mono_style}),
                        ],
                    ),
                    html.Div(
                        style=card_style,
                        children=[
                            html.Div("Video Settings", style={"fontWeight": "650", "marginBottom": "10px"}),
                            html.Div(
                                style={"display": "flex", "gap": "10px"},
                                children=[
                                    slider_block("Scale (0–1)", "s_scale", 1.0),
                                    slider_block("FPS (0–1)", "s_fps", 0.7),
                                    slider_block("Quality (0–1)", "s_q", 0.82),
                                ],
                            ),
                            html.Div(id="video_readout", style={"marginTop": "10px", **mono_style}),
                            html.Button(
                                "Apply",
                                id="apply_video_btn",
                                style={"marginTop": "10px", "padding": "10px 12px", "borderRadius": "10px"},
                            ),
                            html.Div(id="apply_status", style={"marginTop": "10px", **mono_style}),
                        ],
                    ),
                ],
            ),
            # RIGHT: video (fixed display size; transmitted resolution can change independently)
            html.Div(
                style={
                    "width": "65%",
                    "display": "inline-block",
                    "verticalAlign": "top",
                    "height": "100vh",
                },
                children=[
                    html.Iframe(
                        id="video_iframe",
                        src=f"{VIDEO_BASE_URL}/video_panel?control_port={CONTROL_API_PORT}&poll_hz=30",
                        style={"width": "100%", "height": "100vh", "border": "0"},
                    )
                ],
            ),
        ],
    )

    @app.callback(Output("stream_status", "children"), Input("stream_btn", "n_clicks"))
    def stream(n):
        if not n:
            return ""
        r = requests.post(
            f"http://127.0.0.1:{CONTROL_API_PORT}/control/stream_subscribe",
            json={"value": n},
            timeout=2.0,
        )
        return r.json()

    @app.callback(
        Output("video_readout", "children"),
        Input("s_scale", "value"),
        Input("s_fps", "value"),
        Input("s_q", "value"),
    )
    def readout(s_scale, s_fps, s_q):
        # Map 0..1 sliders into real units (display)
        scale = 0.1 + 0.9 * float(s_scale)
        w = int(DEFAULT_W * scale)
        h = int(DEFAULT_H * scale)
        fps = int(round(5 + (30 - 5) * float(s_fps)))   # 5..30 Hz
        q = int(round(10 + (95 - 10) * float(s_q)))     # 10..95
        return f"Scale={scale:.2f} → {w}×{h} | FPS={fps} Hz | Q={q}"

    @app.callback(
        Output("apply_status", "children"),
        Output("video_iframe", "src"),
        Input("apply_video_btn", "n_clicks"),
        State("s_scale", "value"),
        State("s_fps", "value"),
        State("s_q", "value"),
        prevent_initial_call=True,
    )
    def apply(n, s_scale, s_fps, s_q):
        if not n:
            return "", dash.no_update
        scale = 0.1 + 0.9 * float(s_scale)
        w = int(DEFAULT_W * scale)
        h = int(DEFAULT_H * scale)
        fps = int(round(5 + (30 - 5) * float(s_fps)))   # 5..30
        q = int(round(10 + (95 - 10) * float(s_q)))     # 10..95

        payload = {"scale": round(scale, 6), "w": w, "h": h, "fps": fps, "quality": q}
        r = requests.post(
            f"http://127.0.0.1:{CONTROL_API_PORT}/control/video_settings",
            json=payload,
            timeout=2.0,
        )

        iframe_src = f"{VIDEO_BASE_URL}/video_panel?control_port={CONTROL_API_PORT}&poll_hz={fps}"
        return {"sent": payload, "api": r.json()}, iframe_src

    app.run(host="0.0.0.0", port=DASH_PORT)


if __name__ == "__main__":
    run()
