export type SqlScalar = string | number | boolean | null;

export type SnowflakeRow = Record<string, SqlScalar>;

export type Binding = {
  type: "TEXT" | "FIXED" | "BOOLEAN" | "DATE";
  value: SqlScalar;
};

export type SnowflakeQueryResult = {
  rows: SnowflakeRow[];
  queryId: string | null;
  rowCount: number;
  elapsedMs: number;
};
