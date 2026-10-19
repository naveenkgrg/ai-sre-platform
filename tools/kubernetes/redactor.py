import base64
import copy


def redact_kubernetes_secret(secret, secret_manager, context="minikube"):
    """
    Redact a Kubernetes Secret object.

    1. Extract sensitive values.
    2. Store them in SecretManager.
    3. Replace them with references.
    4. Return the sanitized object.
    """

    # Copy the object so we don't modify the original response.
    sanitized = copy.deepcopy(secret)

    # Only process Kubernetes Secret objects.
    if sanitized.get("kind") != "Secret":
        raise ValueError("Expected a Kubernetes Secret object")

    # Identify where this Secret came from.
    name = sanitized["metadata"]["name"]
    namespace = sanitized["metadata"].get("namespace", "default")

    # Kubernetes stores Secret data as Base64-encoded values.
    for key, encoded_value in sanitized.get("data", {}).items():

        # Decode to bytes to support both text and binary secrets.
        value = base64.b64decode(encoded_value, validate=True)

        # Metadata allows the trusted tool to retrieve this value later.
        metadata = {
            "context": context,
            "namespace": namespace,
            "resource": "secret",
            "name": name,
            "key": key
        }

        # Store the actual value and receive an opaque reference.
        reference = secret_manager.store(value, metadata)

        # Replace the sensitive value in the LLM-facing response.
        sanitized["data"][key] = reference

    # stringData may appear in submitted manifests.
    # These values are plain text, so no Base64 decoding is needed.
    for key, value in sanitized.get("stringData", {}).items():
        metadata = {
            "context": context,
            "namespace": namespace,
            "resource": "secret",
            "name": name,
            "key": key
        }

        reference = secret_manager.store(value, metadata)
        sanitized["stringData"][key] = reference

    return sanitized

def redact_kubernetes_output(data, secret_manager, context="minikube"):
    """
    Redact Kubernetes Secret objects and SecretLists.
    """

    kind = data.get("kind")

    # Single Kubernetes Secret
    if kind == "Secret":
        return redact_kubernetes_secret(data, secret_manager, context)

    # Kubernetes list containing multiple resources
    if isinstance(data.get("items"), list):
        sanitized = copy.deepcopy(data)

        sanitized["items"] = [
            redact_kubernetes_output(item, secret_manager, context)
            for item in sanitized["items"]
        ]

        return sanitized

    # Other resource types are unchanged for now
    return copy.deepcopy(data)