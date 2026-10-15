import json
import time
import urllib.request

URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:0.6b"

payload = {
    "model": MODEL,
    "prompt": "Explain Kubernetes readiness probes in one sentence.",
    "stream": True,
    "think": False,
    "keep_alive": "5m"
}

req = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"}
)

start = time.perf_counter()
first_token = None
final = None

with urllib.request.urlopen(req) as response:
    for line in response:
        chunk = json.loads(line)

        if chunk.get("response") and first_token is None:
            first_token = time.perf_counter()

        if chunk.get("done"):
            final = chunk

print("TTFT ms:",
      round((first_token - start) * 1000, 1))

print("Input tokens:",
      final["prompt_eval_count"])

print("Output tokens:",
      final["eval_count"])

print("Total ms:",
      round(final["total_duration"] / 1e6, 1))

print("Tokens/sec:",
      round(final["eval_count"] /
            (final["eval_duration"] / 1e9), 1))
