"""Run `alembic upgrade head` against the AWS database, as a one-off Fargate task:

    uv run python scripts/aws/run_migration.py

Uses the App stack's migrate task definition (same image as the API). Waits for it to
finish and exits non-zero if the migration failed; its output is in CloudWatch Logs
(log group named App-MigrateLogs...).
"""

import os
import sys
from pathlib import Path

from _stack import client, outputs


def main() -> None:
    out = outputs("App")
    ecs = client("ecs")
    response = ecs.run_task(
        cluster=out["ClusterName"],
        taskDefinition=out["MigrateTaskDefinition"],
        launchType="FARGATE",
        count=1,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": out["TaskSubnets"].split(","),
                "securityGroups": [out["TaskSecurityGroup"]],
                "assignPublicIp": "DISABLED",
            }
        },
    )
    if response["failures"]:
        sys.exit(f"couldn't start the task: {response['failures']}")
    task_arn = response["tasks"][0]["taskArn"]
    print(f"started {task_arn.rsplit('/', 1)[-1]}; waiting (a minute or two)…")

    ecs.get_waiter("tasks_stopped").wait(
        cluster=out["ClusterName"], tasks=[task_arn], WaiterConfig={"Delay": 10, "MaxAttempts": 60}
    )
    [task] = ecs.describe_tasks(cluster=out["ClusterName"], tasks=[task_arn])["tasks"]
    [container] = task["containers"]
    code = container.get("exitCode")
    if code != 0:
        reason = container.get("reason") or task.get("stoppedReason")
        sys.exit(f"migration failed (exit {code}): {reason}. See the App-MigrateLogs log group.")
    print("migration finished")


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[2])
    main()
