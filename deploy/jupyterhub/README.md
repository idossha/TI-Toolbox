# Hosted TI-Toolbox (JupyterHub)

One VM runs JupyterHub; each logged-in user gets their **own TI-Toolbox container**
(the same `idossha/simnibs` image everyone runs locally, with this checkout's `tit` and the example notebook baked in), a private project volume
pre-seeded with `sub-ernie`, and the `SimNIBS + TI-Toolbox` Jupyter kernel.
Nothing to install on the user's side.

```
browser ──HTTPS──▶ caddy ──▶ jupyterhub (DockerSpawner, GitHub login)
                                 │ docker.sock
                                 ▼
                    tit-user-<login>  ← ti-toolbox-singleuser image
                    ├─ /mnt/000         per-user volume, seeded from SEED_DIR on first start
                    ├─ /mnt/notebooks   example_workflow.ipynb (and nbgitpuller checkouts)
                    └─ JupyterLab, 2 CPU / 6 GB cap, culled after 1 h idle
```

## Host requirements

- Linux VM with Docker + compose plugin. Sizing rule of thumb: each active user
  container is capped at `USER_CPU_LIMIT` cores / `USER_MEM_LIMIT` (defaults 2 / 10 GB).
  The example notebook (one TI simulation on ernie + analyses) took 8.5 min native on
  one core and 12 min under the 2-core cap on an emulated host; the mesh→NIfTI/MNI step
  is the memory peak — 6 GB was OOM-killed, 10 GB was not. 8 vCPU / 32 GB serves ~3
  concurrent simulations comfortably.
- Disk: base image (~18 GB) + ~1.5 GB per user volume (+ their outputs). 200 GB is comfortable.
- A DNS name pointing at the VM (for HTTPS via Caddy) and a GitHub OAuth app.

## Setup

1. **Seed project** – on the VM, from any full TI-Toolbox project that has a finished
   `m2m_ernie`:
   ```bash
   python3 make_seed.py /data/000 /srv/tit-seed/000 --subject ernie   # add --with-leadfields for ex-search
   ```
2. **GitHub OAuth app** – <https://github.com/settings/developers> → *New OAuth App*:
   Homepage `https://<HUB_DOMAIN>`, callback `https://<HUB_DOMAIN>/hub/oauth_callback`.
3. **Configure** – `cp .env.example .env`, fill in `HUB_DOMAIN`, `HUB_URL`, the OAuth
   client id/secret, `ADMIN_USERS`, `SEED_DIR`. Add GitHub logins to `allowed_users.txt`
   (or set `ALLOW_ALL_GITHUB_USERS=true` — every GitHub account can then burn your CPU).
4. **Build & run**
   ```bash
   docker compose --profile build-only build singleuser   # per-user image (installs jupyterhub into the TI image)
   docker compose build jupyterhub
   docker compose --profile tls up -d                      # hub + caddy
   ```
5. Open `https://<HUB_DOMAIN>`, log in with GitHub, and the example notebook is at
   `/mnt/notebooks/example_workflow.ipynb`. Deep link (used by the docs site):
   `https://<HUB_DOMAIN>/hub/user-redirect/lab/tree/notebooks/example_workflow.ipynb`

## Local smoke test (no domain, no GitHub)

```bash
cp .env.example .env
sed -i 's/^HUB_AUTH=.*/HUB_AUTH=dummy/; s#^SEED_DIR=.*#SEED_DIR=#' .env
docker compose --profile build-only build singleuser && docker compose build jupyterhub
docker compose up -d jupyterhub
# http://127.0.0.1:8000 – any username, password "ti-toolbox"
```

## Operations

| Task | Command |
|---|---|
| Who is running | `docker ps --filter name=tit-user` |
| Stop one user | admin panel at `/hub/admin`, or `docker stop tit-user-<login>` |
| Wipe a user's project | `docker volume rm tit-project-<login>` (their server must be stopped) |
| New toolbox release | `git checkout vX.Y.Z`, bump `TIT_IMAGE` in `.env` to the matching tag, rebuild `singleuser`; users get it on next start |
| Logs | `docker compose logs -f jupyterhub` |
| Bigger simulations | raise `USER_CPU_LIMIT` / `USER_MEM_LIMIT` in `.env`, restart the hub (`USER_CPU_LIMIT` also sets `TI_NIFTI_WORKERS`/`OMP_NUM_THREADS` in user containers — pools size from `os.cpu_count()`, which ignores the cgroup quota) |

Not for: `charm` head-model creation, recon-all, DWI — hours of CPU per subject.
Users who need those run the toolbox locally.

## Security notes

- The hub container has the Docker socket: it is root-equivalent on the VM. Do not run
  other tenants on the same host.
- User containers run as root *inside* their container (the TI image assumes it), with no
  access to the socket, the seed is mounted read-only, and their project is a private volume.
- Keep `ALLOW_ALL_GITHUB_USERS=false` unless you accept unbounded compute usage.
