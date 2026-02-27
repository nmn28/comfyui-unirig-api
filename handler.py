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
import subprocess
import boto3
from botocore.exceptions import ClientError

# S3 configuration from environment
S3_BUCKET = os.environ.get("S3_BUCKET", "endure-media")
S3_TEXTURES_PREFIX = os.environ.get("S3_TEXTURES_PREFIX", "avatar-textures/")
S3_CLOTHING_PREFIX = os.environ.get("S3_CLOTHING_PREFIX", "avatars/")
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


def upload_rigged_model_to_s3(local_path: str, model_id: str, file_type: str) -> str:
    """
    Upload rigged model (GLB or FBX) to S3.

    Args:
        local_path: Path to local file
        model_id: Unique identifier for the model (used in S3 path)
        file_type: File extension (glb or fbx)

    Returns:
        S3 URL of uploaded file, or empty string on failure
    """
    if not local_path or not os.path.exists(local_path):
        print(f"[Handler] Rigged model file not found: {local_path}")
        return ""

    try:
        client = get_s3_client()

        # Generate S3 key: avatars/rigged/{model_id}.{file_type}
        s3_key = f"avatars/rigged/{model_id}.{file_type}"

        # Read file
        with open(local_path, 'rb') as f:
            file_data = f.read()

        # Determine content type
        content_type = 'model/gltf-binary' if file_type == 'glb' else 'application/octet-stream'

        # Upload to S3
        client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_data,
            ContentType=content_type,
        )

        # Generate URL
        s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

        print(f"[Handler] Uploaded rigged model: {s3_key} ({len(file_data)} bytes)")
        return s3_url

    except Exception as e:
        print(f"[Handler] Failed to upload rigged model: {e}")
        return ""


def find_output_files(model_id: str, output_dir: str = "/opt/ComfyUI/output") -> tuple:
    """
    Find GLB and FBX output files in the ComfyUI output directory.

    Args:
        model_id: The model identifier (e.g., avatar_xxx)
        output_dir: Directory to search for output files

    Returns:
        Tuple of (glb_path, fbx_path) - paths may be empty if not found
    """
    glb_path = ""
    fbx_path = ""

    if not os.path.exists(output_dir):
        print(f"[Handler] Output directory not found: {output_dir}")
        return glb_path, fbx_path

    # Look for files matching the model_id pattern
    for filename in os.listdir(output_dir):
        filepath = os.path.join(output_dir, filename)
        if not os.path.isfile(filepath):
            continue

        # Match files containing the model_id
        if model_id in filename:
            if filename.endswith('.glb'):
                glb_path = filepath
                print(f"[Handler] Found GLB: {filepath}")
            elif filename.endswith('.fbx'):
                fbx_path = filepath
                print(f"[Handler] Found FBX: {filepath}")

    # If no exact match, try to find most recent files
    if not glb_path or not fbx_path:
        import glob
        glb_files = sorted(glob.glob(os.path.join(output_dir, "*.glb")), key=os.path.getmtime, reverse=True)
        fbx_files = sorted(glob.glob(os.path.join(output_dir, "*.fbx")), key=os.path.getmtime, reverse=True)

        if not glb_path and glb_files:
            glb_path = glb_files[0]
            print(f"[Handler] Using most recent GLB: {glb_path}")
        if not fbx_path and fbx_files:
            fbx_path = fbx_files[0]
            print(f"[Handler] Using most recent FBX: {fbx_path}")

    return glb_path, fbx_path


