import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign,
  type KeyObject,
} from "node:crypto";
import { env } from "@/server/env";

let cachedToken: { token: string; expiresAt: number } | null = null;

function normalisePrivateKey(raw: string): string {
  let value = raw.trim().replace(/\\n/g, "\n");
  if (!value.includes("BEGIN PRIVATE KEY") && !value.includes("BEGIN RSA PRIVATE KEY")) {
    try {
      value = Buffer.from(value, "base64").toString("utf8");
    } catch {
      // Keep the original value; key parsing will fail with a safe error.
    }
  }
  return value;
}

function loadPrivateKey(): KeyObject {
  const raw = env.SNOWFLAKE_PUBLIC_PRIVATE_KEY;
  if (!raw) throw new Error("SNOWFLAKE_PUBLIC_PRIVATE_KEY is missing");
  return createPrivateKey({
    key: normalisePrivateKey(raw),
    format: "pem",
    passphrase: env.SNOWFLAKE_PUBLIC_PRIVATE_KEY_PASSPHRASE,
  });
}

function publicKeyFingerprint(privateKey: KeyObject): string {
  const der = createPublicKey(privateKey).export({ format: "der", type: "spki" });
  return createHash("sha256").update(der).digest("base64");
}

function base64Url(input: Buffer | string): string {
  return Buffer.from(input)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export function getSnowflakeJwt(): string {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && cachedToken.expiresAt > now + 10) return cachedToken.token;

  const account = env.SNOWFLAKE_ACCOUNT;
  const user = env.SNOWFLAKE_PUBLIC_USER;
  if (!account || !user) throw new Error("Snowflake account/user is missing");

  const privateKey = loadPrivateKey();
  const fingerprint = publicKeyFingerprint(privateKey);
  const header = base64Url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = base64Url(
    JSON.stringify({
      iss: `${account}.${user}.SHA256:${fingerprint}`,
      sub: `${account}.${user}`,
      iat: now,
      exp: now + 60,
    }),
  );
  const signature = sign("RSA-SHA256", Buffer.from(`${header}.${payload}`), privateKey);
  const token = `${header}.${payload}.${base64Url(signature)}`;
  cachedToken = { token, expiresAt: now + 60 };
  return token;
}

export function clearSnowflakeJwtCache(): void {
  cachedToken = null;
}
