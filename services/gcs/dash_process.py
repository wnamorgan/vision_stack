import dash
from dash import html
from dash.dependencies import Input, Output
import requests
import os

CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT", "8100"))
DASH_PORT = int(os.getenv("DASH_PORT", "8080"))

def run():
    app = dash.Dash(__name__)


    app.layout = html.Div([
        html.H3("Configure Connection"),
        html.Button("Stream Video", id="stream_btn"),
        html.Div(id="stream_video")
    ])


    @app.callback(Output("stream_video", "children"), Input("stream_btn", "n_clicks"))
    def send(n):
        if not n:
            return ""
        r = requests.post(f"http://127.0.0.1:{CONTROL_API_PORT}/control/stream_subscribe", json={"value": n})
        return r.json()

    app.run(host="0.0.0.0", port=DASH_PORT)    
