import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { readFileSync } from "node:fs";
import { parseEnv } from "node:util";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import expected from "@/data/expected-answers.json";

/**
 * Calls the tools through the real HTTP endpoint on a real Next server, so a problem that only exists in
 * the server (env loading, bundling, request context) cannot pass here and fail in production.
 *
 * By default it starts its own `next dev` with a clean environment, so Next loads .env.local itself,
 * exactly as `npm run dev` does. Set MCP_URL to test an already running server instead.
 */
let child: ChildProcess | undefined;
let url = process.env.MCP_URL ?? "";

const freePort = () =>
  new Promise<number>((resolve) => {
    const s = createServer().listen(0, () => {
      const port = (s.address() as { port: number }).port;
      s.close(() => resolve(port));
    });
  });

beforeAll(async () => {
  if (url) return;
  const port = await freePort();
  url = `http://localhost:${port}/mcp`;
  // Do NOT forward the test runner's env: the server must get its config the way it does in `npm run dev`.
  child = spawn("node_modules/.bin/next", ["dev", "-p", String(port)], {
    cwd: process.cwd(),
    env: { PATH: process.env.PATH, HOME: process.env.HOME, NODE_ENV: "development", NEXT_DIST_DIR: ".next-test", NEXT_TELEMETRY_DISABLED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("next dev did not become ready in 60s")), 60_000);
    child!.stdout!.on("data", (d) => String(d).includes("Ready") && (clearTimeout(timer), resolve()));
    child!.on("exit", (c) => reject(new Error(`next dev exited early (${c})`)));
  });
}, 90_000);

afterAll(() => {
  if (child?.pid) process.kill(-child.pid, "SIGTERM");
});

async function callTool(name: string, args: Record<string, string>) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
  });
  const body = await res.text();
  const data = body.split("\n").find((l) => l.startsWith("data:"))?.slice(5) ?? body;
  const msg = JSON.parse(data);
  const text: string = msg.result.content[0].text;
  expect(msg.result.isError, `${name}(${JSON.stringify(args)}) returned an error: ${text}`).not.toBe(true);
  return JSON.parse(text);
}

const teams = Object.keys(expected) as (keyof typeof expected)[];

describe("env parity", () => {
  it("Next parses every .env.local value the same as Node does", async () => {
    const { loadEnvConfig } = await import("@next/env");
    const want = parseEnv(readFileSync(".env.local", "utf8"));
    const saved = { ...process.env };
    for (const k of Object.keys(want)) delete process.env[k];
    (process.env as Record<string, string | undefined>).NODE_ENV = "development"; // Next skips .env.local when NODE_ENV is "test"
    loadEnvConfig(process.cwd(), true);
    const differing = Object.keys(want).filter((k) => process.env[k] !== want[k]);
    for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k];
    Object.assign(process.env, saved);
    // Names only, never values. A quoted value or trailing text on the line is the usual cause.
    expect(differing, "these .env.local entries are parsed differently by Next (quotes or trailing text?)").toEqual([]);
  });
});

describe.each(teams)("HTTP /mcp, Sprint 24 – %s", (team) => {
  const exp = expected[team];

  it("check_definition_of_ready", async () => {
    const r = await callTool("check_definition_of_ready", { team, sprint: "sprint-24" });
    expect(r.notReady).toEqual(exp.notReady);
    expect(r.committedPoints).toBe(exp.committedPoints);
    expect(r.readyPoints).toBe(exp.readyPoints);
    expect(r.avgVelocity).toBe(exp.avgVelocity);
    expect(r.commitPctOfVelocity).toBe(exp.commitPctOfVelocity);
  });

  it("get_sprint_capacity", async () => {
    const r = await callTool("get_sprint_capacity", { team, sprint: "sprint-24" });
    expect(r.rawHours).toBe(exp.rawHours);
    expect(r.focusHours).toBeCloseTo(exp.focusHours, 5);
  });
});
