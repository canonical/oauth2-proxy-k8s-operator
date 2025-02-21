# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import ExecError

from cli import CommandLine


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_oauth2_proxy_service_version(self, command_line: CommandLine) -> None:
        expected = "v7.6.0"
        with patch.object(
            command_line,
            "_run_cmd",
            return_value=(f"oauth2-proxy {expected} (built with go1.21.7)"),
        ) as run_cmd:
            actual = command_line.get_oauth2_proxy_service_version()
            assert actual == expected
            run_cmd.assert_called_with(["/bin/oauth2-proxy", "--version"])

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected = ["cmd"], "stdout"

        mocked_process = MagicMock(wait_output=MagicMock(return_value=(expected, "")))
        mocked_container.exec.return_value = mocked_process

        actual = command_line._run_cmd(cmd)

        assert actual == expected
        mocked_container.exec.assert_called_once_with(cmd, timeout=20, environment=None)

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
