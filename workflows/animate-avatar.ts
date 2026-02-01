/**
 * Animate Avatar Endpoint
 * POST /workflow/animate-avatar
 *
 * Takes a rigged FBX and an animation file, returns animated FBX.
 * This is the fast operation (~2-5 seconds) - call for each animation change.
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
  rigged_fbx_url: z
    .string()
    .describe("URL to rigged FBX file (from /workflow/rig-avatar)"),
  animation_url: z
    .string()
    .describe("URL to animation FBX file (Mixamo format)"),
  output_name: z
    .string()
    .optional()
    .default(() => `animated_${Date.now()}`)
    .describe("Custom output filename (without extension)"),
});

type InputType = z.infer<typeof RequestSchema>;

function generateWorkflow(input: InputType): ComfyPrompt {
  return {
    "1": {
      inputs: {
        source_folder: "output",
        file_name: input.rigged_fbx_url,
        load_all_animations: false,
      },
      class_type: "UniRigLoadRiggedMesh",
      _meta: {
        title: "Load Rigged Mesh",
      },
    },
    "2": {
      inputs: {
        model_fbx_path: ["1", 0],
        animation_type: "mixamo",
        animation_file: input.animation_url,
        output_name: input.output_name,
      },
      class_type: "UniRigApplyAnimation",
      _meta: {
        title: "Apply Animation",
      },
    },
  };
}

const workflow: Workflow = {
  RequestSchema,
  generateWorkflow,
  summary: "Animate Avatar",
  description: "Takes a rigged FBX and animation file, returns animated FBX",
};

export default workflow;
