# ComfyUI-UniRig API

REST API for automatic 3D avatar rigging and animation using UniRig.

## Endpoints

### POST /rig-avatar (Slow: 15-30 seconds)
Rigs a mesh with a Mixamo-compatible skeleton. Call once per avatar.

```bash
curl -X POST http://localhost:3000/rig-avatar \
  -H "Content-Type: application/json" \
  -d '{
    "mesh_url": "https://meshy.ai/outputs/avatar.glb",
    "skeleton_template": "mixamo"
  }'
```

Response:
```json
{
  "rigged_fbx_path": "/opt/ComfyUI/output/rigged_avatar.fbx",
  "processing_time": 25.3
}
```

### POST /animate-avatar (Fast: 2-5 seconds)
Applies an animation to an already-rigged avatar. Call for each animation.

```bash
curl -X POST http://localhost:3000/animate-avatar \
  -H "Content-Type: application/json" \
  -d '{
    "rigged_fbx_url": "s3://bucket/users/123/rigged.fbx",
    "animation_url": "s3://bucket/animations/idle.fbx"
  }'
```

Response:
```json
{
  "animated_fbx_path": "/opt/ComfyUI/output/animated_avatar.fbx",
  "processing_time": 3.2
}
```

## Build & Run

### Local Development
```bash
docker build -t comfyui-unirig-api .
docker run --gpus all -p 3000:3000 -p 8188:8188 comfyui-unirig-api
```

### Deploy to RunPod
```bash
# Push to container registry
docker tag comfyui-unirig-api your-registry/comfyui-unirig-api:latest
docker push your-registry/comfyui-unirig-api:latest

# Create RunPod serverless endpoint with the image
```

### Deploy to SaladCloud
```bash
# Push to GHCR
docker tag comfyui-unirig-api ghcr.io/your-org/comfyui-unirig-api:latest
docker push ghcr.io/your-org/comfyui-unirig-api:latest

# Deploy via SaladCloud console
```

## S3 Configuration

For S3 URL support, set these environment variables:
```bash
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_DEFAULT_REGION=us-east-1
```

Or use IAM roles if running on AWS.

## Animation Files

Animations must have Mixamo bone naming (`mixamorig:Hips`, etc.).

To convert UE5 animations to Mixamo format:
```bash
cd /path/to/endureworkspace
./run_animation_converter.sh --recommended
```

Upload converted animations to S3:
```bash
aws s3 sync mixamo_animations_converted/ s3://your-bucket/animations/
```

## Pipeline Overview

```
User Photo
    ↓
Meshy/Tripo (30-60s) → GLB mesh
    ↓
/rig-avatar (15-30s) → Rigged FBX (save to S3)
    ↓
/animate-avatar (2-5s) → Animated FBX
    ↓
Frontend displays animated avatar
    ↓
User clicks different animation
    ↓
/animate-avatar (2-5s) → Different animation (fast!)
```

## Cost Estimate

| Operation | Time | Cost (RunPod 4090) |
|-----------|------|-------------------|
| Rig avatar | 15-30s | ~$0.005 |
| Animate avatar | 2-5s | ~$0.001 |

Per user: ~$0.006 initial + $0.001 per animation change
