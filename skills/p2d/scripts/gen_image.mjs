#!/usr/bin/env node
// p2d image runtime: generate (or edit) one image through the ChatGPT/Codex subscription backend.
// Bundled from the codex-image skill so p2d has no external skill dependency.
// Works with Bun or Node 18+. No dependencies.
//
//   bun gen.mjs --prompt-file prompt.txt --out out.png [--size 1024x1536] [--quality high]
//               [--model gpt-6.1-sol] [--effort medium] [--ref a.png --ref b.jpg]
//   bun gen.mjs --prompt "a red fox in snow" --out fox.png
//
// Auth: first ~/.omo/auth.json ("chatgpt-subscription"), then ~/.codex/auth.json
// (Codex CLI ChatGPT login). Override with --auth <path>.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";

const ENDPOINT = "https://chatgpt.com/backend-api/codex/responses";

function parseArgs(argv) {
  const args = { ref: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) throw new Error(`Unexpected argument: ${a}`);
    const key = a.slice(2);
    const val = argv[i + 1];
    if (val === undefined || val.startsWith("--")) throw new Error(`Missing value for ${a}`);
    i++;
    if (key === "ref") args.ref.push(val);
    else args[key] = val;
  }
  return args;
}

function jwtExpMs(token) {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    return typeof payload.exp === "number" ? payload.exp * 1000 : undefined;
  } catch {
    return undefined;
  }
}

function loadAuth(explicitPath) {
  const candidates = explicitPath
    ? [resolve(explicitPath)]
    : [join(homedir(), ".omo", "auth.json"), join(homedir(), ".codex", "auth.json")];
  const tried = [];
  for (const p of candidates) {
    if (!existsSync(p)) { tried.push(`${p} (missing)`); continue; }
    const j = JSON.parse(readFileSync(p, "utf8"));
    let access, accountId, expires;
    if (j["chatgpt-subscription"]?.access) {
      const c = j["chatgpt-subscription"];
      access = c.access; accountId = c.accountId; expires = c.expires;
    } else if (j.tokens?.access_token) {
      access = j.tokens.access_token; accountId = j.tokens.account_id;
    } else { tried.push(`${p} (no ChatGPT login)`); continue; }
    expires ??= jwtExpMs(access);
    if (expires !== undefined && expires < Date.now()) {
      throw new Error(`ChatGPT token in ${p} expired at ${new Date(expires).toISOString()}. ` +
        `Re-login (omo: /login; Codex CLI: run any codex command or 'codex login') and retry.`);
    }
    return { access, accountId, source: p };
  }
  throw new Error(`No ChatGPT subscription login found. Tried: ${tried.join("; ")}`);
}

function mimeOf(path) {
  const e = extname(path).toLowerCase();
  if (e === ".png") return "image/png";
  if (e === ".jpg" || e === ".jpeg") return "image/jpeg";
  if (e === ".webp") return "image/webp";
  throw new Error(`Unsupported reference image type: ${path}`);
}

function pngSize(buf) {
  if (buf.length > 24 && buf.readUInt32BE(0) === 0x89504e47) return `${buf.readUInt32BE(16)}x${buf.readUInt32BE(20)}`;
  return "unknown";
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const prompt = args["prompt-file"] ? readFileSync(args["prompt-file"], "utf8") : args.prompt;
  if (!prompt?.trim()) throw new Error("Provide --prompt-file <path> or --prompt <text>");
  if (!args.out) throw new Error("Provide --out <path.png>");
  const format = (extname(args.out).slice(1).toLowerCase() || "png").replace("jpg", "jpeg");
  if (!["png", "jpeg", "webp"].includes(format)) throw new Error("--out must end in .png, .jpg/.jpeg or .webp");

  const auth = loadAuth(args.auth);
  const model = args.model ?? process.env.CODEX_IMAGE_MODEL ?? "gpt-6.1-sol";
  const tool = { type: "image_generation", size: args.size ?? "auto", quality: args.quality ?? "high", output_format: format };
  if (args.mask) {
    if (!args.ref.length) throw new Error("--mask needs the image to edit as the first --ref");
    tool.input_image_mask = { image_url: `data:${mimeOf(args.mask)};base64,${readFileSync(args.mask).toString("base64")}` };
  }

  const content = [];
  for (const r of args.ref) {
    const data = readFileSync(r).toString("base64");
    content.push({ type: "input_image", image_url: `data:${mimeOf(r)};base64,${data}` });
  }
  const lead = args.ref.length
    ? `Edit/compose using the ${args.ref.length} attached image(s) as references (in order: image 1..${args.ref.length}). `
    : "";
  content.push({ type: "input_text", text: `${lead}Generate exactly one image. Use the following as the image prompt verbatim:\n\n${prompt}` });

  const body = {
    model,
    instructions: "You generate images. Call the image_generation tool exactly once with the user's prompt passed through verbatim. Never generate more than one image. Reply with one short sentence afterwards.",
    input: [{ role: "user", content }],
    tools: [tool],
    tool_choice: "auto",
    reasoning: { effort: args.effort ?? "medium" },
    store: false,
    stream: true,
  };

  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${auth.access}`,
      "chatgpt-account-id": auth.accountId ?? "",
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "OpenAI-Beta": "responses=experimental",
      originator: "codex_cli_rs",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 2000)}`);

  const raw = await res.text();
  let image, revised, text = "";
  const errors = [];
  for (const line of raw.split("\n")) {
    if (!line.startsWith("data: ")) continue;
    let ev;
    try { ev = JSON.parse(line.slice(6)); } catch { continue; }
    if (ev.type === "error" || ev.type === "response.failed") errors.push(JSON.stringify(ev.error ?? ev.response?.error ?? ev).slice(0, 1000));
    if (ev.type === "response.output_text.done") text = ev.text ?? text;
    if (ev.type === "response.output_item.done" && ev.item?.type === "image_generation_call" && ev.item.result) {
      image = ev.item.result;
      revised = ev.item.revised_prompt;
    }
  }
  if (!image) throw new Error(`No image returned.${errors.length ? " Errors: " + errors.join(" | ") : ""}${text ? " Model said: " + text : ""}`);

  const outPath = resolve(args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  const buf = Buffer.from(image, "base64");
  writeFileSync(outPath, buf);
  console.log(JSON.stringify({ path: outPath, size: format === "png" ? pngSize(buf) : "n/a", bytes: buf.length, model, auth: auth.source, revised_prompt: revised }, null, 2));
}

main().catch((e) => {
  console.error(`gen_image: ${e.message}`);
  process.exit(1);
});
