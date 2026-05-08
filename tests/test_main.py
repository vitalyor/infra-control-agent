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


if __name__ == "__main__":
    unittest.main()

