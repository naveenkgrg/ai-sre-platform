import asyncio


async def execute_kubernetes(operation, resource, namespace="default"):
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

    return stdout.decode()