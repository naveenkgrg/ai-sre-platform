from tools.kubernetes.secret_manager import SecretManager
from tools.kubernetes.redactor import redact_kubernetes_secret

# Initialize Secret Manager
manager = SecretManager()

# Fake Kubernetes Secret (Base64-encoded password123)
secret = {
    "kind": "Secret",
    "metadata": {
        "name": "db-credentials",
        "namespace": "default"
    },
    "data": {
        "password": "cGFzc3dvcmQxMjM="
    }
}

# Redact the Secret and store its value in memory
result = redact_kubernetes_secret(secret, manager)

# Verify that the actual value was replaced
reference = result["data"]["password"]

assert reference.startswith("SECRET_")
assert reference != secret["data"]["password"]
assert len(manager.secrets) == 1
assert manager.get(reference)["value"] == b"password123"

print("PASS: Secret value replaced with reference")
print("PASS: Actual value stored in memory")
print("PASS: Secret retrieval works")

from tools.kubernetes.redactor import redact_kubernetes_output

# Simulate kubectl get secrets -o json
secret_list = {
    "kind": "SecretList",
    "items": [
        {
            "kind": "Secret",
            "metadata": {"name": "db-secret", "namespace": "default"},
            "data": {"password": "cGFzc3dvcmQxMjM="}
        },
        {
            "kind": "Secret",
            "metadata": {"name": "api-secret", "namespace": "default"},
            "data": {"token": "dGVzdC10b2tlbg=="}
        }
    ]
}

# Redact both Secrets
result = redact_kubernetes_output(secret_list, manager)

# Verify neither Secret exposes its original value
for original, sanitized in zip(secret_list["items"], result["items"]):
    for key in original["data"]:
        reference = sanitized["data"][key]
        assert reference.startswith("SECRET_")
        assert reference != original["data"][key]

print("PASS: Multiple Kubernetes Secrets redacted")