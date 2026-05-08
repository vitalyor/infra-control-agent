from __future__ import annotations

import importlib.util
import os
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_agent():
    os.environ.setdefault("AGENT_API_TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("infra_control_agent_main", ROOT / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load_agent()


class AgentV2Tests(unittest.TestCase):
    def test_operations_registry_non_empty(self) -> None:
        self.assertTrue(len(agent.OPERATIONS) >= 10)

    def test_operations_scripts_exist(self) -> None:
        for op in agent.OPERATIONS.values():
            self.assertTrue(op.script_path.exists(), f"missing script for {op.operation_id}")

    def test_create_job_unknown_operation(self) -> None:
        with self.assertRaises(ValueError):
            agent._create_job("missing.operation", {}, dry_run=True)

    def test_prune_jobs_ok(self) -> None:
        result = agent._prune_jobs(max_age_s=0, max_count=1)
        self.assertTrue(result["ok"])

    def test_to_params_scalars_only(self) -> None:
        payload = {"a": 1, "b": True, "c": "x", "d": {"nested": 1}}
        params = agent._to_params(payload, exclude=set())
        self.assertEqual(params["a"], 1)
        self.assertNotIn("d", params)

    def test_alias_node_install_defaults_include_ufw_strict(self) -> None:
        params = agent._alias_params("/v1/remnawave/node/install", {"domain": "example.com", "node_secret_key": "s"})
        self.assertEqual(params["UFW_STRICT"], "true")

    def test_alias_node_install_cert_force_renewal(self) -> None:
        params = agent._alias_params(
            "/v1/remnawave/node/install",
            {"domain": "example.com", "node_secret_key": "s", "cert_force_renewal": True},
        )
        self.assertEqual(params["CERT_FORCE_RENEWAL"], "true")

    def test_job_error_code_mappings(self) -> None:
        self.assertEqual(agent._job_error_code({"exit_code": None, "stderr": ""}), "timeout")
        self.assertEqual(
            agent._job_error_code({"exit_code": 2, "stderr": "required command not found: docker"}),
            "missing_dependency_docker",
        )
        self.assertEqual(
            agent._job_error_code({"exit_code": 1, "stderr": "Some challenges have failed."}),
            "cert_issue_http_challenge",
        )
        self.assertEqual(
            agent._job_error_code({"exit_code": 2, "stderr": "DIAG_STACK_COMPOSE_MISSING dir=/opt/remnanode"}),
            "stack_compose_missing",
        )

    def test_alias_system_reboot_params(self) -> None:
        params = agent._alias_params(
            "/v1/system/reboot",
            {"delay_sec": 5, "mode": "soft", "wait_timeout_sec": 120, "poll_sec": 3},
        )
        self.assertEqual(params["REBOOT_DELAY_SEC"], "5")
        self.assertEqual(params["REBOOT_MODE"], "soft")
        self.assertEqual(params["REBOOT_WAIT_TIMEOUT_SEC"], "120")
        self.assertEqual(params["REBOOT_POLL_SEC"], "3")


if __name__ == "__main__":
    unittest.main()
