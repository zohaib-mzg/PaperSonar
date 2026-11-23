import { z } from "zod";

export const chatRequestSchema = z
  .object({
    message: z.string().trim().min(1).max(500),
    session_id: z.string().uuid().optional(),
    client_request_id: z.string().max(80).optional(),
  })
  .strict();

export type ChatRequest = z.infer<typeof chatRequestSchema>;

export const feedbackRequestSchema = z
  .object({
    request_id: z.string().max(120),
    rating: z.enum(["helpful", "not_helpful"]),
    reason: z.enum(["wrong_number", "wrong_topic", "not_relevant", "missing_data", "other"]),
    comment: z.string().trim().max(500).optional(),
  })
  .strict();

export type FeedbackRequest = z.infer<typeof feedbackRequestSchema>;
