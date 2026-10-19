import asyncio
from tools.kubernetes.permissions import validate_operation
import json
from tools.kubernetes.redactor import redact_kubernetes_output

async def execute_kubernetes(operation, resource, namespace="default", secret_manager=None):
    validate_operation(operation, resource)
    if operation != "get":
        raise ValueError(f"Operation not supported yet: {operation}")

    process = await asyncio.create_subprocess_exec(
        "kubectl",
        "--context=minikube",
        "get",
        resource,
        "-n",
        namespace,
        "-o",
        "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(stderr.decode())

    # Parse the Kubernetes JSON response
    data = json.loads(stdout.decode())

    # Require a Secret Manager before returning any data
    if secret_manager is None:
        raise ValueError("SecretManager is required")

    # Redact Kubernetes Secret objects before returning
    sanitized = redact_kubernetes_output(data, secret_manager)

    return json.dumps(sanitized)