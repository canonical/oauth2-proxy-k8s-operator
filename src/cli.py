# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import re
from typing import Optional

from ops.model import Container
from ops.pebble import Error, ExecError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"v(\w+\.)+(\w)+")


class CommandLine:
    """A helper object for interacting with the OAuth2 Proxy command line."""
    def __init__(self, container: Container) -> None:
        self.container = container

    def get_oauth2_proxy_service_version(self) -> Optional[str]:
        """Get OAuth2 Proxy application version."""
        cmd = ["/bin/oauth2-proxy", "--version"]
        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the service version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched[0] if matched else None

    def _run_cmd(self, cmd: list[str], timeout: float = 20, environment: Optional[dict] = None) -> str:
        logger.debug("Running command: %s", cmd)
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        try:
            stdout, _ = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout
