import os
import subprocess

from fastapi import FastAPI, Header, HTTPException

# This small webhook service receives Grafana alert notifications.
app = FastAPI()

# Grafana must send this value as a Bearer token. Reading it from the
# environment keeps the secret out of source control.
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


@app.post("/notify")
async def notify(payload: dict, authorization: str | None = Header(default=None)):
    """Show a macOS notification for each firing or resolved Grafana alert."""

    # FastAPI reads the HTTP Authorization header into this parameter.
    # Reject unauthenticated webhooks before inspecting their payload.
    if authorization != f"Bearer {WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Grafana groups alert instances under the "alerts" list. Missing or empty
    # lists are valid and simply result in no desktop notifications.
    for alert in payload.get("alerts", []):
        status = alert.get("status", "unknown")
        name = alert.get("labels", {}).get("alertname", "LLM Alert")

        # Ignore states such as pending; only notify on a problem or recovery.
        if status not in ("firing", "resolved"):
            continue

        message = f"{name}: {status.upper()}"

        # Use osascript's argv support so the message is passed as data rather
        # than interpolated into AppleScript. This displays a native macOS
        # notification and raises an error if macOS cannot create it.
        subprocess.run(
            [
                "osascript",
                "-e",
                "on run argv\n"
                "display notification (item 1 of argv) "
                'with title "AI-SRE Alert" sound name "Glass"\n'
                "end run",
                message,
            ],
            check=True,
        )

    # Grafana treats any 2xx response as successful webhook delivery.
    return {"status": "ok"}
