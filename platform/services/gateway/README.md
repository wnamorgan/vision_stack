# Gateway Service

The gateway is the single boundary between platform services and clients. It owns all
external UDP/RTP egress and stays component-agnostic by using dynamic registration and
stream-based sink routing.

## Core responsibilities

- Ingest internal ZMQ streams from platform services (via registration).
- Produce RTP (HostRTP) and forward frame metadata.
- Forward registered JSON telemetry over UDP.
- Track link usage and publish it to clients.

## Control and data paths

### 1) Registration (platform services -> gateway)

Platform services publish ZMQ and send a UDP registration intent to the gateway:

```
{
  "type": "GW_REGISTER_ZMQ_SUB",
  "value": {
    "endpoint": "tcp://service:port",
    "stream":   "stream_id"
  }
}
```

Gateway behavior:
- Stores the endpoint.
- Spawns a blocking ZMQ SUB listener thread for that endpoint.
- Associates the endpoint with a per-stream destination list.

Notes:
- The `endpoint` is treated as opaque.
- `stream` is used only for routing sinks (not for component identity).
- Gateway starts with zero endpoints; all ingest is registration-driven.

### 2) Sink requests (clients -> gateway)

Clients request UDP delivery for a stream using control intents:

```
{ "type": "ADD_SINK",    "ip": "CLIENT_IP", "value": { "stream": "stream_id" } }
{ "type": "REMOVE_SINK", "ip": "CLIENT_IP", "value": { "stream": "stream_id" } }
```

Gateway behavior:
- Adds/removes `CLIENT_IP` from the destination set for the given stream.
- Does not embed any component-specific knowledge.

### 3) UDP forwarding (platform gateway -> client gateway)

The platform gateway forwards JSON payloads to clients:

- `UDP_META_PORT` (default 9100): frame meta and side-channel data
- `UDP_TELEM_PORT` (default 9102): link usage and tracker status
- `UDP_STREAM_PORT` (default 9101): registered streams (requires `stream`)

The gateway keeps unique destination IPs per stream; each registered stream is
forwarded only to its stream’s sink list.

### 4) Client gateway fanout (UDP -> ZMQ)

The client gateway binds UDP ports defined by `UDP_RX_BINDINGS` and republishes all
received JSON on a single ZMQ PUB bus (`ZMQ_BIND_PUB_TELEM_PORT`, default 5570).

This means multiple UDP ports fan into one ZMQ bus, with messages tagged by `_udp_src`
and `_udp_port`.

## RTP path (platform gateway)

Camera frames are published over ZMQ and registered as a `frame` stream. The gateway:

1. Subscribes to the frame ZMQ endpoint (HostRTP only).
2. Reads shared memory and produces RTP.
3. Publishes `FRAME_META` on its internal ZMQ bus.
4. `udp_tx_process` forwards that meta over `UDP_META_PORT` to clients.

RTP sinks are managed by `RTP_SUBSCRIBE`/`RTP_UNSUBSCRIBE` and are independent from
registered stream sinks.

## Key guarantees

- No component-specific wiring in the gateway.
- All ingest is registration-based.
- Sink routing requires a `stream` identifier; requests without one are ignored.
- Client fanout remains simple: UDP -> single ZMQ bus.

## Environment overview (gateway)

- `UDP_META_PORT` (default 9100)
- `UDP_STREAM_PORT`  (default 9101)
- `UDP_TELEM_PORT` (default 9102)
- `ZMQ_CONNECT_SUB_CMD_HOST/PORT` (internal control bus)
- `ZMQ_CONNECT_SUB_FRAME_META_HOST/PORT` (frame meta bus)
- `ZMQ_CONNECT_SUB_RTP_USAGE_HOST/PORT` (RTP usage bus)
