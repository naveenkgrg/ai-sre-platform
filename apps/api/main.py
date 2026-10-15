from fastapi import FastAPI
from pydantic import BaseModel
import requests

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
def generate(req: PromptRequest):

    # Call the Ollama API running locally on port 11434.
    # FastAPI acts as a wrapper/service layer around the LLM.
    ollama_response = requests.post(
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
            "think": False
        }
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
