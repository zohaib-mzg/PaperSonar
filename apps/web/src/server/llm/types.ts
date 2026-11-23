import { z } from "zod";

export const plannerFilterSchema = z.object({
  category_key: z.string().optional(),
  category_key_b: z.string().optional(),
  parent_category_key: z.string().optional(),
  year_from: z.number().int().optional(),
  year_to: z.number().int().optional(),
  source_name: z.string().optional(),
  output_type: z.string().optional(),
  venue_name: z.string().optional(),
  institution_key: z.string().optional(),
  country_code: z.string().optional(),
  author_key: z.string().optional(),
  orcid: z.string().optional(),
  access_status: z.string().optional(),
  snapshot_date: z.string().optional(),
  search_term: z.string().optional(),
  limit: z.number().int().optional(),
  order: z.string().optional(),
});

export const plannerOutputSchema = z.object({
  intent: z.enum(["metric", "compare", "search", "clarify", "refuse"]),
  metric_ids: z.array(z.string()).min(1),
  filters: plannerFilterSchema.default({}),
  comparison: z
    .object({
      metric_id: z.string(),
      dimension: z.enum(["category", "source", "year", "institution", "venue", "type"]),
      sides: z
        .array(
          z.object({
            label: z.string(),
            filters: plannerFilterSchema,
          }),
        )
        .length(2),
    })
    .optional(),
  interpretation: z.string().max(160),
  confidence: z.number().min(0).max(1),
  clarification: z.string().max(300).optional(),
  refusal_reason: z.string().max(300).optional(),
});

export type PlannerOutput = z.infer<typeof plannerOutputSchema>;
export type PlannerFilters = z.infer<typeof plannerFilterSchema>;

export type PlannerInput = {
  message: string;
  recent: Array<{
    metric_id: string;
    filters: Record<string, unknown>;
    interpretation: string;
  }>;
  metrics: Array<{
    id: string;
    label: string;
    description: string;
    dimensions: string[];
  }>;
  categories: Array<{
    key: string;
    label: string;
    parent_key: string | null;
    aliases: string[];
  }>;
};

export type ComposeInput = {
  metricLabel: string;
  intent: string;
  facts: Record<string, unknown>;
  caveats: string[];
};

export interface LlmProvider {
  readonly name: "groq" | "gemini";
  plan(input: PlannerInput): Promise<unknown>;
  compose(input: ComposeInput): Promise<string>;
}
