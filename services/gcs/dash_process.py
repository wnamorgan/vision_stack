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
        html.H3("GCS Hello World"),
        html.Button("Send HELLO", id="btn"),
        html.Div(id="status")
    ])

    @app.callback(Output("status", "children"), Input("btn", "n_clicks"))
    def send(n):
        if not n:
            return ""
        r = requests.post(f"http://127.0.0.1:{CONTROL_API_PORT}/control/hello", json={"value": n})
        return r.json()

    app.run(host="0.0.0.0", port=DASH_PORT)
