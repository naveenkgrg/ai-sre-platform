import asyncio
import json

from tools.kubernetes.executor import execute_kubernetes
from tools.kubernetes.secret_manager import SecretManager


async def main():
    manager = SecretManager()

    # Retrieve Secrets from our actual Minikube cluster
    result = await execute_kubernetes(
        operation="get",
        resource="secrets",
        namespace="default",
        secret_manager=manager
    )

    data = json.loads(result)

    # Find the test Secret
    secret = next(
        item for item in data["items"]
        if item["metadata"]["name"] == "test-ai-secret"
    )

    # The password should now be a reference
    reference = secret["data"]["password"]

    assert reference.startswith("SECRET_")

    # Verify the actual value is stored internally
    stored = manager.get(reference)
    assert stored["status"] == "ACTIVE"
    assert stored["value"] == b"fake-password-123"

    # Ensure the original password and Base64 value aren't exposed
    assert "fake-password-123" not in result
    assert "ZmFrZS1wYXNzd29yZC0xMjM=" not in result

    print("PASS: Kubernetes Secret retrieved")
    print("PASS: Secret value replaced with reference")
    print("PASS: Actual value stored internally")
    print("PASS: Secret value not exposed in executor response")

    import time

    # Shorten timeout for testing
    manager.timeout = 2

    # Wait until the secret expires
    await asyncio.sleep(3)

    expired = manager.get(reference)

    assert expired["status"] == "EXPIRED"
    assert expired["metadata"]["name"] == "test-ai-secret"
    assert expired["metadata"]["key"] == "password"

    print("PASS: Secret expired after inactivity")
    print("PASS: Retrieval metadata preserved")


asyncio.run(main())
