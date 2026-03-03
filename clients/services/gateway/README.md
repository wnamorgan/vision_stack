# Client Gateway

The client gateway is the fan-in point for UDP from the platform gateway and the
fan-out point to local ZMQ consumers.

## Core behavior

- Binds one or more UDP ports (`UDP_RX_BINDINGS`).
- Republishes all received JSON on a single ZMQ PUB bus
  (`ZMQ_BIND_PUB_TELEM_PORT`, default `5570`).
- Supports dynamic UDP binds via `GW_REGISTER_UDP_BIND` on the client command bus.

## UDP bindings

`UDP_RX_BINDINGS` defines which UDP ports the client gateway listens on:

```
meta:9100,telem:9102
```

Each received message is tagged with:

- `_udp_src`
- `_udp_port`
- `_udp_from_ip`
- `_udp_from_port`

## ZMQ fanout

All UDP traffic is republished on:

```
tcp://0.0.0.0:5570
```

Local services (e.g., IMU dash, GCS) subscribe to that single bus and filter by
message content (`type`, `topic`, `_udp_src`).
