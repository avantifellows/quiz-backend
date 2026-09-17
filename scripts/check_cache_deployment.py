"""Check ECS cache prerequisites without printing task-definition secrets."""

import argparse
import json
import re
from pathlib import Path


def check(definition, tasks=None, expected_image=None):
    containers = {c["name"]: c for c in definition["containerDefinitions"]}
    backend = containers["quiz-backend"]
    env = {e["name"]: e["value"] for e in backend.get("environment", [])}
    cache_names = {
        "CACHE_ENABLED",
        "REDIS_URL",
        "CACHE_NAMESPACE",
        "REDIS_MAX_CONNECTIONS",
    }
    if any(s["name"] in cache_names for s in backend.get("secrets", [])):
        raise ValueError(
            "Cache settings must be explicit task environment values for validation"
        )
    enabled = env.get("CACHE_ENABLED", "false").lower()
    if enabled not in {"true", "false"}:
        raise ValueError("CACHE_ENABLED must be true or false")
    enabled = enabled == "true"
    if enabled:
        redis = containers.get("redis")
        if redis is None or redis.get("essential", True):
            raise ValueError("Cache enabled requires a nonessential redis sidecar")
        if not redis.get("healthCheck"):
            raise ValueError("Redis sidecar requires a health check")
        if env.get("REDIS_URL") != "redis://localhost:6379/0":
            raise ValueError("Cache enabled requires the local Redis sidecar URL")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", env.get("CACHE_NAMESPACE", "")):
            raise ValueError("Cache enabled requires an explicit valid namespace")
        pool = env.get("REDIS_MAX_CONNECTIONS", "")
        if not pool.isdigit() or int(pool) < 1:
            raise ValueError("Cache enabled requires a positive Redis connection limit")
    if tasks is not None:
        if not expected_image:
            raise ValueError("Expected image is required for runtime validation")
        if tasks.get("failures") or not tasks.get("tasks"):
            raise ValueError("Running task inspection failed or returned no tasks")
        for task in tasks["tasks"]:
            actual = {c["name"]: c for c in task["containers"]}
            app = actual.get("quiz-backend", {})
            if (
                task.get("lastStatus") != "RUNNING"
                or app.get("lastStatus") != "RUNNING"
            ):
                raise ValueError("Backend task/container is not running")
            if (
                app.get("image") != expected_image
                or app.get("healthStatus") != "HEALTHY"
            ):
                raise ValueError(
                    "Backend image or health does not match the deployment"
                )
            if enabled:
                sidecar = actual.get("redis", {})
                if (
                    sidecar.get("lastStatus") != "RUNNING"
                    or sidecar.get("healthStatus") != "HEALTHY"
                ):
                    raise ValueError(
                        "Cache enabled but Redis sidecar is not running and healthy"
                    )
    return enabled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("definition", type=Path)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--expected-image")
    args = parser.parse_args()
    try:
        enabled = check(
            json.loads(args.definition.read_text()),
            json.loads(args.tasks.read_text()) if args.tasks else None,
            args.expected_image,
        )
    except (ValueError, KeyError) as exc:
        raise SystemExit(f"Deployment validation failed: {exc}") from None
    if enabled:
        print("Cache enabled: configuration checks passed.")
        if args.tasks:
            print("Backend image and Redis health verified on running tasks.")
        print(
            "Cache effectiveness is NOT verified: staging sign-off still requires cache-hit evidence."
        )
    else:
        print("CACHE DISABLED: this deployment does not test Redis caching.")


if __name__ == "__main__":
    main()
