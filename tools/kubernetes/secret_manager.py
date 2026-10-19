import time
import uuid


class SecretManager:

    def __init__(self, timeout=900):
        # Store secrets in memory only
        # Default inactivity timeout = 15 minutes
        self.secrets = {}
        self.timeout = timeout

    def store(self, value, metadata):
        """
        Store a secret and return its reference.
        Metadata describes how to retrieve it again.
        """

        # Generate a unique reference
        ref = f"SECRET_{uuid.uuid4().hex}"

        self.secrets[ref] = {
            "value": value,
            "last_used": time.monotonic(),
            "status": "ACTIVE",
            "metadata": metadata.copy()
        }

        return ref

    def get(self, ref):
        """
        Retrieve a secret using its reference.

        ACTIVE  -> Return actual value internally
        EXPIRED -> Return metadata for retrieval
        NOT_FOUND -> Invalid reference
        """

        entry = self.secrets.get(ref)

        if entry is None:
            return {"status": "NOT_FOUND"}

        # Check inactivity timeout
        if entry["status"] == "ACTIVE":
            idle_time = time.monotonic() - entry["last_used"]

            if idle_time >= self.timeout:
                # Discard secret value but preserve metadata
                entry["value"] = None
                entry["status"] = "EXPIRED"

        # If expired, tell the agent how to retrieve it again
        if entry["status"] == "EXPIRED":
            return {
                "status": "EXPIRED",
                "reference": ref,
                "metadata": entry["metadata"].copy(),
                "action": "RETRIEVE_AGAIN"
            }

        # Successful use resets inactivity timer
        entry["last_used"] = time.monotonic()

        # IMPORTANT: Actual value is for trusted tools only
        # Never send this result directly to the LLM
        return {
            "status": "ACTIVE",
            "value": entry["value"]
        }

    def refresh(self, ref, new_value):
        """
        Update an expired secret after retrieving it again.
        Keep the same reference and metadata.
        """

        entry = self.secrets.get(ref)

        if entry is None:
            return {"status": "NOT_FOUND"}

        entry["value"] = new_value
        entry["last_used"] = time.monotonic()
        entry["status"] = "ACTIVE"

        return {"status": "ACTIVE"}