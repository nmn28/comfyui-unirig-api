/**
 * Fit Clothing Endpoint
 * POST /workflow/fit-clothing
 *
 * Takes a rigged avatar and a clothing mesh, fits the clothing to the avatar's body,
 * transfers skin weights, and returns a rigged clothing GLB.
 *
 * Uses:
 * - cloth-fit (SIGGRAPH 2025) for intersection-free garment retargeting
 * - Robust Weight Transfer (SIGGRAPH Asia 2023) for skin weight transfer
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
  avatar_url: z.string().describe("URL to rigged avatar GLB (from rig-avatar workflow)"),
  clothing_url: z.string().describe("URL to clothing mesh OBJ from S3 library"),
  reference_skeleton_url: z
    .string()
    .describe("URL to reference skeleton OBJ that the clothing was fitted to"),
  output_name: z
    .string()
    .optional()
    .default(() => `fitted_clothing_${Date.now()}`)
    .describe("Custom output filename (without extension)"),
  combine_with_avatar: z
    .boolean()
    .optional()
    .default(false)
    .describe("If true, returns combined avatar+clothing GLB. If false, returns clothing-only GLB."),
});

type InputType = z.infer<typeof RequestSchema>;

function generateWorkflow(input: InputType): ComfyPrompt {
  const nodes: ComfyPrompt = {
    // Node 1: Load rigged avatar mesh
    "1": {
      inputs: {
        source_folder: "input",
        file_path: input.avatar_url,
      },
      class_type: "UniRigLoadMesh",
      _meta: {
        title: "Load Avatar Mesh",
      },
    },
    // Node 2: Load MIA model to extract skeleton from avatar
    "2": {
      inputs: {
        cache_to_gpu: true,
      },
      class_type: "MIALoadModel",
      _meta: {
        title: "Load MIA Model",
      },
    },
    // Node 3: Re-rig avatar to get skeleton dict (if not already available)
    // In practice, we'd pass the skeleton from the original rig, but this ensures we have it
    "3": {
      inputs: {
        trimesh: ["1", 0],
        model: ["2", 0],
        fbx_name: `${input.output_name}_avatar`,
        no_fingers: false,
        use_normal: false,
        reset_to_rest: true,
        separate_textures: false,
      },
      class_type: "MIAAutoRig",
      _meta: {
        title: "Extract Avatar Skeleton",
      },
    },
    // Node 4: Load clothing mesh from S3 library
    "4": {
      inputs: {
        clothing_url: input.clothing_url,
      },
      class_type: "LoadClothingMesh",
      _meta: {
        title: "Load Clothing Mesh",
      },
    },
    // Node 5: Load reference skeleton (the body the clothing was originally fitted to)
    "5": {
      inputs: {
        source_folder: "input",
        file_path: input.reference_skeleton_url,
      },
      class_type: "UniRigLoadMesh",
      _meta: {
        title: "Load Reference Skeleton",
      },
    },
    // Node 6: Cloth-fit (deform clothing to fit target avatar)
    "6": {
      inputs: {
        source_garment: ["4", 0],
        source_skeleton: ["5", 0], // Reference skeleton
        target_mesh: ["1", 0],
        target_skeleton: ["3", 1], // Skeleton from MIAAutoRig output
        output_name: `${input.output_name}_fitted`,
      },
      class_type: "ClothFitGarment",
      _meta: {
        title: "Cloth-Fit Garment",
      },
    },
    // Node 7: Transfer skin weights from avatar to fitted garment
    "7": {
      inputs: {
        rigged_avatar_path: ["3", 0], // FBX path from MIAAutoRig
        fitted_garment: ["6", 0],
        output_name: input.output_name,
      },
      class_type: "TransferSkinWeights",
      _meta: {
        title: "Transfer Skin Weights",
      },
    },
  };

  // Optionally combine avatar + clothing
  if (input.combine_with_avatar) {
    nodes["8"] = {
      inputs: {
        avatar_path: ["3", 0], // Avatar GLB path
        clothing_path: ["7", 0], // Rigged clothing path
        output_name: `${input.output_name}_combined`,
      },
      class_type: "CombineAvatarClothing",
      _meta: {
        title: "Combine Avatar + Clothing",
      },
    };
  }

  return nodes;
}

const workflow: Workflow = {
  RequestSchema,
  generateWorkflow,
  summary: "Fit Clothing",
  description:
    "Fits clothing to a rigged avatar using cloth-fit for geometry and Robust Weight Transfer for skinning. Returns a rigged clothing GLB that animates with the avatar.",
};

export default workflow;
