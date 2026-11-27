"""The Claude Code sandbox a sandboxed step runs in, and what Foreman passes to turn it on."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foreman.definitions.roles import ACCEPT_OPEN_READS_FLAG, RoleLoadError, load_role_text
from foreman.domain.models import Project
from foreman.domain.settings import SettingsError, settings_of
from foreman.runner import AgentRunConfig, ClaudeCodeRunner, PreflightError
from foreman.runner.base import SandboxPolicy
from foreman.runner.claude_code import NO_STDIN_PREFIX
from foreman.runner.sandbox import (
    check_machine,
    closed_paths,
    credential_env_names,
    claude_settings,
    socket_policy,
)
from tests.test_sandbox import role_text


def settings_arg(command: list[str]) -> dict:
    return json.loads(command[command.index("--settings") + 1])


class ClosedPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve() / "home"
        for name in (".ssh", ".aws", "projects/other", "projects/repo/.git/objects",
                     "projects/repo/.git/config.d", "projects/repo/src", "projects/repo/.foreman/worktrees/_sandbox-T-1",
                     "projects/repo/.foreman/worktrees/T-2", ".pyenv/versions"):
            (self.home / name).mkdir(parents=True)
        (self.home / ".bashrc").write_text("x")
        (self.home / "projects/repo/.env").write_text("SECRET=1")
        (self.home / "projects/repo/.git/HEAD").write_text("ref")
        self.sandbox = self.home / "projects/repo/.foreman/worktrees/_sandbox-T-1"
        self.objects = self.home / "projects/repo/.git/objects"

    def closed(self, *extra: Path) -> set[str]:
        paths = closed_paths([self.home], [self.sandbox, self.objects, *extra])
        return {str(path.relative_to(self.home)) for path in paths}

    def test_everything_is_closed_except_what_the_step_needs(self) -> None:
        self.assertEqual(
            self.closed(),
            {
                ".ssh", ".aws", ".pyenv", ".bashrc", "projects/other",
                "projects/repo/.env", "projects/repo/src",
                "projects/repo/.git/HEAD", "projects/repo/.git/config.d",
                "projects/repo/.foreman/worktrees/T-2",
            },
        )

    def test_a_listed_path_is_opened(self) -> None:
        closed = self.closed(self.home / ".pyenv")
        self.assertNotIn(".pyenv", closed)
        self.assertIn(".ssh", closed)

    def test_a_link_is_closed_as_a_file_and_never_followed(self) -> None:
        (self.home / "link").symlink_to(self.home / ".ssh")
        self.assertIn("link", self.closed())


class ClaudeSettingsTests(unittest.TestCase):
    def policy(self, **kw) -> SandboxPolicy:
        return SandboxPolicy(**kw)

    def test_the_sandbox_is_on_and_never_skipped(self) -> None:
        sandbox = claude_settings(self.policy())["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        self.assertIs(sandbox["failIfUnavailable"], True)
        self.assertIs(sandbox["allowUnsandboxedCommands"], False)
        self.assertIs(sandbox["autoAllowBashIfSandboxed"], True)

    def test_no_host_is_reachable_but_the_ones_listed(self) -> None:
        none = claude_settings(self.policy())["sandbox"]["network"]
        self.assertEqual(none, {"allowedDomains": [], "strictAllowlist": True})
        some = claude_settings(self.policy(allowed_hosts=("pypi.org", "*.example.com")))
        self.assertEqual(some["sandbox"]["network"]["allowedDomains"], ["pypi.org", "*.example.com"])

    def test_reads_are_closed_for_commands_and_for_the_read_tools(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw).resolve()
            (home / ".ssh").mkdir()
            (home / "box").mkdir()
            (home / ".rc").write_text("x")
            settings = claude_settings(
                self.policy(deny_roots=(home,), read_paths=(home / "box",))
            )
            self.assertEqual(settings["sandbox"]["filesystem"]["denyRead"], [str(home)])
            self.assertEqual(settings["sandbox"]["filesystem"]["allowRead"], [str(home / "box")])
            # An absolute path in a rule takes two slashes; a directory takes /**.
            self.assertEqual(
                sorted(settings["permissions"]["deny"]),
                sorted([f"Read(/{home}/.ssh/**)", f"Read(/{home}/.rc)"]),
            )

    def test_the_command_line_carries_the_settings_and_the_shell_prefix_is_readable(self) -> None:
        config = AgentRunConfig(
            backend="claude_code", model="m", prompt="p", working_dir=Path("/tmp/x"),
            session_id=None, permission_mode="bypassPermissions",
            sandbox=self.policy(allowed_hosts=("pypi.org",)),
        )
        runner = ClaudeCodeRunner()
        command = runner.build_command(config, credential_names=("ANTHROPIC_API_KEY",))
        settings = settings_arg(command)
        self.assertIn(str(NO_STDIN_PREFIX), settings["sandbox"]["filesystem"]["allowRead"])
        self.assertEqual(
            settings["sandbox"]["credentials"],
            {"envVars": [{"name": "ANTHROPIC_API_KEY", "mode": "deny"}]},
        )
        self.assertEqual(settings["sandbox"]["network"]["allowedDomains"], ["pypi.org"])

    def test_a_step_that_is_not_sandboxed_gets_no_settings(self) -> None:
        config = AgentRunConfig(
            backend="claude_code", model="m", prompt="p", working_dir=Path("/tmp/x"),
            session_id=None, permission_mode="bypassPermissions",
        )
        self.assertNotIn("--settings", ClaudeCodeRunner().build_command(config))

    def test_the_backends_keys_are_kept_from_commands(self) -> None:
        env = {"ANTHROPIC_API_KEY": "a", "openai_api_key": "b", "OPENAI_BASE_URL": "c",
               "CLAUDE_CODE_OAUTH_TOKEN": "d", "PATH": "/bin", "HOME": "/h"}
        self.assertEqual(
            credential_env_names(env),
            ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_BASE_URL", "openai_api_key"),
        )


class UnixSocketTests(unittest.TestCase):
    def test_off_by_default_nothing_is_added(self) -> None:
        settings = claude_settings(SandboxPolicy())
        self.assertNotIn("allowAllUnixSockets", settings["sandbox"]["network"])
        self.assertEqual(settings["sandbox"]["filesystem"]["denyRead"], [])

    def test_allowed_the_hosts_socket_directories_are_closed(self) -> None:
        policy = SandboxPolicy(allow_unix_sockets=True)
        shut = socket_policy(policy, uid=1234)
        self.assertTrue(set(map(str, shut.deny_roots)) >= {"/run", "/tmp"})
        # What Claude Code's own sandbox needs there stays open.
        self.assertIn(Path("/run/user/1234/cc-socks"), shut.read_paths)
        self.assertIn(Path("/tmp/claude-1234"), shut.read_paths)
        settings = claude_settings(policy)
        self.assertIs(settings["sandbox"]["network"]["allowAllUnixSockets"], True)
        self.assertIn("/run", settings["sandbox"]["filesystem"]["denyRead"])


class MachineTests(unittest.TestCase):
    def test_a_machine_without_bubblewrap_or_socat_is_refused_with_the_reason(self) -> None:
        for missing, text in (
            ({"bwrap"}, "bwrap is not installed"),
            ({"socat"}, "socat is not installed"),
            ({"bwrap", "socat"}, "bwrap and socat are not installed"),
        ):
            with self.subTest(missing=missing), self.assertRaisesRegex(PreflightError, text):
                check_machine(lambda name, missing=missing: None if name in missing else "/usr/bin/x")

    def test_a_machine_with_both_passes(self) -> None:
        check_machine(lambda name: f"/usr/bin/{name}")

    def test_the_runner_never_starts_claude_unsandboxed(self) -> None:
        runner = ClaudeCodeRunner(
            which=lambda name: None if name == "bwrap" else f"/usr/bin/{name}",
            popen_factory=lambda *a, **k: self.fail("started"),
        )
        config = AgentRunConfig(
            backend="claude_code", model="m", prompt="p", working_dir=Path("/tmp/x"),
            session_id=None, permission_mode="bypassPermissions", sandbox=SandboxPolicy(),
        )
        with self.assertRaisesRegex(PreflightError, "bwrap is not installed"):
            list(runner.run(config))


class ProjectSettingsTests(unittest.TestCase):
    def test_they_are_empty_by_default_and_host_level(self) -> None:
        from foreman.domain.settings import HOST_LEVEL_SETTINGS

        project = Project(id="p", name="P", repo_path="/r", workflow_id="w", default_branch="main")
        settings = settings_of(project)
        self.assertEqual((settings.sandbox_allowed_hosts, settings.sandbox_read_paths), ((), ()))
        self.assertIs(settings.sandbox_allow_unix_sockets, False)
        self.assertLessEqual(
            {"sandbox_allowed_hosts", "sandbox_read_paths", "sandbox_allow_unix_sockets"},
            HOST_LEVEL_SETTINGS,
        )

    def settings(self, **raw):
        return settings_of(Project(id="p", name="P", repo_path="/r", workflow_id="w",
                                   default_branch="main", settings=raw))

    def test_hosts_and_paths_are_validated(self) -> None:
        ok = self.settings(sandbox_allowed_hosts=["pypi.org", "*.example.com"],
                           sandbox_read_paths=["/opt/x", "~/.pyenv"])
        self.assertEqual(ok.sandbox_allowed_hosts, ("pypi.org", "*.example.com"))
        for bad in ({"sandbox_allowed_hosts": ["https://pypi.org"]},
                    {"sandbox_allowed_hosts": ["a b"]},
                    {"sandbox_read_paths": ["relative/path"]},
                    {"sandbox_read_paths": ["/a/../b"]}):
            with self.subTest(bad=bad), self.assertRaises(SettingsError):
                self.settings(**bad)


class CodexRoleLoadTests(unittest.TestCase):
    def codex(self, scope: str, flags: str = "") -> str:
        return role_text(agent=f'run_scope = "{scope}"\n').replace(
            'backend = "claude_code"', 'backend = "codex"'
        ).replace('[agent.tools]', f'[agent.flags]\n{flags}\n\n[agent.tools]')

    def test_a_sandboxed_role_on_codex_is_refused_naming_why(self) -> None:
        with self.assertRaisesRegex(RoleLoadError, "Codex cannot enforce it.*home directory"):
            load_role_text(self.codex("sandbox"), "r.toml")

    def test_it_can_be_accepted_with_the_open_reads_named(self) -> None:
        role = load_role_text(self.codex("sandbox", f"{ACCEPT_OPEN_READS_FLAG} = true"), "r.toml")
        self.assertEqual(role.run_scope, "sandbox")

    def test_the_other_scopes_load_on_codex(self) -> None:
        for scope in ("none", "branch"):
            self.assertEqual(load_role_text(self.codex(scope), "r.toml").run_scope, scope)

    def test_a_sandboxed_role_loads_on_claude_code(self) -> None:
        self.assertEqual(
            load_role_text(role_text(agent='run_scope = "sandbox"'), "r.toml").run_scope, "sandbox"
        )


if __name__ == "__main__":
    unittest.main()
