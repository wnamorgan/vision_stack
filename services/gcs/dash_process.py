import dash
from dash import html
from dash.dependencies import Input, Output
import requests
import os

CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT"))
DASH_PORT = int(os.getenv("DASH_PORT", "8080"))
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "http://127.0.0.1:8000")



import os
import requests

import dash
from dash import html
from dash.dependencies import Input, Output


CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT"))
DASH_PORT = int(os.getenv("DASH_PORT", "8081"))

# IMPORTANT: This must be reachable by the *browser*, not just the Dash container.
# Example: http://192.168.1.2:8000
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "http://127.0.0.1:8000")


def run():
    app = dash.Dash(__name__)

    app.layout = html.Div(
        [
            html.Div(
                [
                    html.H3("Configure Connection"),
                    html.Button("Stream Video", id="stream_btn"),
                    html.Div(id="stream_status", style={"marginTop": "10px"}),

                    html.Hr(),

                    html.Button("Send HELLO", id="hello_btn"),
                    html.Div(id="hello_status", style={"marginTop": "10px"}),
                ],
                style={"width": "34%", "display": "inline-block", "verticalAlign": "top", "padding": "10px"},
            ),
            html.Div(
                [
                    html.Iframe(
                        id="video_iframe",
                        src=f"{VIDEO_BASE_URL}/video_panel?control_port={CONTROL_API_PORT}",
                        style={"width": "100%", "height": "90vh", "border": "0"},
                    )
                ],
                style={"width": "65%", "display": "inline-block", "verticalAlign": "top"},
            ),
        ]
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

    @app.callback(Output("hello_status", "children"), Input("hello_btn", "n_clicks"))
    def hello(n):
        if not n:
            return ""
        r = requests.post(
            f"http://127.0.0.1:{CONTROL_API_PORT}/control/hello",
            json={"value": n},
            timeout=2.0,
        )
        return r.json()

    app.run(host="0.0.0.0", port=DASH_PORT)
