"""
RunPod Serverless Handler for ComfyUI-UniRig API

This wraps the comfyui-api HTTP server for RunPod serverless.
"""

import runpod
import requests
import time
import os

# Wait for ComfyUI API to be ready
def wait_for_api(max_wait=120):
    """Wait for the comfyui-api server to be ready"""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get("http://localhost:3000/health", timeout=5)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(2)
    return False

def handler(job):
    """
    RunPod handler function.
    
    Expected input format:
    {
        "input": {
            "endpoint": "/workflow/rig-avatar",  # or "/workflow/animate-avatar" or "/prompt"
            "body": {
                "input": {
                    "mesh_url": "https://..."
                }
            }
        }
    }
    """
    job_input = job.get("input", {})
    
    # Get endpoint and body from input
    endpoint = job_input.get("endpoint", "/prompt")
    body = job_input.get("body", job_input)
    
    # Make request to local comfyui-api
    try:
        url = f"http://localhost:3000{endpoint}"
        response = requests.post(url, json=body, timeout=300)
        
        return {
            "status": "success",
            "status_code": response.status_code,
            "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        }
    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Request timed out after 300 seconds"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Start the handler
if __name__ == "__main__":
    print("Waiting for ComfyUI API to be ready...")
    if wait_for_api():
        print("ComfyUI API ready, starting RunPod handler...")
        runpod.serverless.start({"handler": handler})
    else:
        print("ERROR: ComfyUI API failed to start")
        exit(1)
