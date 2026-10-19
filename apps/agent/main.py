import asyncio
import json
import httpx

from apps.agent.tool_registry import TOOLS
from tools.kubernetes.executor import execute_kubernetes
from tools.kubernetes.secret_manager import SecretManager


async def run_agent(user_question):

    # Store sensitive Kubernetes values locally.
    manager = SecretManager()

    # Conversation history for Ollama.
    messages = [
        {
            "role": "system",
            "content": (
                "REQUEST_REJECTED: This operation is not supported. "
                "Allowed operations: get pods, get events in namespace default. "
                "If investigating ImagePullBackOff, use get events. "
                "Do not assume the application is missing or that no Pods exist. "
                "Do not claim rejected tools were executed."
            ),
        },
        {
            "role": "user",
            "content": user_question,
        },
    ]

    async with httpx.AsyncClient(timeout=60) as client:

        # Limit investigation to 5 rounds.
        for step in range(5):

            # 1. Ask Ollama what to do next.
            response = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen3:0.6b",
                    "messages": messages,
                    "tools": TOOLS,
                    "stream": False,
                },
            )

            response.raise_for_status()

            message = response.json()["message"]

            # Save Ollama's response in conversation history.
            messages.append(message)

            tool_calls = message.get("tool_calls", [])

            # 2. If Ollama doesn't request another tool, finish.
            if not tool_calls:
                print("\nAI Analysis:")
                print(message.get("content") or "No analysis provided.")
                return

            # 3. Execute each requested Kubernetes tool.
            for call in tool_calls:

                function = call["function"]
                args = function["arguments"]

                operation = args.get("operation")
                resource = args.get("resource")
                namespace = args.get("namespace", "default")

                # Only allow read-only Pods and Events.
                if (
                    function["name"] != "kubernetes_tool"
                    or operation != "get"
                    or resource not in {"pods", "events"}
                    or namespace != "default"
                ):
                    print("Tool request rejected:", args)

                    messages.append({
                        "role": "tool",
                        "tool_name": function["name"],
                        "content": "Tool request rejected by policy.",
                    })
                    continue

                print(f"Step {step + 1}: get {resource}")

                # 4. Execute the Kubernetes command.
                result = await execute_kubernetes(
                    operation="get",
                    resource=resource,
                    namespace="default",
                    secret_manager=manager,
                )

                data = json.loads(result)

                # Never send raw Kubernetes output to Ollama.
                summary = []

                # 5. Extract safe Pod status fields.
                if resource == "pods":

                    for pod in data.get("items", []):

                        containers = []

                        for container in pod["status"].get(
                            "containerStatuses", []
                        ):
                            containers.append({
                                "name": container["name"],
                                "reason": (
                                    container.get("state", {})
                                    .get("waiting", {})
                                    .get("reason")
                                ),
                            })

                        summary.append({
                            "name": pod["metadata"]["name"],
                            "phase": pod["status"]["phase"],
                            "containers": containers,
                        })

                # 6. Extract limited Event information.
                elif resource == "events":

                    for event in data.get("items", []):

                        summary.append({
                            "reason": event.get("reason"),
                            "type": event.get("type"),
                            "object": event.get(
                                "involvedObject", {}
                            ).get("name"),
                        })

                # 7. Return only filtered information to Ollama.
                messages.append({
                    "role": "tool",
                    "tool_name": function["name"],
                    "content": json.dumps({
                        "resource": resource,
                        "namespace": namespace,
                        "results": summary,
                    }),
                })

        print("\nInvestigation stopped: maximum 5 rounds reached.")


# Start the agent when this file is executed.
if __name__ == "__main__":

    asyncio.run(
        run_agent(
            "Use the Kubernetes tool to check Pods in the default "
            "namespace and explain why broken-app is unhealthy."
        )
    )