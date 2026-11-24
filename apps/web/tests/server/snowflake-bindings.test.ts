import { describe, expect, it } from "vitest";
import { toBinding } from "@/server/snowflake/client";

describe("Snowflake SQL API bindings", () => {
  it("converts integers to FIXED string bindings", () => {
    expect(toBinding(2024)).toEqual({ type: "FIXED", value: "2024" });
  });

  it("converts non-integer numbers to REAL string bindings", () => {
    expect(toBinding(1.5)).toEqual({ type: "REAL", value: "1.5" });
  });

  it("converts strings to TEXT bindings", () => {
    expect(toBinding("rag")).toEqual({ type: "TEXT", value: "rag" });
  });

  it("converts booleans to BOOLEAN string bindings", () => {
    expect(toBinding(true)).toEqual({ type: "BOOLEAN", value: "true" });
  });

  it("converts null and undefined to null TEXT bindings", () => {
    expect(toBinding(null)).toEqual({ type: "TEXT", value: null });
    expect(toBinding(undefined)).toEqual({ type: "TEXT", value: null });
  });

  it("converts Date objects to TIMESTAMP_NTZ ISO string bindings", () => {
    const value = new Date("2025-01-15T12:34:56.789Z");
    expect(toBinding(value)).toEqual({
      type: "TIMESTAMP_NTZ",
      value: "2025-01-15T12:34:56.789Z",
    });
  });

  it("normalises existing typed bindings to string values", () => {
    expect(toBinding({ type: "FIXED", value: 2025 })).toEqual({
      type: "FIXED",
      value: "2025",
    });
  });
});
