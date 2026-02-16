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
# Install BOTH requirements files, excluding flash_attn (installed separately below)
RUN cd custom_nodes && \
    git clone https://github.com/nmn28/ComfyUI-UniRig.git && \
    cd ComfyUI-UniRig && \
    pip install --no-cache-dir -r requirements.txt && \
    grep -v flash_attn nodes/unirig/requirements.txt | pip install --no-cache-dir -r /dev/stdin

# Install flash_attn from source (requires ninja for fast compilation)
# --no-build-isolation uses the already-installed torch instead of isolated env
# Falls back gracefully if build fails - UniRig works without it
RUN pip install --no-cache-dir ninja && \
    CUDA_HOME=/usr/local/cuda MAX_JOBS=4 pip install flash-attn --no-build-isolation || \
    echo "flash_attn build failed - continuing without it (UniRig will use standard attention)"

# Install torch-geometric packages (required for ML inference)
# The -f flag points to PyG wheel index for torch 2.8.0 + CUDA 12.8
RUN pip install --no-cache-dir \
    torch-cluster torch-scatter torch-sparse torch-geometric \
    -f https://data.pyg.org/whl/torch-2.8.0+cu128.html

# Install spconv for sparse convolutions (used in point cloud processing)
RUN pip install --no-cache-dir spconv-cu120

# Run UniRig install script (downloads Blender, models, etc.)
RUN cd custom_nodes/ComfyUI-UniRig && \
    python install.py || true

# Install AWS CLI, boto3, and RunPod SDK
RUN pip install --no-cache-dir awscli boto3 runpod requests

# =============================================================================
# CLOTHING PIPELINE: cloth-fit + Robust Weight Transfer
# =============================================================================

# Install build dependencies for cloth-fit (PolyFEM-based, C++ with cmake)
# cloth-fit requires: CMake 3.25+, Eigen3, TBB, Boost >= 1.80, OpenVDB, and many others
RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    git \
    libeigen3-dev \
    libtbb-dev \
    libspdlog-dev \
    libgmp-dev \
    libmpfr-dev \
    libblosc-dev \
    libjemalloc-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Boost 1.83 from source (Ubuntu 22.04 only has 1.74, OpenVDB needs >= 1.80)
# Using SourceForge mirror (most reliable)
RUN wget -q https://sourceforge.net/projects/boost/files/boost/1.83.0/boost_1_83_0.tar.bz2/download -O boost_1_83_0.tar.bz2 && \
    tar -xjf boost_1_83_0.tar.bz2 && \
    cd boost_1_83_0 && \
    ./bootstrap.sh --prefix=/usr/local --with-libraries=iostreams,system,filesystem,thread,regex && \
    ./b2 install -j$(nproc) && \
    cd .. && rm -rf boost_1_83_0 boost_1_83_0.tar.bz2 && \
    ldconfig

# Install OpenVDB from source (needs Boost 1.80+)
# Using version 11.0.0 which is well-tested
RUN git clone --depth 1 --branch v11.0.0 https://github.com/AcademySoftwareFoundation/openvdb.git /tmp/openvdb && \
    cd /tmp/openvdb && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
             -DOPENVDB_BUILD_PYTHON_MODULE=OFF \
             -DOPENVDB_BUILD_BINARIES=OFF \
             -DUSE_BLOSC=ON && \
    make -j$(nproc) && make install && \
    cd / && rm -rf /tmp/openvdb && \
    ldconfig

# Clone and build cloth-fit (SIGGRAPH 2025 - Intersection-free Garment Retargeting)
# https://github.com/Huangzizhou/cloth-fit
# Note: This is based on PolyFEM, the binary is called PolyFEM_bin
# Build may take 15-30 minutes due to FetchContent dependencies
RUN git clone --recursive https://github.com/Huangzizhou/cloth-fit.git /opt/cloth-fit && \
    cd /opt/cloth-fit && \
    mkdir -p build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
             -DPOLYFEM_WITH_TESTS=OFF \
             -DPOLYFEM_WITH_CUDA=OFF \
             -DBOOST_ROOT=/usr/local \
             -DBoost_NO_SYSTEM_PATHS=ON && \
    make -j$(nproc) && \
    ln -s /opt/cloth-fit/build/PolyFEM_bin /usr/local/bin/cloth-fit || \
    echo "cloth-fit build failed - check logs above"

# Copy cloth-fit example data for reference skeleton templates
RUN mkdir -p /opt/cloth-fit-templates && \
    cp -r /opt/cloth-fit/json-specs /opt/cloth-fit-templates/ || true

# Install full Blender for Robust Weight Transfer addon
# (bpy module alone doesn't support addons that use BMesh operators)
ENV BLENDER_VERSION=4.0
ENV BLENDER_URL="https://mirror.clarkson.edu/blender/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz"

RUN wget -q ${BLENDER_URL} -O /tmp/blender.tar.xz && \
    tar -xf /tmp/blender.tar.xz -C /opt && \
    mv /opt/blender-* /opt/blender && \
    ln -s /opt/blender/blender /usr/local/bin/blender && \
    rm /tmp/blender.tar.xz

# Clone Robust Weight Transfer addon (SIGGRAPH Asia 2023)
# https://github.com/sentfromspacevr/robust-weight-transfer
RUN git clone https://github.com/sentfromspacevr/robust-weight-transfer.git \
    /opt/blender/4.0/scripts/addons/robust_weight_transfer

# Create directories for clothing pipeline
RUN mkdir -p /tmp/clothing /tmp/fitted

# =============================================================================

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
