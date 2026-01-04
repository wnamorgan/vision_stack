# Doodle Labs RTP Datalink Integration Guide

This document explains how to stream RTP video over a **Doodle Labs mesh radio** using
a correct RF-efficient network configuration. It covers bandwidth sizing, network setup,
Docker configuration, and why **unicast** is required over radio.

---

## 1. Scope and Assumptions

- Video is sent as **RTP over UDP**
- Transport is **Ethernet → Doodle radio → Ethernet**
- No TCP, no application-layer retransmission
- Goal: **fail-fast video** (drops allowed, no buffering)

---

## 2. Image Size & Bandwidth Reference

Approximate payload bandwidth (excluding headers):

| Resolution | Format | FPS | Bandwidth |
|-----------|--------|-----|-----------|
| 3840×2160 | Raw 8-bit | 60 | ~4.0 Gbps |
| 3840×2160 | JPEG | 60 | ~1–2.4 Gbps |
| 1280×720  | Raw 8-bit | 30 | ~221 Mbps |
| 1280×720  | JPEG | 30 | ~24–72 Mbps |
| 640×640   | Raw 8-bit | 30 | ~98 Mbps |
| 640×640   | JPEG | 60 | ~19–48 Mbps |

**Doodle usable throughput:** ~20–80 Mbps (configuration and RF dependent)

➡️ **Conclusion:**  
Raw video is not viable.  
**JPEG or H.264/H.265 at reduced resolution/FPS is required.**

---

## 3. Doodle Network Model (Critical)

The Doodle radio behaves like a **wireless Ethernet cable**, but RF has constraints:

- **Unicast frames**
  - MAC-layer ACKs and short retries
  - Higher PHY rates
  - Efficient airtime usage

- **Broadcast / Multicast frames**
  - No MAC ACKs
  - Lowest PHY rate
  - Maximum airtime usage
  - Poor performance on RF

---

## 4. Why Broadcast Works on Wire but Fails on Radio

On a wired LAN:
- Broadcast (`192.168.1.255`) is cheap
- No shared RF medium

On a radio:
- Broadcast is sent at **base rate**
- No retries
- Every packet consumes maximum airtime
- Throughput collapses quickly

➡️ **Broadcast is acceptable on Ethernet, but not on RF.**

---

## 5. Unicast vs UDP / RTP Semantics

### Important distinction: ACK layers

| Layer | ACKs? |
|-----|------|
| RTP | ❌ |
| UDP | ❌ |
| **MAC (radio)** | ✅ (unicast only) |

**Key point:**
- MAC retries happen in **microseconds–milliseconds**
- Typical retry adds **~1–2 ms**
- Retries are bounded
- Failed packets are dropped

➡️ This **does NOT introduce buffering** and **does NOT violate RTP design intent**.

RTP avoids **slow transport-layer retransmissions**, not fast PHY retries.

---

## 6. Recommended Network Topology

### Subnet
```
192.168.1.0/24
```

### Example IPs
| Device | IP |
|------|----|
| UAV / Dashboard | 192.168.1.20 |
| Ground Station | 192.168.1.50 |
| Doodle radios | Transparent |

---

## 7. Docker / Compose Configuration

### ❌ What NOT to do (broadcast)
```yaml
RTP_DST_IP: 192.168.1.255
```

### ✅ Correct (unicast)
```yaml
RTP_DST_IP: 192.168.1.50
```

---

## 8. Ground Station Setup

- GCS owns the unicast IP:
  ```
  192.168.1.50/24
  ```
- Receiver binds to:
  ```
  0.0.0.0:5004
  ```

---

## 9. Failure Behavior (Desired)

When RF degrades:
- Packets drop
- No buffering
- No latency buildup
- Video resumes immediately on link recovery

This matches **real-time RTP expectations**.

---

## 10. Summary Rules (Non-Negotiable)

- ❌ No broadcast over radio
- ❌ No TCP
- ❌ No application-layer retries
- ✅ Unicast RTP over UDP
- ✅ Accept bounded MAC retries
- ✅ Design for frame drops, not buffering

---
