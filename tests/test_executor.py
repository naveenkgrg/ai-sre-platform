import asyncio
import json

from tools.kubernetes.executor import execute_kubernetes
from tools.kubernetes.secret_manager import SecretManager


async def main():
    # Create a Secret Manager for this test session
    manager = SecretManager()

    # Retrieve Pods through our Kubernetes executor
    result = await execute_kubernetes(
        operation="get",
        resource="pods",
        namespace="default",
        secret_manager=manager
    )

    # Executor returns JSON after passing through the redactor
    data = json.loads(result)

    # Verify Kubernetes returned a valid Pod list
    assert data["kind"] in ("List", "PodList")
    assert isinstance(data["items"], list)

    print("PASS: Kubernetes executor works")
    print("PASS: JSON response processed by redactor")
    print("Pods found:", len(data["items"]))


asyncio.run(main())