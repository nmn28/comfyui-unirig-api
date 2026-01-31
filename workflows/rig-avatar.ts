/**
 * Rig Avatar Endpoint
 *
 * Takes a mesh URL (GLB from Meshy/Tripo) and returns a rigged FBX.
 * This is the slow operation (~15-30 seconds) - only call once per avatar.
 *
 * POST /rig-avatar
 * {
 *   "mesh_url": "https://meshy.ai/outputs/avatar.glb",
 *   "skeleton_template": "mixamo",  // optional, default "mixamo"
 *   "output_name": "user_123_avatar" // optional
 * }
 *
 * Returns:
 * {
 *   "rigged_fbx_url": "...",
 *   "processing_time": 25.3
 * }
 */

import { z } from "zod";

// Input validation schema
const InputSchema = z.object({
  mesh_url: z.string().url().describe("URL to GLB/OBJ mesh file"),
  skeleton_template: z.enum(["mixamo", "articulationxl"]).default("mixamo")
    .describe("Skeleton type: mixamo for humanoids, articulationxl for any object"),
  output_name: z.string().optional()
    .describe("Custom output filename (without extension)"),
});

// Output schema
const OutputSchema = z.object({
  rigged_fbx_path: z.string().describe("Path to rigged FBX file"),
  processing_time: z.number().describe("Processing time in seconds"),
});

export default {
  // Endpoint configuration
  method: "POST",
  path: "/rig-avatar",

  // Schema definitions
  input: InputSchema,
  output: OutputSchema,

  // Generate ComfyUI workflow from input
  generateWorkflow(input: z.infer<typeof InputSchema>) {
    const outputName = input.output_name || `rigged_${Date.now()}`;

    return {
      // Node 1: Load the mesh from URL
      "1": {
        class_type: "UniRigLoadMesh",
        inputs: {
          source_folder: "input",
          // comfyui-api will download the URL and provide local path
          file_path: input.mesh_url,
        },
      },

      // Node 2: Load UniRig model
      "2": {
        class_type: "UniRigLoadModel",
        inputs: {
          cache_to_gpu: false,
        },
      },

      // Node 3: Auto-rig the mesh
      "3": {
        class_type: "UniRigAutoRig",
        inputs: {
          trimesh: ["1", 0],
          model: ["2", 0],
          skeleton_template: input.skeleton_template,
          fbx_name: outputName,
          target_face_count: 50000,
        },
      },
    };
  },

  // Extract output from ComfyUI results
  parseOutput(results: Record<string, any>) {
    // Node 3 outputs the FBX path
    const fbxPath = results["3"]?.outputs?.[0];

    return {
      rigged_fbx_path: fbxPath,
      processing_time: results._meta?.execution_time || 0,
    };
  },
};
