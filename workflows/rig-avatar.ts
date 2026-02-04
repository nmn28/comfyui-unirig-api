/**
 * Rig Avatar Endpoint
 * POST /workflow/rig-avatar
 *
 * Takes a mesh URL (GLB from Meshy/Tripo) and returns a rigged FBX.
 * Uses MIA (Make-It-Animatable) for fast humanoid rigging (<1 second).
 * Output is Mixamo-compatible skeleton ready for Mixamo animations.
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
  output_name: z
    .string()
    .optional()
    .default(() => `rigged_mia_${Date.now()}`)
    .describe("Custom output filename (without extension)"),
  no_fingers: z
    .boolean()
    .optional()
    .default(false)
    .describe("Merge finger weights to hand bone (true) or keep separate finger bones (false)"),
  use_normal: z
    .boolean()
    .optional()
    .default(false)
    .describe("Use surface normals for better weights on overlapping limbs (slower)"),
  reset_to_rest: z
    .boolean()
    .optional()
    .default(true)
    .describe("Transform to T-pose rest position (required for Mixamo animations)"),
  separate_textures: z
    .boolean()
    .optional()
    .default(true)
    .describe("Export geometry-only GLB (2-3MB) and return textures separately for S3 upload. Recommended for production."),
});

type InputType = z.infer<typeof RequestSchema>;

function generateWorkflow(input: InputType): ComfyPrompt {
  return {
    // Node 1: Load mesh from URL (comfyui-api preprocessor downloads it)
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
    // Node 2: Load MIA models (fast humanoid rigging)
    "2": {
      inputs: {
        cache_to_gpu: true,
      },
      class_type: "MIALoadModel",
      _meta: {
        title: "Load MIA Model",
      },
    },
    // Node 3: MIA Auto-rig (outputs Mixamo-compatible FBX + GLB + textures)
    "3": {
      inputs: {
        trimesh: ["1", 0],
        model: ["2", 0],
        fbx_name: input.output_name,
        no_fingers: input.no_fingers,
        use_normal: input.use_normal,
        reset_to_rest: input.reset_to_rest,
        separate_textures: input.separate_textures,
        // Required by comfyui-api to detect output nodes
        filename_prefix: input.output_name,
      },
      class_type: "MIAAutoRig",
      _meta: {
        title: "MIA Auto Rig",
      },
    },
  };
}

const workflow: Workflow = {
  RequestSchema,
  generateWorkflow,
  summary: "Rig Avatar (MIA)",
  description:
    "Fast humanoid rigging using MIA. Takes a mesh URL, returns Mixamo-compatible FBX ready for animations.",
};

export default workflow;
