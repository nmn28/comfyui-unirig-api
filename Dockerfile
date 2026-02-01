# ComfyUI-UniRig API with RunPod Serverless Support
FROM ghcr.io/saladtechnologies/comfyui-api:comfy0.8.2-api1.17.0-torch2.8.0-cuda12.8-runtime

# Set working directory
WORKDIR /opt/ComfyUI

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

# Install ComfyUI-UniRig
RUN cd custom_nodes && \
    git clone https://github.com/PozzettiAndrea/ComfyUI-UniRig.git && \
    cd ComfyUI-UniRig && \
    pip install --no-cache-dir -r requirements.txt

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
