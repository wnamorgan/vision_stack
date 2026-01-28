import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import threading
import queue

# Shared message queue (injected by main)
message_queue = None

# Storage buffer for plotting
history = {
    "timestamps": [],
    "gyro_x": [],
    "gyro_y": [],
    "gyro_z": [],
    "accel_x": [],
    "accel_y": [],
    "accel_z": [],
}

def dequeue_loop():
    while True:
        try:
            # New message format ONLY:
            # {"tx": "...", "rx": "*", "topic": "gaa", "payload": {"timestamp":..., "gyro":[...], "accel":[...], ...}}
            msg = message_queue.get(timeout=1)

            if msg["topic"] != "gaa":
                continue

            p = msg["payload"]
            ts = p["timestamp"]
            gx, gy, gz = p["gyro"]
            ax, ay, az = p["accel"]

            history["timestamps"].append(ts)
            history["gyro_x"].append(gx)
            history["gyro_y"].append(gy)
            history["gyro_z"].append(gz)
            history["accel_x"].append(ax)
            history["accel_y"].append(ay)
            history["accel_z"].append(az)

            # Limit to last 500 samples
            for key in history:
                history[key] = history[key][-500:]

        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Dash dequeue error] {e}")

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H3("IMU Live Plot"),
    dcc.Graph(id="imu-plot"),
    dcc.Interval(id="update-interval", interval=500, n_intervals=0),
])

@app.callback(Output("imu-plot", "figure"), Input("update-interval", "n_intervals"))
def update_plot(n):
    return {
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
        )
    }

def launch_dash(queue_handle):
    global message_queue
    message_queue = queue_handle
    threading.Thread(target=dequeue_loop, daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=8050)
