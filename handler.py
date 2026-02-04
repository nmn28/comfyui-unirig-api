"""
RunPod Serverless Handler for ComfyUI-UniRig API

This wraps the comfyui-api HTTP server for RunPod serverless.
Handles texture extraction and S3 upload for separate_textures mode.
"""

import runpod
import requests
import time
import os
import json
import base64
import boto3
from botocore.exceptions import ClientError

# S3 configuration from environment
S3_BUCKET = os.environ.get("S3_BUCKET", "endure-media")
S3_TEXTURES_PREFIX = os.environ.get("S3_TEXTURES_PREFIX", "avatar-textures/")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-1")

# Initialize S3 client (will use IAM role or env credentials)
s3_client = None
def get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client(
            's3',
            region_name=AWS_REGION,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
    return s3_client


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


def upload_textures_to_s3(textures_json: str, model_id: str) -> list:
    """
    Upload extracted textures to S3.

    Args:
        textures_json: JSON string containing list of texture dicts with base64 data
        model_id: Unique identifier for the model (used in S3 path)

    Returns:
        List of dicts with texture name and S3 URL
    """
    if not textures_json or textures_json == '[]':
        return []

    try:
        textures = json.loads(textures_json)
    except json.JSONDecodeError:
        print(f"[Handler] Failed to parse textures JSON")
        return []

    if not textures:
        return []

    uploaded = []
    client = get_s3_client()

    for texture in textures:
        try:
            name = texture.get('name', 'texture')
            data_b64 = texture.get('data_base64', '')
            texture_type = texture.get('type', 'unknown')

            if not data_b64:
                continue

            # Decode base64 data
            texture_data = base64.b64decode(data_b64)

            # Generate S3 key
            s3_key = f"{S3_TEXTURES_PREFIX}{model_id}/{name}.png"

            # Upload to S3
            client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=texture_data,
                ContentType='image/png',
            )

            # Generate URL
            s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

            uploaded.append({
                'name': name,
                'type': texture_type,
                'url': s3_url,
                'width': texture.get('width'),
                'height': texture.get('height'),
            })

            print(f"[Handler] Uploaded texture: {s3_key} ({len(texture_data)} bytes)")

        except Exception as e:
            print(f"[Handler] Failed to upload texture {name}: {e}")

    return uploaded


def handler(job):
    """
    RunPod handler function.

    Expected input format:
    {
        "input": {
            "endpoint": "/workflow/rig-avatar",
            "body": {
                "input": {
                    "mesh_url": "https://...",
                    "separate_textures": true
                }
            }
        }
    }

    Response includes texture_urls when separate_textures=true:
    {
        "status": "success",
        "response": {
            "fbx_output_path": "/path/to/model.fbx",
            "glb_output_path": "/path/to/model.glb",
            "texture_urls": [
                {"name": "baseColor_texture", "type": "baseColor", "url": "https://s3..."}
            ]
        }
    }
    """
    job_input = job.get("input", {})

    # Get endpoint and body from input
    endpoint = job_input.get("endpoint", "/prompt")
    body = job_input.get("body", job_input)

    # Extract model_id for S3 path (use output_name or generate one)
    input_data = body.get("input", {})
    model_id = input_data.get("output_name", f"model_{int(time.time())}")

    # Make request to local comfyui-api
    try:
        url = f"http://localhost:3000{endpoint}"
        response = requests.post(url, json=body, timeout=300)

        result = {
            "status": "success",
            "status_code": response.status_code,
        }

        # Parse response
        if response.headers.get("content-type", "").startswith("application/json"):
            api_response = response.json()

            # Check if response contains textures to upload
            # The comfyui-api returns node outputs, need to find textures_json
            textures_json = None

            # Handle different response formats from comfyui-api
            if isinstance(api_response, dict):
                # Direct output format
                if 'textures_json' in api_response:
                    textures_json = api_response['textures_json']
                # Nested outputs format
                elif 'outputs' in api_response:
                    outputs = api_response['outputs']
                    if isinstance(outputs, dict):
                        for node_id, node_output in outputs.items():
                            if isinstance(node_output, dict) and 'textures_json' in node_output:
                                textures_json = node_output['textures_json']
                                break
                            elif isinstance(node_output, list) and len(node_output) >= 3:
                                # Output is [fbx_path, glb_path, textures_json]
                                textures_json = node_output[2] if len(node_output) > 2 else None
                                break

            # Upload textures if we found any
            texture_urls = []
            if textures_json and textures_json != '[]':
                print(f"[Handler] Found textures to upload for model: {model_id}")
                texture_urls = upload_textures_to_s3(textures_json, model_id)

            # Add texture URLs to response
            if texture_urls:
                if isinstance(api_response, dict):
                    api_response['texture_urls'] = texture_urls
                    # Remove large base64 data from response
                    if 'textures_json' in api_response:
                        del api_response['textures_json']
                    if 'outputs' in api_response and isinstance(api_response['outputs'], dict):
                        for node_id in api_response['outputs']:
                            if isinstance(api_response['outputs'][node_id], dict):
                                api_response['outputs'][node_id].pop('textures_json', None)

            result["response"] = api_response
        else:
            result["response"] = response.text

        return result

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
