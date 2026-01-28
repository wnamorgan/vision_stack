import os
import logging
import requests
import dash
from dash import html
from dash.dependencies import Input, Output

HTTP_BIND_IMU_DASH_HOST = os.getenv("HTTP_BIND_IMU_DASH_HOST", "0.0.0.0")
HTTP_BIND_IMU_DASH_PORT = int(os.getenv("HTTP_BIND_IMU_DASH_PORT", "8201"))

HTTP_PUBLIC_IMU_API_HOST = os.getenv("HTTP_PUBLIC_IMU_API_HOST", "127.0.0.1")
HTTP_PUBLIC_IMU_API_PORT = int(os.getenv("HTTP_PUBLIC_IMU_API_PORT", "8200"))

API_BASE = f"http://{HTTP_PUBLIC_IMU_API_HOST}:{HTTP_PUBLIC_IMU_API_PORT}"


def run():
    app = dash.Dash(__name__)
    logging.getLogger("werkzeug").disabled = True

    panel_style = {
        "backgroundColor": "#0b0b0b",
        "color": "#eaeaea",
        "height": "100vh",
        "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        "padding": "24px",
    }

    card_style = {
        "backgroundColor": "#111",
        "border": "1px solid #222",
        "borderRadius": "12px",
        "padding": "14px",
        "boxShadow": "0 6px 18px rgba(0,0,0,0.35)",
        "maxWidth": "420px",
    }

    mono_style = {
        "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "fontSize": "12px",
        "opacity": "0.9",
        "whiteSpace": "pre-wrap",
    }

    app.layout = html.Div(
        style=panel_style,
        children=[
            html.H2("IMU Dev Dash"),
            html.Div(
                style=card_style,
                children=[
                    html.Div("IMU Stream Control", style={"fontWeight": "650", "marginBottom": "8px"}),
                    html.Div(
                        style={"display": "flex", "gap": "10px"},
                        children=[
                            html.Button("Start IMU", id="imu_start", style={"padding": "10px 12px"}),
                            html.Button("Stop IMU", id="imu_stop", style={"padding": "10px 12px"}),
                        ],
                    ),
                    html.Div(id="imu_status", style={"marginTop": "10px", **mono_style}),
                ],
            ),
        ],
    )

    @app.callback(Output("imu_status", "children"), Input("imu_start", "n_clicks"), Input("imu_stop", "n_clicks"))
    def handle_buttons(n_start, n_stop):
        ctx = dash.callback_context
        if not ctx.triggered:
            return ""
        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
        try:
            if btn_id == "imu_start":
                r = requests.post(f"{API_BASE}/imu/start", timeout=2.0)
            else:
                r = requests.post(f"{API_BASE}/imu/stop", timeout=2.0)
            return r.json()
        except Exception as e:
            return f"Error: {e}"

    app.run(host=HTTP_BIND_IMU_DASH_HOST, port=HTTP_BIND_IMU_DASH_PORT, debug=False)


if __name__ == "__main__":
    run()
