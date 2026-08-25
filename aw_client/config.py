import logging
import os
from typing import Optional, Union

import tomlkit
from aw_core import dirs
from aw_core.config import load_config_toml

logger = logging.getLogger(__name__)

default_config = """
[server]
hostname = "127.0.0.1"
port = "5600"
fleet_token = ""

[client]
commit_interval = 10

[server-testing]
hostname = "127.0.0.1"
port = "5666"

[client-testing]
commit_interval = 5
""".strip()


def load_config():
    return load_config_toml("aw-client", default_config)


# Machine-wide location the watcher installer writes the fleet token to. All
# watchers on a device read the same file, so the token is provisioned once per
# machine instead of once per user profile.
FLEET_TOKEN_FILENAME = "fleet-token.txt"


def fleet_token_path() -> Optional[str]:
    program_data = os.environ.get("ProgramData")
    if not program_data:
        return None
    return os.path.join(program_data, "ActivityWatchFleet", FLEET_TOKEN_FILENAME)


def load_fleet_token(config=None) -> Optional[str]:
    """Shared secret proving that a request comes from a fleet device.

    Watchers have no browser session, so once the server requires
    authentication for machine endpoints they authenticate with this token
    (sent as `Authorization: Bearer ...`). Resolution order:
      1. AW_FLEET_TOKEN environment variable (set by the start scripts)
      2. %ProgramData%\\ActivityWatchFleet\\fleet-token.txt (written by the
         watcher installer)
      3. the aw-client config's [server] fleet_token
    """
    env_token = os.environ.get("AW_FLEET_TOKEN", "").strip()
    if env_token:
        return env_token

    path = fleet_token_path()
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                token = f.read().strip()
            if token:
                return token
        except OSError as e:
            logger.warning("Failed to read fleet token %s: %s", path, e)

    try:
        server_config = (config or load_config())["server"]
        token = str(server_config.get("fleet_token") or "").strip()
        if token:
            return token
    except Exception:
        pass

    return None


def load_local_server_api_key(host: str, port: Union[int, str]) -> Optional[str]:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return None

    try:
        requested_port = int(str(port))
    except (TypeError, ValueError):
        return None

    config_dirs = [dirs.get_config_dir("aw-server-rust")]
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        xdg_config_dir = os.path.join(
            xdg_config_home, "activitywatch", "aw-server-rust"
        )
        if xdg_config_dir not in config_dirs:
            config_dirs.insert(0, xdg_config_dir)

    candidates = (
        ("config.toml", 5600),
        ("config-testing.toml", 5666),
    )

    for config_dir in config_dirs:
        for filename, default_port in candidates:
            config_path = os.path.join(config_dir, filename)
            if not os.path.isfile(config_path):
                continue

            try:
                with open(config_path, encoding="utf-8") as f:
                    config = tomlkit.parse(f.read())
                configured_port = int(str(config.get("port", default_port)))
                if configured_port != requested_port:
                    continue

                auth_config = config.get("auth", {})
                api_key = auth_config.get("api_key")
                if api_key:
                    return str(api_key)
            except Exception as e:
                logger.warning(
                    "Failed to read aw-server-rust config %s: %s", config_path, e
                )

    return None
