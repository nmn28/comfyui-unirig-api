/**
 * Animate Avatar Endpoint
 *
 * Takes a rigged FBX and an animation file, returns animated FBX.
 * This is the fast operation (~2-5 seconds) - call for each animation change.
 *
 * POST /animate-avatar
 * {
 *   "rigged_fbx_url": "s3://bucket/users/123/rigged.fbx",
 *   "animation_url": "s3://bucket/animations/idle.fbx",
 *   "output_name": "user_123_idle" // optional
 * }
 *
 * Returns:
 * {
 *   "animated_fbx_url": "...",
 *   "processing_time": 3.2
 * }
 */

import { z } from "zod";

// Input validation schema
const InputSchema = z.object({
  rigged_fbx_url: z.string().url()
    .describe("URL to rigged FBX file (from /rig-avatar)"),
  animation_url: z.string().url()
    .describe("URL to animation FBX file (Mixamo format)"),
  output_name: z.string().optional()
    .describe("Custom output filename (without extension)"),
});

// Output schema
const OutputSchema = z.object({
  animated_fbx_path: z.string().describe("Path to animated FBX file"),
  processing_time: z.number().describe("Processing time in seconds"),
});

export default {
  // Endpoint configuration
  method: "POST",
  path: "/animate-avatar",

  // Schema definitions
  input: InputSchema,
  output: OutputSchema,

  // Generate ComfyUI workflow from input
  generateWorkflow(input: z.infer<typeof InputSchema>) {
    const outputName = input.output_name || `animated_${Date.now()}`;

    // Extract animation filename from URL for the node
    const animationFilename = input.animation_url.split('/').pop() || 'animation.fbx';

    return {
      // Node 1: Load the rigged mesh from URL
      "1": {
        class_type: "UniRigLoadRiggedMesh",
        inputs: {
          source_folder: "output",
          // comfyui-api will download the URL and provide local path
          file_name: input.rigged_fbx_url,
          load_all_animations: false,
        },
      },

      // Node 2: Apply animation
      "2": {
        class_type: "UniRigApplyAnimation",
        inputs: {
          model_fbx_path: ["1", 0],
          animation_type: "mixamo",
          // comfyui-api will download the animation URL
          animation_file: input.animation_url,
          output_name: outputName,
        },
      },
    };
  },

  // Extract output from ComfyUI results
  parseOutput(results: Record<string, any>) {
    // Node 2 outputs the animated FBX path
    const fbxPath = results["2"]?.outputs?.[0];

    return {
      animated_fbx_path: fbxPath,
      processing_time: results._meta?.execution_time || 0,
    };
  },
};
