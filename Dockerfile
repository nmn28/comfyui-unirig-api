# ComfyUI-UniRig API with RunPod Serverless Support
# Uses forked repos with mesh URL preprocessing and OUTPUT_NODE fix

# Stage 1: Build forked comfyui-api
FROM node:20-slim AS api-builder

WORKDIR /build

# Clone and build forked comfyui-api with mesh URL preprocessing
RUN apt-get update && apt-get install -y git && \
    git clone https://github.com/nmn28/comfyui-api.git . && \
    npm install && \
    npm run build && \
    npm run build-binary

# Stage 2: Final image
FROM ghcr.io/saladtechnologies/comfyui-api:comfy0.8.2-api1.17.0-torch2.8.0-cuda12.8-runtime

# Set working directory
WORKDIR /opt/ComfyUI

# Copy our forked comfyui-api binary (replaces the original)
COPY --from=api-builder /build/bin/comfyui-api /comfyui-api
RUN chmod +x /comfyui-api

# Install system dependencies for UniRig + Blender
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglu1-mesa \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxi6 \
    libxxf86vm1 \
    libxfixes3 \
    libxkbcommon0 \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install ComfyUI-UniRig from our fork (with OUTPUT_NODE fix)
RUN cd custom_nodes && \
    git clone https://github.com/nmn28/ComfyUI-UniRig.git && \
    cd ComfyUI-UniRig && \
    pip install --no-cache-dir -r requirements.txt

# Install python-box (for YAML config loading) and bpy (Blender Python)
RUN pip install --no-cache-dir python-box bpy lightning

# Run UniRig install script (downloads Blender, models, etc.)
RUN cd custom_nodes/ComfyUI-UniRig && \
    python install.py || true

# Install AWS CLI, boto3, and RunPod SDK
RUN pip install --no-cache-dir awscli boto3 runpod requests

# Copy workflows
COPY workflows/ /workflows/

# Copy manifest
COPY manifest.yaml /manifest.yaml

# Copy RunPod handler and start script
COPY handler.py /handler.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Set manifest path
ENV MANIFEST=/manifest.yaml

# Expose ports (for local testing)
EXPOSE 3000 8188

# Health check (for local testing)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Use start script that runs both comfyui-api and runpod handler
CMD ["/start.sh"]
