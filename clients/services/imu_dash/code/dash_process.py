import os
import logging
import requests
import dash
from dash import html, dcc
from dash.dependencies import Input, Output
import plotly.graph_objs as go

HTTP_BIND_IMU_DASH_HOST = os.getenv("HTTP_BIND_IMU_DASH_HOST", "0.0.0.0")
HTTP_BIND_IMU_DASH_PORT = int(os.getenv("HTTP_BIND_IMU_DASH_PORT", "8201"))

HTTP_PUBLIC_IMU_API_HOST = os.getenv("HTTP_PUBLIC_IMU_API_HOST", "127.0.0.1")
HTTP_PUBLIC_IMU_API_PORT = int(os.getenv("HTTP_PUBLIC_IMU_API_PORT", "8200"))

API_BASE = f"http://{HTTP_PUBLIC_IMU_API_HOST}:{HTTP_PUBLIC_IMU_API_PORT}"

history = {
    "timestamps": [],
    "gyro_x": [],
    "gyro_y": [],
    "gyro_z": [],
    "accel_x": [],
    "accel_y": [],
    "accel_z": [],
}


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
            html.Div(
                style={**card_style, "marginTop": "16px", "width": "95%", "maxWidth": "95%"},
                children=[
                    html.Div("IMU Live Plot", style={"fontWeight": "650", "marginBottom": "8px"}),
                    dcc.Graph(id="imu-plot", style={"height": "620px"}),
                    dcc.Interval(id="imu-tick", interval=500, n_intervals=0),
                ],
            ),
            html.Div(
                style={**card_style, "marginTop": "16px", "width": "95%", "maxWidth": "95%"},
                children=[
                    html.Div("IMU Timestamp Delta CDF", style={"fontWeight": "650", "marginBottom": "8px"}),
                    dcc.Graph(id="imu-cdf", style={"height": "320px"}),
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

    @app.callback(
        Output("imu-plot", "figure"),
        Output("imu-cdf", "figure"),
        Input("imu-tick", "n_intervals"),
    )
    def update_plot(_n):
        try:
            r = requests.get(f"{API_BASE}/imu/buffer", timeout=1.0)
            if r.status_code == 200:
                samples = r.json()
                for key in history:
                    history[key].clear()
                for msg in samples:
                    payload = msg.get("payload", {})
                    ts = payload.get("timestamp")
                    gyro = payload.get("gyro")
                    accel = payload.get("accel")
                    if ts is None or not gyro or not accel:
                        continue
                    history["timestamps"].append(ts)
                    history["gyro_x"].append(gyro[0])
                    history["gyro_y"].append(gyro[1])
                    history["gyro_z"].append(gyro[2])
                    history["accel_x"].append(accel[0])
                    history["accel_y"].append(accel[1])
                    history["accel_z"].append(accel[2])
        except Exception:
            pass

        fig_line = {
            "data": [
                go.Scatter(x=history["timestamps"], y=history["gyro_x"], mode="lines", name="Gyro X"),
                go.Scatter(x=history["timestamps"], y=history["gyro_y"], mode="lines", name="Gyro Y"),
                go.Scatter(x=history["timestamps"], y=history["gyro_z"], mode="lines", name="Gyro Z"),
                go.Scatter(x=history["timestamps"], y=history["accel_x"], mode="lines", name="Accel X"),
                go.Scatter(x=history["timestamps"], y=history["accel_y"], mode="lines", name="Accel Y"),
                go.Scatter(x=history["timestamps"], y=history["accel_z"], mode="lines", name="Accel Z"),
            ],
            "layout": go.Layout(
                template="plotly_dark",
                title="Gyro & Accel (IMU)",
                xaxis_title="Time (s)",
                yaxis_title="Value",
                margin={"l": 40, "r": 10, "t": 30, "b": 40},
            ),
        }

        dts = []
        if len(history["timestamps"]) > 1:
            for i in range(1, len(history["timestamps"])):
                dts.append(history["timestamps"][i] - history["timestamps"][i - 1])

        dts = [dt for dt in dts if dt > 0]
        dts.sort()
        n = len(dts)
        cdf_y = [(i + 1) / n for i in range(n)] if n else []

        fig_cdf = {
            "data": [
                go.Scatter(x=dts, y=cdf_y, mode="lines", name="CDF"),
            ],
            "layout": go.Layout(
                template="plotly_dark",
                title="Timestamp Delta CDF (s)",
                xaxis_title="Delta (s)",
                xaxis_type="log",
                xaxis_range=[-4, -2],
                yaxis_title="CDF",
                margin={"l": 40, "r": 10, "t": 30, "b": 40},
            ),
        }

        return fig_line, fig_cdf
    app.run(host=HTTP_BIND_IMU_DASH_HOST, port=HTTP_BIND_IMU_DASH_PORT, debug=False)


if __name__ == "__main__":
    run()
