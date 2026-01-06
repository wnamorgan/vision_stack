# Vision Stack Network Notes (Authoritative)

This document defines the networking behavior for the **vision stack** Compose system:
- **Container ↔ container** messaging (ZeroMQ on the `vision` bridge)
- **Container → host** local testing (host-side tools like `tcpdump`/`gst-launch`)
- **Container ↔ LAN / remote-side user** networking (via `macvlan`)
- **RTP over UDP** (JPEG/RTP) and common failure modes (especially **multiple receivers**)

The goal is to make future troubleshooting **mechanical** (commands + expected interpretations), without relying on rediscovering behaviors.

---

## 1) Networks in this project

### 1.1 `vision` (user-defined Docker bridge)
Purpose: **internal container-to-container communication** (e.g., ZeroMQ pub/sub).

Properties:
- Each container gets its own network namespace and a **unique IP** on the bridge subnet.
- Docker provides **DNS by service name** (e.g., `camera` resolves to the camera container on the `vision` network).
- Port numbers can be reused across containers internally (no conflict) because they are in different namespaces.

Recommended configuration (portable + deterministic):
```yaml
networks:
  vision:
    driver: bridge
    ipam:
      config:
        - subnet: 172.30.10.0/24
          gateway: 172.30.10.1
```

Why pin the subnet/gateway:
- Avoids per-host variability (e.g., `172.19.0.1` on one machine, `172.21.0.1` on another).
- Enables stable “container → host” addressing for local testing.

**Important constraint:** choose a `vision` subnet that will not overlap with any real LAN/VPN used in development.

---

### 1.2 `macvlan` (container appears as a LAN device)
Purpose: make a container reachable as a **first-class device on the Ethernet LAN**.

Properties:
- The container receives a **LAN IP** (e.g., `192.168.1.x`) and has its own L2 identity (unique MAC).
- A remote-side user on the same Ethernet segment can send/receive to this IP directly.
- Many setups prevent **host ↔ macvlan-container** communication by default (“macvlan host isolation”).
  - Do not assume the host can talk to the macvlan IP unless a host-side macvlan shim is created.

Typical configuration:
```yaml
networks:
  macvlan:
    driver: macvlan
    driver_opts:
      parent: ${MACVLAN_PARENT}
    ipam:
      config:
        - subnet: 192.168.1.0/24
          gateway: 192.168.1.1
```

---

## 2) Canonical endpoint glossary (with pinned `vision` gateway)

With the pinned bridge configuration, the following is stable:

### 2.1 Host-side endpoint of the `vision` bridge
- **`VISION_GATEWAY = 172.30.10.1`**
- Meaning: the host endpoint of the `vision` bridge network.
- Use case: container → host local testing/viewing.

### 2.2 LAN endpoint of a macvlan-attached container
- Example: `gateway` container gets **`192.168.1.2`** on macvlan.
- Meaning: the container as a LAN device.
- Use case: remote-side user over Ethernet/radio reaches the container.

### 2.3 Bridge IP of a container (internal only)
- Example: `gateway` also gets a `vision` IP such as `172.30.10.x`.
- Meaning: internal container address on the `vision` bridge.
- Use case: container-to-container connectivity (rarely needed directly because service DNS is preferred).

---

## 3) ZeroMQ pub/sub on the `vision` bridge

### 3.1 Bind vs connect (ZeroMQ)
For ZeroMQ, treat:
- **bind** = “offer a stable endpoint”
- **connect** = “dial a stable endpoint”

Typical pattern:
- Publisher binds inside its container: `tcp://0.0.0.0:5555`
- Subscribers connect using service DNS: `tcp://camera:5555`

Why this works:
- `camera` resolves via Docker DNS on the `vision` bridge.
- The bridge routes packets between container IPs.

**Nuance:** ZeroMQ patterns differ:
- PUB/SUB: fan-out (each subscriber receives the stream)
- PUSH/PULL: load distribution (each message goes to one consumer)

---

## 4) RTP (JPEG/RTP) addressing in this project

### 4.1 Host-side viewing/debugging (local machine)
Set the sender destination to the **host bridge endpoint**:
- `RTP_DST_IP = 172.30.10.1`
- `RTP_PORT  = 5004`

Then a host-side user can receive:
```bash
gst-launch-1.0 -v   udpsrc port=5004 caps="application/x-rtp,media=video,encoding-name=JPEG,payload=26,clock-rate=90000" !   rtpjpegdepay ! jpegdec ! autovideosink sync=false
```

This works even if Ethernet/Wi‑Fi are down because it is local virtual networking.

### 4.2 Remote-side user over Ethernet/radio (LAN visibility)
Set the sender destination to the LAN path:
- **Unicast (recommended):** `RTP_DST_IP = 192.168.1.<receiver>`
- **Broadcast:** `RTP_DST_IP = 192.168.1.255` (only if receivers are on that L2 segment)

Broadcast notes:
- Host self-receive of its own broadcast is not guaranteed across all NIC/driver/kernel combinations.
- Broadcast can be blocked or isolated on some Wi‑Fi setups.

---

## 5) The “multiple receivers on :5004” conflict (root cause + proof)

### 5.1 What happened
A host-side GCS process (running with `network_mode: host`) started a receiver:
- `udpsrc port=5004` → binds **0.0.0.0:5004** on the host.

Starting `gst-launch` on the host also binds:
- **0.0.0.0:5004**

Now two processes are bound to the same UDP port:
- Packets may be delivered to one receiver (starving the other), or distributed unpredictably depending on socket options.

### 5.2 Mechanical proof
Run:
```bash
sudo ss -uapn | grep ':5004'
```

If output shows both `python` and `gst-launch-1.0` bound to `:5004`, the system is in contention.

### 5.3 Deterministic solutions (choose one)
- **Single-consumer rule:** do not run two RTP receivers on the same host on the same UDP port at the same time.
- **Different ports:** reserve `5004` for one receiver and use a separate debug port (e.g., `5006`) for other receivers.
- **Duplicate at sender:** send the same RTP to two ports (one for GCS, one for host debug).
- **Multicast:** if true “one-to-many” is required at the network layer.

---

## 6) Environment precedence (Compose pitfall)
In Docker Compose:
- `environment:` values in `docker-compose.yml` override `env_file:` values.

Verify effective values inside a container:
```bash
docker compose exec gateway sh -lc 'echo RTP_DST_IP=$RTP_DST_IP RTP_PORT=$RTP_PORT'
```

---

## 7) Common host port publish errors (example: 8080)
If Compose reports:
- `Bind for 0.0.0.0:8080 failed: port is already allocated`

It means the host already has a process/container listening on port 8080.

Find the owner:
```bash
sudo ss -ltnp | grep ':8080'
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep 8080
```

Fix:
- stop the existing owner, or
- change the mapping (e.g., `18080:80`), or
- bind only to localhost (e.g., `127.0.0.1:18080:80`).

---

## 8) Quick checklists

### 8.1 Confirm `vision` gateway is pinned
```bash
docker network inspect <project>_vision | grep -i '"Subnet"\|"Gateway"'
```
Expected: `172.30.10.0/24` and `172.30.10.1`.

### 8.2 Confirm LAN path is active (macvlan)
On a host connected to the LAN:
```bash
sudo tcpdump -ni ${MACVLAN_PARENT} udp port 5004
```
Packets appear only when `RTP_DST_IP` targets a `192.168.1.x/.255` destination.