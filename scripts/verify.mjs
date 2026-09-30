import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(process.argv[2] ?? ".");
const wantGlobal = process.argv.includes("--global");
const senpi = process.env.SENPI_ROOT ?? join(homedir(), ".bun/install/global/node_modules/@code-yeongyu/senpi");
const { DefaultResourceLoader } = await import(`${senpi}/dist/core/resource-loader.js`);
const { SettingsManager } = await import(`${senpi}/dist/core/settings-manager.js`);

const skillDir = join(root, "skills/p2d");
const skillPath = join(skillDir, "SKILL.md");
const cli = join(skillDir, "scripts/p2d.py");

function check(name, assertion) {
  assertion();
  console.log(`PASS ${name}`);
}

async function loadSkills(options) {
  const loader = new DefaultResourceLoader({
    settingsManager: SettingsManager.inMemory(),
    noContextFiles: true,
    ...options,
  });
  await loader.reload();
  return loader.getSkills();
}

function runCli(args) {
  return execFileSync("python3", [cli, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

const fromPackage = await loadSkills({ cwd: root, agentDir: join(root, ".absent-agent"), additionalExtensionPaths: [root] });
check("package manifest: senpi loader discovers p2d with no diagnostics", () => {
  const ours = fromPackage.diagnostics.filter((d) => String(d.path ?? "").startsWith(root));
  assert.deepEqual(ours, []);
  const skill = fromPackage.skills.find((s) => s.name === "p2d");
  assert.ok(skill, "skill p2d not found");
  assert.equal(realpathSync(skill.filePath), realpathSync(skillPath));
});

if (wantGlobal) {
  const globalSkills = await loadSkills({ cwd: "/tmp", agentDir: join(homedir(), ".omo/agent") });
  check("global install: ~/.agents/skills/p2d is discovered from an unrelated cwd", () => {
    const skill = globalSkills.skills.find((s) => s.name === "p2d");
    assert.ok(skill, "skill p2d not found globally");
    assert.equal(realpathSync(skill.filePath), realpathSync(skillPath));
    const ours = globalSkills.diagnostics.filter((d) => String(d.path ?? "").includes("/p2d/"));
    assert.deepEqual(ours, []);
  });
}

const skillText = readFileSync(skillPath, "utf8");
const front = skillText.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
check("frontmatter: valid name and description within 1024 chars", () => {
  assert.ok(front, "SKILL.md needs YAML frontmatter");
  const name = front[1].match(/^name:\s*(.+)$/m)?.[1].trim();
  const description = front[1].match(/^description:\s*(.+)$/m)?.[1].trim() ?? "";
  assert.equal(name, "p2d");
  assert.ok(description.length > 0 && description.length <= 1024, `description length ${description.length}`);
});

check("SKILL.md stays within 150 lines", () => {
  assert.ok(skillText.split("\n").length <= 150, `${skillText.split("\n").length} lines`);
});

const refDir = join(skillDir, "references");
const refs = readdirSync(refDir).filter((f) => f.endsWith(".md")).sort();
check("every reference is linked from SKILL.md", () => {
  for (const ref of refs) assert.ok(skillText.includes(`](references/${ref})`), `${ref} is not linked`);
  for (const link of skillText.matchAll(/\]\((references\/[^)]+)\)/g)) assert.ok(existsSync(join(skillDir, link[1])), `${link[1]} missing`);
});

check("no reference points to another reference", () => {
  for (const ref of refs) {
    const text = readFileSync(join(refDir, ref), "utf8");
    for (const other of refs) {
      if (other !== ref) assert.ok(!new RegExp(`\\b${other.replace(".", "\\.")}\\b`).test(text), `${ref} mentions ${other}`);
    }
    assert.ok(!text.includes("references/"), `${ref} links into references/`);
  }
});

const topHelp = runCli(["--help"]);
const commands = [...topHelp.matchAll(/^  ([a-z-]+)  /gm)].map((m) => m[1]);
const packActions = ["init", "show", "set", "palette", "attempt", "accept"];
check("every command named in the docs exists and its --help runs", () => {
  const docs = [skillText, ...refs.map((r) => readFileSync(join(refDir, r), "utf8"))].join("\n");
  const named = new Set();
  for (const m of docs.matchAll(/p2d\.py ([a-z][a-z-]*)(?: ([a-z]+))?/g)) {
    assert.ok(commands.includes(m[1]), `docs name unknown command ${m[1]}`);
    named.add(m[1] === "pack" && packActions.includes(m[2]) ? `pack ${m[2]}` : m[1]);
  }
  for (const m of docs.matchAll(/`((?:pack (?:init|show|set|palette|attempt|accept))|[a-z][a-z-]*)[ `]/g)) {
    if (commands.includes(m[1].split(" ")[0])) named.add(m[1]);
  }
  for (const name of [...commands, ...packActions.map((a) => `pack ${a}`)]) named.add(name);
  for (const name of named) runCli([...name.split(" "), "--help"]);
  console.log(`  checked --help for: ${[...named].sort().join(", ")}`);
});
