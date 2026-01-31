# ComfyUI-UniRig API
# Combines ComfyUI + UniRig + SaladTechnologies API wrapper
#
# Build:
#   docker build -t comfyui-unirig-api .
#
# Run:
#   docker run --gpus all -p 3000:3000 -p 8188:8188 comfyui-unirig-api

FROM ghcr.io/saladtechnologies/comfyui-api:comfy0.8.2-api1.17.0-torch2.8.0-cuda12.8-runtime

# Set working directory
WORKDIR /opt/ComfyUI

# Install ALL system dependencies for UniRig + Blender before install.py
# (install.py tries to use sudo which doesn't exist in container)
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
# Skip apt install since we did it above
RUN cd custom_nodes/ComfyUI-UniRig && \
    python install.py || true

# Install AWS CLI for S3 access (optional, for debugging)
RUN pip install --no-cache-dir awscli boto3

# Copy custom workflow endpoints
COPY workflows/ /workflows/

# Copy manifest for configuration
COPY manifest.yaml /manifest.yaml
ENV MANIFEST=/manifest.yaml

# Expose ports
# 3000 = API server
# 8188 = ComfyUI (internal)
EXPOSE 3000 8188

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Start the API server
CMD ["./comfyui-api"]
