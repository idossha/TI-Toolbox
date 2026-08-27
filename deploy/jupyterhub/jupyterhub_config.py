"""JupyterHub configuration for the hosted TI-Toolbox.

Every user gets their own container from the TI-Toolbox image (built by
Dockerfile.singleuser), a private project volume seeded from SEED_DIR on
first start, and a CPU/memory cap. All knobs come from the environment —
see .env.example and README.md.
"""
import os

from dockerspawner import DockerSpawner
from jupyterhub.auth import DummyAuthenticator

c = get_config()  # noqa: F821

def env(name, default=None):
    return os.environ.get(name, default)

# --------------------------------------------------------------------------
# Hub
# --------------------------------------------------------------------------
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = "jupyterhub"     # service name in docker-compose
c.JupyterHub.port = 8000
c.JupyterHub.cookie_secret_file = "/srv/jupyterhub/data/cookie_secret"
c.JupyterHub.db_url = "sqlite:////srv/jupyterhub/data/jupyterhub.sqlite"
c.JupyterHub.cleanup_servers = False           # leave user servers up across hub restarts
c.JupyterHub.allow_named_servers = False

# --------------------------------------------------------------------------
# Authentication: GitHub OAuth (production) or a dummy password (local test)
# --------------------------------------------------------------------------
_allowed = {
    u.strip()
    for u in open(env("ALLOWED_USERS_FILE", "/srv/jupyterhub/allowed_users.txt")).read().splitlines()
    if u.strip() and not u.strip().startswith("#")
} if os.path.exists(env("ALLOWED_USERS_FILE", "/srv/jupyterhub/allowed_users.txt")) else set()
_admins = {u.strip() for u in env("ADMIN_USERS", "").split(",") if u.strip()}

if env("HUB_AUTH", "github") == "dummy":
    c.JupyterHub.authenticator_class = DummyAuthenticator
    c.DummyAuthenticator.password = env("DUMMY_PASSWORD", "ti-toolbox")
    c.Authenticator.allow_all = True
else:
    from oauthenticator.github import GitHubOAuthenticator
    c.JupyterHub.authenticator_class = GitHubOAuthenticator
    c.GitHubOAuthenticator.client_id = env("GITHUB_CLIENT_ID")
    c.GitHubOAuthenticator.client_secret = env("GITHUB_CLIENT_SECRET")
    c.GitHubOAuthenticator.oauth_callback_url = f"{env('HUB_URL').rstrip('/')}/hub/oauth_callback"
    if env("ALLOW_ALL_GITHUB_USERS", "false").lower() == "true":
        c.Authenticator.allow_all = True           # anyone with a GitHub account
    else:
        c.Authenticator.allowed_users = _allowed | _admins
c.Authenticator.admin_users = _admins

# --------------------------------------------------------------------------
# Spawner: one TI-Toolbox container per user
# --------------------------------------------------------------------------
c.JupyterHub.spawner_class = DockerSpawner
c.DockerSpawner.image = env("SINGLEUSER_IMAGE", "ti-toolbox-singleuser:latest")
c.DockerSpawner.network_name = env("DOCKER_NETWORK", "tit-hub")
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.remove = True                  # container removed on stop; data lives in the volume
c.DockerSpawner.prefix = "tit-user"
c.DockerSpawner.cmd = ["/usr/local/bin/start-singleuser.sh"]
c.DockerSpawner.notebook_dir = "/mnt"
c.Spawner.default_url = "/lab"
c.Spawner.http_timeout = 180                   # first start copies the ~1.5 GB seed
c.Spawner.start_timeout = 300

# Per-user project volume at /mnt/000 (seeded on first start), shared read-only seed at /seed.
PROJECT_NAME = env("PROJECT_DIR_NAME", "000")
c.DockerSpawner.volumes = {
    "tit-project-{username}": f"/mnt/{PROJECT_NAME}",
}
if env("SEED_DIR"):
    c.DockerSpawner.read_only_volumes = {env("SEED_DIR"): "/seed"}

_cpus = max(1, int(float(env("USER_CPU_LIMIT", "2"))))
c.DockerSpawner.environment = {
    "PROJECT_DIR_NAME": PROJECT_NAME,
    # Worker pools size themselves from os.cpu_count(), which ignores the cgroup
    # quota; without these a 2-core container spawns 8 mesh->NIfTI workers and OOMs.
    "TI_NIFTI_WORKERS": str(_cpus),
    "OMP_NUM_THREADS": str(_cpus),
    "LOCAL_PROJECT_DIR": f"/mnt/{PROJECT_NAME}",
    "USER": "root",
    "KMP_AFFINITY": "disabled",
    "TI_TOOLBOX_VERSION": env("TI_TOOLBOX_VERSION", "hub"),
    "TIT_HOST_OS": "jupyterhub",
}

# Resource caps per user
c.DockerSpawner.cpu_limit = float(env("USER_CPU_LIMIT", "2"))   # also drives TI_NIFTI_WORKERS above
c.DockerSpawner.mem_limit = env("USER_MEM_LIMIT", "10G")
c.DockerSpawner.extra_host_config = {
    "shm_size": "1g",
}

# --------------------------------------------------------------------------
# Idle culler: stop servers idle for CULL_TIMEOUT seconds (default 1 h)
# --------------------------------------------------------------------------
c.JupyterHub.load_roles = [
    {
        "name": "jupyterhub-idle-culler-role",
        "scopes": ["list:users", "read:users:activity", "read:servers", "delete:servers"],
        "services": ["jupyterhub-idle-culler-service"],
    }
]
c.JupyterHub.services = [
    {
        "name": "jupyterhub-idle-culler-service",
        "command": [
            "python3", "-m", "jupyterhub_idle_culler",
            f"--timeout={env('CULL_TIMEOUT', '3600')}",
            "--cull-every=300",
        ],
    }
]
