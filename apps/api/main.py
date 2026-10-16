import asyncio
from contextlib import suppress

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Create the FastAPI application.
# This is the service our client will call.
app = FastAPI()


# Define the JSON request format.
# Example:
# {
#   "prompt": "Explain Kubernetes"
# }
class PromptRequest(BaseModel):
    prompt: str


# Create a POST API endpoint.
# Client will call:
# POST http://localhost:8000/generate
@app.post("/generate")
async def generate(req: PromptRequest, request: Request):

    # Call the Ollama API running locally on port 11434.
    # FastAPI acts as a wrapper/service layer around the LLM.
    try:
        async with httpx.AsyncClient(timeout=1) as client:
            ollama_request = asyncio.create_task(
                client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        # Local model we downloaded earlier.
                        "model": "qwen3:0.6b",

                        # Send the user prompt to the model.
                        "prompt": req.prompt,

                        # Return the full response in one result.
                        # Later we will change this to streaming.
                        "stream": False,

                        # Disable extra reasoning output for this experiment.
                        "think": False,
                    },
                )
            )

            try:
                while not ollama_request.done():
                    await asyncio.wait({ollama_request}, timeout=0.1)
                    if await request.is_disconnected():
                        ollama_request.cancel()
                        with suppress(asyncio.CancelledError):
                            await ollama_request
                        raise HTTPException(
                            status_code=499,
                            detail="Client disconnected before LLM inference completed",
                        )

                ollama_response = await ollama_request
            except asyncio.CancelledError:
                # The ASGI server cancelled this handler (for example, after a
                # client disconnect). Cancelling the httpx task closes its
                # upstream Ollama connection as well.
                ollama_request.cancel()
                with suppress(asyncio.CancelledError):
                    await ollama_request
                raise
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="LLM inference timed out",
        )

    # Convert Ollama's JSON response into a Python dictionary.
    data = ollama_response.json()

    # Return only the fields we care about.
    # FastAPI automatically converts this dictionary back to JSON.
    return {
        "response": data["response"],
        "input_tokens": data["prompt_eval_count"],
        "output_tokens": data["eval_count"],
        "total_duration": data["total_duration"]
    }

@app.get("/health")
def health():
    return {"status": "ok"}
