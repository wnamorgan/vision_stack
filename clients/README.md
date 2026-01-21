# Clients stack

This folder contains the **client-side** services (GCS UI and Client Gateway) and
their `docker compose` wiring.

## Quick start

From this directory:

```bash
docker compose up --build
```

Stop:

```bash
docker compose down --remove-orphans
```

## Canonical port / endpoint map (clients)

**Principle:** ports are **buses**, not “one port per message”. Payloads are
multiplexed by `type`.

| Env var / endpoint (defaults) | Plane | Meaning (≤10 words) |
|---|---|---|
| `ZMQ_CONTROL=tcp://127.0.0.1:6000` | Fan-in | Local intents: producers → one UDP sender. |
| `UDP_DST_IP:UDP_DST_PORT` (`:9000`) | Uplink | Client → platform UDP messages (intents today). |
| `UDP_RX_BINDINGS` (`meta:9100`) | Downlink | Platform → client UDP ingress (named channels). |
| `ZMQ_PUB_ENDPOINT=tcp://*:5570` | Fan-out | Local telemetry/notify bus for downlink + events. |
| `RTP_PORT=5004` | Data | Platform → client video stream (RTP/JPEG). |
| `VIDEO_HTTP_PORT=8000` | UI | Serves `/frame.jpg` to browser. |
| `DASH_PORT=8081` | UI | Dash UI web app. |
| `CONTROL_API_PORT=8100` | UI/API | Local HTTP API endpoints (commands + status). |

## Services (intent)

- `gcs/`
  - UI: Dash (`DASH_PORT`)
  - Local API: FastAPI/uvicorn (`CONTROL_API_PORT`)
  - Video HTTP: `/frame.jpg` (`VIDEO_HTTP_PORT`)
  - Local intent producer to `ZMQ_CONTROL`
  - Local telemetry consumer from `ZMQ_PUB_ENDPOINT`

- `gateway/`
  - Downlink UDP ingest (`UDP_RX_BINDINGS`) → local fan-out (`ZMQ_PUB_ENDPOINT`)
  - Uplink bridge: `ZMQ_CONTROL` → UDP (`UDP_DST_IP:UDP_DST_PORT`)
  - (Planned) video ingest → SHM + notify on `ZMQ_PUB_ENDPOINT`

## Where to configure

- Compose wiring: `clients/docker-compose.yml`
- Service env: `clients/services/*/.env`