def optimize_glb(input_path: str, output_path: str = None) -> str:
    """
    Optimize GLB with mesh decimation, texture resize, and Draco compression.
    Uses gltf-transform CLI for ~90% file size reduction.

    Args:
        input_path: Path to input GLB file
        output_path: Path for optimized output (default: input_optimized.glb)

    Returns:
        Path to optimized GLB file, or original if optimization fails
    """
    if not input_path or not os.path.exists(input_path):
        return input_path

    if not output_path:
        output_path = input_path.replace('.glb', '_optimized.glb')

    try:
        # gltf-transform optimize with:
        # --simplify: mesh decimation (200k verts -> ~20k)
        # --simplify-ratio 0.1: keep 10% of vertices
        # --texture-resize 1024: downscale textures from 4096 to 1024
        # --compress draco: apply Draco compression
        cmd = [
            'gltf-transform', 'optimize',
            input_path, output_path,
            '--simplify',
            '--simplify-ratio', '0.1',
            '--texture-resize', '1024',
            '--compress', 'draco',
        ]

        print(f"[Handler] Optimizing GLB: {input_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode == 0 and os.path.exists(output_path):
            orig_size = os.path.getsize(input_path)
            opt_size = os.path.getsize(output_path)
            reduction = 100 - (opt_size / orig_size * 100)
            print(f"[Handler] GLB optimized: {orig_size:,} -> {opt_size:,} bytes ({reduction:.0f}% reduction)")
            return output_path
        else:
            print(f"[Handler] GLB optimization failed: {result.stderr}")
            return input_path  # Fall back to unoptimized

    except subprocess.TimeoutExpired:
        print(f"[Handler] GLB optimization timed out after 120s")
        return input_path
    except Exception as e:
        print(f"[Handler] GLB optimization error: {e}")
        return input_path  # Fall back to unoptimized


def upload_clothing_to_s3(local_path: str, user_id: str, garment_id: str) -> str:
    """
    Upload fitted/rigged clothing GLB to S3.

    Args:
        local_path: Path to local GLB file
        user_id: User identifier for S3 path
        garment_id: Garment identifier for S3 path

    Returns:
        S3 URL of uploaded file
    """
    if not os.path.exists(local_path):
        print(f"[Handler] Clothing file not found: {local_path}")
        return ""

    try:
        client = get_s3_client()

        # Generate S3 key: avatars/{user_id}/clothing/{garment_id}.glb
        s3_key = f"{S3_CLOTHING_PREFIX}{user_id}/clothing/{garment_id}.glb"

        # Read file
        with open(local_path, 'rb') as f:
            file_data = f.read()

        # Upload to S3
        client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_data,
            ContentType='model/gltf-binary',
        )

        # Generate URL
        s3_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

        print(f"[Handler] Uploaded clothing: {s3_key} ({len(file_data)} bytes)")
        return s3_url

    except Exception as e:
        print(f"[Handler] Failed to upload clothing: {e}")
        return ""


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

    # Extract identifiers for S3 paths
    input_data = body.get("input", {})
    model_id = input_data.get("output_name", f"model_{int(time.time())}")
    user_id = input_data.get("user_id", "anonymous")
    garment_id = input_data.get("garment_id", model_id)

    # Check if this is a clothing workflow
    is_clothing_workflow = "fit-clothing" in endpoint

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

            # Handle rig-avatar workflow - upload GLB and FBX to S3
            is_rig_workflow = "rig-avatar" in endpoint
            if is_rig_workflow:
                print(f"[Handler] Processing rig-avatar workflow for model: {model_id}")

                # Find output files in the ComfyUI output directory
                glb_path, fbx_path = find_output_files(model_id)

                # Upload to S3 and get URLs
                glb_url = ""
                fbx_url = ""

                if glb_path:
                    # Optimize GLB before upload (mesh decimation + texture resize + Draco)
                    # Reduces ~29MB -> ~3MB for mobile delivery
                    optimized_glb = optimize_glb(glb_path)
                    glb_url = upload_rigged_model_to_s3(optimized_glb, model_id, "glb")
                if fbx_path:
                    fbx_url = upload_rigged_model_to_s3(fbx_path, model_id, "fbx")

                # Update response with S3 URLs
                # Set directly on api_response so Go backend finds them at output["response"]["glb_output_path"]
                if isinstance(api_response, dict):
                    api_response['glb_output_path'] = glb_url
                    api_response['fbx_output_path'] = fbx_url

                print(f"[Handler] Rig workflow complete - GLB: {glb_url}, FBX: {fbx_url}")

            # Handle clothing workflow outputs - upload GLB to S3
            if is_clothing_workflow and isinstance(api_response, dict):
                clothing_url = None

                # Find clothing output path in response
                if 'outputs' in api_response and isinstance(api_response['outputs'], dict):
                    for node_id, node_output in api_response['outputs'].items():
                        # TransferSkinWeights returns (rigged_garment_path,)
                        # CombineAvatarClothing returns (combined_path,)
                        if isinstance(node_output, list) and len(node_output) > 0:
                            output_path = node_output[0]
                            if isinstance(output_path, str) and output_path.endswith('.glb'):
                                # Upload to S3
                                clothing_url = upload_clothing_to_s3(output_path, user_id, garment_id)
                                if clothing_url:
                                    print(f"[Handler] Clothing uploaded: {clothing_url}")
                                break
                        elif isinstance(node_output, dict):
                            # Check for path keys
                            for key in ['rigged_garment_path', 'combined_path', 'output_path']:
                                if key in node_output:
                                    output_path = node_output[key]
                                    if isinstance(output_path, str) and output_path.endswith('.glb'):
                                        clothing_url = upload_clothing_to_s3(output_path, user_id, garment_id)
                                        if clothing_url:
                                            print(f"[Handler] Clothing uploaded: {clothing_url}")
                                        break

                # Add clothing URL to response
                if clothing_url:
                    api_response['clothing_url'] = clothing_url
                    api_response['user_id'] = user_id
                    api_response['garment_id'] = garment_id

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
