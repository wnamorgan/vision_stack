# vision_stack Compose Workflow

This repository is built around _services_ that expose their own Dockerfiles, env files, and run scripts. `docker-compose.yml` wires those services together so you can spin up the entire stack with a single command.

## Build

`docker-compose.yml` wires the camera and dashboard services together on the shared `vision` network and honors the shared contracts (`ZMQ_SUB_ENDPOINT=tcp://camera:5555`, shared memory via `ipc: host`, etc.). Use Compose to build either a single service or the entire stack:

```bash
docker compose build camera
docker compose build dashboard
```

Or rebuild every service at once:

```bash
docker compose build
```

The per-service `build.sh` helpers still exist under `services/camera` and `services/dashboard` and source their own `.env` when you need more granular builds outside of Compose.

The root-level `.env` file (next to this README) contains overrides such as `CAM_DEVICE` so Compose can map the camera device without hardcoding it in the YAML.

If you need automatic V4L2 detection, use `scripts/up.sh`—it scans `/dev/video*`, updates the root `.env` with the first available device, and then runs `docker compose up` for you.

## Run

### Starting the stack

Bring everything up on the shared `vision` network:

```bash
docker compose up --build
```

### Stopping the stack

```bash
docker compose down
```

### Viewing & debugging

Tail logs while services run:

```bash
docker compose logs -f camera
docker compose logs -f dashboard
```

Drop into either container:

```bash
docker compose exec camera bash
docker compose exec dashboard bash
```

Inside each container you’ll find the respective README for deeper instructions (`services/camera/tests/README.md`, `services/dashboard/README.md`).

# Viewing & debugging

Tail logs:

```bash
docker compose logs -f camera
docker compose logs -f dashboard
```

Drop into a running container:

```bash
docker compose exec camera bash
docker compose exec dashboard bash
```

Inside you'll find each service’s README with more testing details (`services/camera/tests/README.md`, `services/dashboard/README.md`).
