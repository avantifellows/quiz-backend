import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "check_cache_deployment", Path(__file__).parents[1] / "check_cache_deployment.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
check = module.check


class DeploymentChecksTest(unittest.TestCase):
    def setUp(self):
        self.definition = {
            "containerDefinitions": [
                {
                    "name": "quiz-backend",
                    "environment": [
                        {"name": "CACHE_ENABLED", "value": "true"},
                        {"name": "REDIS_URL", "value": "redis://localhost:6379/0"},
                        {"name": "CACHE_NAMESPACE", "value": "staging-test"},
                        {"name": "REDIS_MAX_CONNECTIONS", "value": "10"},
                    ],
                },
                {
                    "name": "redis",
                    "essential": False,
                    "healthCheck": {"command": ["CMD", "redis-cli", "ping"]},
                },
            ]
        }
        self.tasks = {
            "tasks": [
                {
                    "lastStatus": "RUNNING",
                    "containers": [
                        {
                            "name": "quiz-backend",
                            "lastStatus": "RUNNING",
                            "image": "repo:sha",
                            "healthStatus": "HEALTHY",
                        },
                        {
                            "name": "redis",
                            "lastStatus": "RUNNING",
                            "healthStatus": "HEALTHY",
                        },
                    ],
                }
            ]
        }

    def test_enabled_and_healthy(self):
        self.assertTrue(check(self.definition, self.tasks, "repo:sha"))

    def test_legacy_cache_disabled_definition(self):
        self.assertFalse(check({"containerDefinitions": [{"name": "quiz-backend"}]}))

    def test_missing_sidecar(self):
        self.definition["containerDefinitions"].pop()
        with self.assertRaises(ValueError):
            check(self.definition)

    def test_bad_config(self):
        for name, value in [
            ("CACHE_ENABLED", "maybe"),
            ("REDIS_URL", "redis://remote"),
            ("CACHE_NAMESPACE", ""),
            ("REDIS_MAX_CONNECTIONS", "0"),
        ]:
            with self.subTest(name=name):
                definition = copy.deepcopy(self.definition)
                for env in definition["containerDefinitions"][0]["environment"]:
                    if env["name"] == name:
                        env["value"] = value
                with self.assertRaises(ValueError):
                    check(definition)

    def test_wrong_image(self):
        with self.assertRaises(ValueError):
            check(self.definition, self.tasks, "repo:other")

    def test_unhealthy_sidecar(self):
        self.tasks["tasks"][0]["containers"][1]["healthStatus"] = "UNHEALTHY"
        with self.assertRaises(ValueError):
            check(self.definition, self.tasks, "repo:sha")

    def test_partial_task_lookup(self):
        self.tasks["failures"] = [{"reason": "MISSING"}]
        with self.assertRaises(ValueError):
            check(self.definition, self.tasks, "repo:sha")


if __name__ == "__main__":
    unittest.main()
