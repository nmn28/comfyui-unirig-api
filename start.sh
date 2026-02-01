#!/bin/bash

# Start ComfyUI API in background
./comfyui-api &

# Wait a moment for it to start initializing
sleep 5

# Start RunPod handler (this blocks and handles jobs)
python /handler.py
