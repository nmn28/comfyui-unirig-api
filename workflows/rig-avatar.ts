/**
 * Rig Avatar Endpoint
 * POST /workflow/rig-avatar
 *
 * Takes a mesh URL (GLB from Meshy/Tripo) and returns a rigged FBX.
 * This is the slow operation (~15-30 seconds) - only call once per avatar.
 */

import { z } from "zod";

const ComfyNodeSchema = z.object({
  inputs: z.any(),
  class_type: z.string(),
  _meta: z.any().optional(),
});

type ComfyNode = z.infer<typeof ComfyNodeSchema>;
type ComfyPrompt = Record<string, ComfyNode>;

interface Workflow {
  RequestSchema: z.ZodObject<any, any>;
  generateWorkflow: (input: any) => Promise<ComfyPrompt> | ComfyPrompt;
  description?: string;
  summary?: string;
}

const RequestSchema = z.object({
  mesh_url: z.string().describe("URL to GLB/OBJ/FBX mesh file"),
  skeleton_template: z
    .enum(["mixamo", "articulationxl"])
    .optional()
    .default("mixamo")
    .describe("Skeleton type: mixamo for humanoids, articulationxl for any object"),
  output_name: z
    .string()
    .optional()
    .default(() => `rigged_${Date.now()}`)
    .describe("Custom output filename (without extension)"),
});

type InputType = z.infer<typeof RequestSchema>;

function generateWorkflow(input: InputType): ComfyPrompt {
  return {
    // Node 1: Load mesh from input folder
    "1": {
      inputs: {
        source_folder: "input",
        file_path: input.mesh_url,
      },
      class_type: "UniRigLoadMesh",
      _meta: {
        title: "Load Mesh",
      },
    },
    // Node 2: Load UniRig models (skeleton + skinning)
    "2": {
      inputs: {
        cache_to_gpu: false,
      },
      class_type: "UniRigLoadModel",
      _meta: {
        title: "Load UniRig Model",
      },
    },
    // Node 3: Auto-rig (extracts skeleton, applies skinning, exports FBX)
    "3": {
      inputs: {
        trimesh: ["1", 0],
        model: ["2", 0],
        skeleton_template: input.skeleton_template,
        fbx_name: input.output_name,
        target_face_count: 50000,
        // Required by comfyui-api to detect output nodes
        filename_prefix: input.output_name,
      },
      class_type: "UniRigAutoRig",
      _meta: {
        title: "Auto Rig",
      },
    },
  };
}

const workflow: Workflow = {
  RequestSchema,
  generateWorkflow,
  summary: "Rig Avatar",
  description: "Takes a mesh URL and returns a rigged FBX with Mixamo skeleton",
};

export default workflow;
