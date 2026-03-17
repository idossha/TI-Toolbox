"""Check for new TI-Toolbox releases on GitHub."""


import logging

logger = logging.getLogger(__name__)


def parse_version(version_str: str) -> tuple:
    """Parse a version string like '2.2.1' or 'v2.2.1' into a tuple of ints."""
    parts = version_str.strip().lstrip("v").split(".")
    result = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            pass
    return tuple(result)


def check_for_new_version(
    current_version: str,
    repo: str = "idossha/TI-Toolbox",
    timeout: float = 2.0,
) -> str | None:
    """Check GitHub for the latest release. Returns version string if newer, else None."""
    import requests

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    latest = data.get("tag_name", "").lstrip("v")
    if latest and parse_version(latest) > parse_version(current_version):
        return latest
    return None
