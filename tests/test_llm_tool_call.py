import asyncio
import httpx
from tools.kubernetes.executor import execute_kubernetes
from tools.kubernetes.secret_manager import SecretManager
from apps.agent.tool_registry import TOOLS
import json
async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3:0.6b",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Use the Kubernetes tool to get pods "
                            "in the default namespace."
                        ),
                    }
                ],
                "tools": TOOLS,
                "stream": False,
            },
        )

        response.raise_for_status()

        message = response.json()["message"]

        # Show only the requested tool calls, not internal reasoning.
        print("Tool calls:", message.get("tool_calls", []))
        # Step 2: Execute the tool requested by Ollama
        manager = SecretManager()

        for call in message.get("tool_calls", []):
            function = call["function"]
            args = function["arguments"]

            # Only allow get pods in default namespace for this test
            if (
                function["name"] != "kubernetes_tool"
                or args.get("operation") != "get"
                or args.get("resource") != "pods"
                or args.get("namespace", "default") != "default"
            ):
                print("Tool request rejected:", args)
                continue

            # HERE: Call our Kubernetes executor
            result = await execute_kubernetes(
                operation="get",
                resource="pods",
                namespace="default",
                secret_manager=manager,
            )

            # Step 3: Display Pod names and statuses
            data = json.loads(result)

            for pod in data["items"]:
                print(
                    "Pod:", pod["metadata"]["name"],
                    "| Phase:", pod["status"]["phase"]
                )
            # Step 4: Build the summary only after data has been parsed and
            # every pod has been printed. It remains inside this tool-call
            # loop so each approved result is analyzed independently.
            pod_summary = []
            for pod in data["items"]:
                pod_summary.append(
                    {
                        "name": pod["metadata"]["name"],
                        "phase": pod["status"]["phase"],
                        "containers": [
                            {
                                "name": container["name"],
                                "reason": container.get("state", {})
                                .get("waiting", {})
                                .get("reason"),
                            }
                            for container in pod["status"].get(
                                "containerStatuses", []
                            )
                        ],
                    }
                )

            # Step 5: Ask Ollama to explain the pod status.
            analysis_response = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen3:0.6b",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Explain why this Kubernetes Pod is unhealthy. "
                                "Use only this status information:\n"
                                + json.dumps(pod_summary)
                            ),
                        }
                    ],
                    "stream": False,
                },
            )
            analysis_response.raise_for_status()

            print("\nAI Analysis:")
            print(analysis_response.json()["message"]["content"])


if __name__ == "__main__":
    asyncio.run(main())
