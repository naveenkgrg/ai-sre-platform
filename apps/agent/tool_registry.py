TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "kubernetes_tool",
            "description": (
                "Read Kubernetes Pods or Events. "
                "Use operation='get' and resource='pods' or 'events'. "
                "For ImagePullBackOff, inspect Events."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["get"],
                        "description": "Always use 'get', never 'get pods'.",
                    },
                    "resource": {
                        "type": "string",
                        "enum": ["pods", "events"],
                        "description": "Kubernetes resource to retrieve.",
                    },
                    "namespace": {
                        "type": "string",
                        "enum": ["default"],
                        "description": "Kubernetes namespace.",
                    },
                },
                "required": ["operation", "resource", "namespace"],
            },
        },
    }
]