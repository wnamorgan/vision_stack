# Clients stack

This folder contains the **client-side** services (GCS UI and Client Gateway) and
their `docker compose` wiring.

## Quick start

Default (same-host or wired LAN):

```bash
./compose.sh up --build
```

Wi-Fi mode:

```bash
./compose.sh --wifi up --build
```

Stop:

```bash
./compose.sh down --remove-orphans
./compose.sh --wifi down --remove-orphans
```

## Canonical port / endpoint map (clients)

**Principle:** ports are **buses**, not “one port per message”. Payloads are
multiplexed by `type`.

| Env var / endpoint (defaults) | Plane | Meaning (≤10 words) |
|---|---|---|
| `ZMQ_BIND_PULL_INTENT_HOST/PORT` + `ZMQ_CONNECT_PUSH_INTENT_HOST/PORT` | Fan-in | Local intents: producers → one UDP sender. |
| `UDP_INTENT_DST_IP:UDP_INTENT_DST_PORT` (`:9000`) | Uplink | Client → platform UDP messages (intents today). |
| `UDP_RX_BINDINGS` (`meta:9100`) | Downlink | Platform → client UDP ingress (named channels). |
| `ZMQ_BIND_PUB_TELEM_HOST/PORT` + `ZMQ_CONNECT_SUB_TELEM_HOST/PORT` | Fan-out | Local telemetry/notify bus for downlink + events. |
| `RTP_RX_LISTEN_PORT=5004` | Data | Platform → client video stream (RTP/JPEG). |
| `HTTP_BIND_VIDEO_HOST/PORT` | UI | Serves `/frame.jpg` to browser. |
| `HTTP_BIND_DASH_HOST/PORT` | UI | Dash UI web app. |
| `HTTP_BIND_CONTROL_HOST/PORT` | UI/API | Local HTTP API endpoints (commands + status). |

## Services (intent)

- `gcs/`
  - UI: Dash (`HTTP_BIND_DASH_HOST/PORT`)
  - Local API: FastAPI/uvicorn (`HTTP_BIND_CONTROL_HOST/PORT`)
  - Video HTTP: `/frame.jpg` (`HTTP_BIND_VIDEO_HOST/PORT`)
  - Local intent producer to `ZMQ_BIND_PULL_INTENT_HOST/PORT` + `ZMQ_CONNECT_PUSH_INTENT_HOST/PORT`
  - Local telemetry consumer from `ZMQ_BIND_PUB_TELEM_HOST/PORT` + `ZMQ_CONNECT_SUB_TELEM_HOST/PORT`

- `gateway/`
  - Downlink UDP ingest (`UDP_RX_BINDINGS`) → local fan-out (`ZMQ_BIND_PUB_TELEM_HOST/PORT`)
  - Uplink bridge: ZMQ intent bus → UDP (`UDP_INTENT_DST_IP:UDP_INTENT_DST_PORT`)
  - (Planned) video ingest → SHM + notify on `ZMQ_BIND_PUB_TELEM_HOST/PORT`

## Where to configure

- Compose wiring: `clients/docker-compose.yml`
- Service env: `clients/services/*/.env`
