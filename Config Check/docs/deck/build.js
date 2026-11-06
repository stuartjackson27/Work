const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("/root/.claude/skills/synced/0b75e8e6-7955-4e43-a277-4081bee46ff8_5069b1f0-84c0-4f00-916b-e00f10ad17e6/pptx/scripts/apply_theme.js");

const THEME = {
  name: "Config Check",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14202A", lt1: "FFFFFF", dk2: "0E2B33", lt2: "EEF2F3",
    accent1: "0F6E74", accent2: "D9731A", accent3: "C22F2F",
    accent4: "3A78B8", accent5: "2F8A57", accent6: "B69212",
    hlink: "0F6E74", folHlink: "5D6B76",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color = "FFFFFF", size = 256) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.title = "Config Check";
  pres.author = "Stuart Jackson";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.3, w: 11.5, h: 1.4, fontFace: THEME.headFontFace, fontSize: 48, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.85, w: 11.0, h: 1.6, fontSize: 20, color: "9FC7CA", valign: "top", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.8, fontFace: THEME.headFontFace, fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { text: { text: "Config Check · PoC", options: { x: 0.6, y: 7.0, w: 4, h: 0.3, fontSize: 10, color: "5D6B76", margin: 0 } } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: "5D6B76", align: "right" },
  });
  pres.defineSlideMaster({
    title: "CLOSE_DARK",
    background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.8, fontFace: THEME.headFontFace, fontSize: 32, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 12.3, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: "9FC7CA", align: "right" },
  });

  const I = {
    server: await icon(fa.FaServer), desk: await icon(fa.FaDesktop), net: await icon(fa.FaNetworkWired),
    brain: await icon(fa.FaBrain), shield: await icon(fa.FaShieldAlt), hist: await icon(fa.FaHistory),
    file: await icon(fa.FaFileAlt), search: await icon(fa.FaSearch), list: await icon(fa.FaListUl),
    code: await icon(fa.FaCode), lock: await icon(fa.FaLock), user: await icon(fa.FaUserShield),
    chart: await icon(fa.FaChartBar), road: await icon(fa.FaRoad), flask: await icon(fa.FaFlask),
    globe: await icon(fa.FaGlobe), db: await icon(fa.FaDatabase), cubes: await icon(fa.FaCubes),
  };

  // circle + icon motif
  function badge(slide, img, x, y, d = 0.6, fill = C.accent1, name = "badge") {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: name + " circle" });
    const p = d * 0.25;
    slide.addImage({ data: img, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, objectName: name + " icon", altText: name });
  }
  function card(slide, x, y, w, h, name, fill = C.background2) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, objectName: name });
  }
  function txt(slide, text, o) {
    slide.addText(text, { isTextBox: true, margin: 0, valign: "top", color: C.text1, fontSize: 14, ...o });
  }

  // ---------------------------------------------------------------- 1 title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
  s.addText("Config Check", { placeholder: "title" });
  s.addText("LLM-assisted configuration anomaly detection for Junos networks\nProof of concept · Proxmox + EVE-NG lab · November 2026", { placeholder: "body" });
  badge(s, I.net, 0.8, 1.25, 0.8, C.accent1, "network");
  s.addNotes("Config Check is a proof of concept: it reads device configs through Juniper's MCP server, checks them against our design docs and templates, tracks changes over time and shows rated anomalies on a dashboard. Everything runs on my lab kit with a local LLM.");

  // ---------------------------------------------------------------- 2 what it does
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  s.addText("What the tool does", { placeholder: "title" });
  txt(s, "Reads every device's running config, compares it with how the network is meant to be built, and rates every deviation 1–5 on one dashboard.", { x: 0.6, y: 1.3, w: 11.6, h: 0.7, fontSize: 18, color: "3A4A55" });
  const what = [
    [I.search, "Detect", "Exact template rules per role: base, infrastructure and service config. Plus drift between devices in the same role."],
    [I.brain, "Explain", "A local LLM reads the design docs and reviews each config section and every change, with strict grounding checks."],
    [I.hist, "Track", "Every scan is a config snapshot. Diffs, Junos commit history, regressions and pinned baselines."],
    [I.chart, "Prioritise", "Severity, compliance score, accepted exceptions and a suggested Junos fix for each finding."],
  ];
  what.forEach(([img, h, b], i) => {
    const x = 0.6 + i * 3.08;
    card(s, x, 2.35, 2.85, 3.4, "card " + h);
    badge(s, img, x + 0.3, 2.65, 0.75, C.accent1, h);
    txt(s, h, { x: x + 0.3, y: 3.6, w: 2.3, h: 0.5, fontSize: 22, bold: true, fontFace: THEME.headFontFace });
    txt(s, b, { x: x + 0.3, y: 4.2, w: 2.3, h: 1.9, fontSize: 14, color: "3A4A55" });
  });
  s.addNotes("Four jobs. Detection is deterministic code. The LLM explains and reviews. History turns scans into backups. The dashboard prioritises.");

  // ---------------------------------------------------------------- 3 architecture
  pres.addSection({ title: "Architecture" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Architecture" });
  s.addText("Architecture", { placeholder: "title" });
  const zone = (x, y, w, h, label, name) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: C.background2 }, line: { color: "C9D3D8", width: 1 }, objectName: name });
    txt(s, label, { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: 0.35, fontSize: 12, bold: true, color: "5D6B76" });
  };
  const box = (x, y, w, h, head, sub, fill, name, headColor = C.background1, subColor = "D8ECEE") => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { type: "none" }, objectName: name });
    s.addText([
      { text: head, options: { bold: true, fontSize: 13, color: headColor, breakLine: true } },
      { text: sub, options: { fontSize: 11, color: subColor } },
    ], { isTextBox: true, x: x + 0.12, y: y + 0.06, w: w - 0.24, h: h - 0.12, valign: "middle", margin: 0 });
  };
  // browser
  box(0.5, 2.3, 1.75, 1.1, "Browser", "dashboard\n192.168.1.39:8080", "5D6B76", "browser", C.background1, "E6EBEE");
  // proxmox
  zone(2.55, 1.35, 7.35, 5.45, "Proxmox host · 192.168.1.14 (Minisforum MS-01)", "proxmox zone");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 2.75, y: 1.85, w: 3.65, h: 4.75, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: HEX.accent1, width: 1.25 }, objectName: "config-check vm" });
  txt(s, "VM 111 config-check · 192.168.1.39\nUbuntu 26.04 · Docker Compose", { x: 2.9, y: 1.95, w: 3.4, h: 0.55, fontSize: 11, bold: true, color: C.accent1 });
  box(2.95, 2.6, 3.25, 1.35, "cc-backend  ·  FastAPI :8080", "Collector · rule engine · drift · history\nLLM orchestration · SQLite · dashboard", C.accent1, "backend");
  box(2.95, 4.25, 3.25, 1.05, "cc-junos-mcp  ·  :30030", "Juniper junos-mcp-server\nlocalhost only · token · read-only policy", "0E2B33", "mcp");
  box(2.95, 5.5, 3.25, 0.9, "knowledge/  ·  data/", "design docs · templates · snapshots", "DDE7EA", "storage", C.text1, "3A4A55");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.75, y: 3.1, w: 2.95, h: 3.5, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: "8E9BA5", width: 1.25 }, objectName: "eve vm" });
  txt(s, "VM 108 EVE-NG3 · 192.168.1.38", { x: 6.9, y: 3.2, w: 2.7, h: 0.3, fontSize: 11, bold: true, color: "5D6B76" });
  box(6.95, 3.65, 2.55, 0.85, "qfx1  ·  192.168.1.52", "vJunos-switch 25.4R1", "3A78B8", "qfx1");
  box(6.95, 4.75, 2.55, 0.85, "qfx2  ·  192.168.1.53", "vJunos-switch 25.4R1", "3A78B8", "qfx2");
  txt(s, "Reached over NETCONF :830\nLab EVPN_VXLAN_QFX · role qinq-edge", { x: 6.95, y: 5.85, w: 2.6, h: 0.5, fontSize: 11, color: "5D6B76" });
  // windows
  zone(10.2, 1.35, 2.65, 5.45, "Windows PC · 192.168.1.232", "windows zone");
  box(10.4, 1.9, 2.25, 1.0, "Ollama  ·  :11434", "RTX 3060 · 12 GB", C.accent2, "ollama");
  box(10.4, 3.15, 2.25, 0.85, "qwen3.5:9b", "review + change review", "8A4A12", "model review");
  box(10.4, 4.25, 2.25, 0.85, "nomic-embed-text", "doc retrieval (RAG)", "8A4A12", "model embed");
  txt(s, "Local models only. Cloud models are blocked by an allow-list.", { x: 10.4, y: 5.35, w: 2.25, h: 1.2, fontSize: 11, color: "5D6B76" });
  // connectors
  const arrow = (x1, y1, x2, y2, name) => s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001, flipV: (y2 < y1) !== (x2 < x1), line: { color: "14202A", width: 1.5, endArrowType: "triangle" }, objectName: name });
  arrow(2.25, 2.85, 2.95, 3.1, "browser to backend");
  s.addShape(pres.shapes.LINE, { x: 4.575, y: 3.95, w: 0.001, h: 0.3, line: { color: "14202A", width: 1.5, endArrowType: "triangle" }, objectName: "backend to mcp" });
  txt(s, "MCP + token", { x: 4.7, y: 3.97, w: 1.4, h: 0.25, fontSize: 10, color: "5D6B76" });
  arrow(6.2, 4.6, 6.95, 4.1, "mcp to qfx1");
  arrow(6.2, 4.9, 6.95, 5.15, "mcp to qfx2");
  
  s.addShape(pres.shapes.LINE, { x: 6.2, y: 2.4, w: 4.2, h: 0.001, line: { color: "14202A", width: 1.5, endArrowType: "triangle", beginArrowType: "none" }, objectName: "backend to ollama" });
  s.addShape(pres.shapes.LINE, { x: 6.2, y: 2.4, w: 0.001, h: 0.2, line: { color: "14202A", width: 1.5 }, objectName: "backend riser" });
  txt(s, "HTTP :11434 · embed + JSON-schema chat", { x: 6.75, y: 2.05, w: 3.3, h: 0.3, fontSize: 10, color: "5D6B76" });
  s.addNotes("Three machines. The config-check VM runs two containers: the backend and Juniper's MCP server, bound to localhost. The backend only talks to devices through MCP over NETCONF. The LLM runs on my Windows PC's RTX 3060 through Ollama; the VM calls it over the LAN.");

  // ---------------------------------------------------------------- 4 component table
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Architecture" });
  s.addText("Components", { placeholder: "title" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.accent1 }, fontSize: 13 } });
  const rows = [
    [hdr("Component"), hdr("Runs on"), hdr("Address"), hdr("Job")],
    ["Dashboard + API", "cc-backend container", "192.168.1.39:8080", "UI, scan control, findings, changes, decisions"],
    ["Scan engine", "cc-backend container", "n/a", "Collect, rules, drift, diff, LLM calls, scoring"],
    ["Junos MCP server", "cc-junos-mcp container", "127.0.0.1:30030", "Device access over NETCONF, block-listed to read-only"],
    ["Store", "SQLite + files on the VM", "/opt/config-check/data", "Scans, findings, changes, commits, baselines, snapshots"],
    ["Knowledge", "Files on the VM", "/opt/config-check/knowledge", "HLD, base / infra / service templates"],
    ["LLM runtime", "Ollama on Windows PC", "192.168.1.232:11434", "qwen3.5:9b (review), nomic-embed-text (retrieval)"],
    ["Lab devices", "EVE-NG VM 108", "192.168.1.52 / .53", "2 × vJunos-switch 25.4R1, role qinq-edge"],
    ["Hypervisor", "Proxmox VE 9", "192.168.1.14", "Hosts the config-check and EVE-NG VMs"],
  ].map((r, i) => i === 0 ? r : r.map((c, j) => ({ text: c, options: { fontSize: 12, bold: j === 0, color: C.text1, fill: { color: i % 2 ? C.background1 : C.background2 } } })));
  s.addTable(rows, { x: 0.6, y: 1.4, w: 12.1, colW: [2.3, 2.6, 2.7, 4.5], rowH: 0.52, border: { type: "solid", pt: 0.5, color: "D9DFE3" }, margin: [0.05, 0.1, 0.05, 0.1], valign: "middle", objectName: "components table" });
  s.addNotes("Reference table of every component, where it runs and what it does.");

  // ---------------------------------------------------------------- 5 pipeline
  pres.addSection({ title: "How it works" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "How it works" });
  s.addText("What happens in a scan", { placeholder: "title" });
  const steps = [
    ["Collect", "Config, facts and commit history for each device, via MCP", "Code"],
    ["Rules", "Each role's templates checked line by line, scoped per VR and interface", "Code"],
    ["Drift", "Lines on one device in a role that its peers don't have", "Code"],
    ["History", "Diff against the last snapshot or a pinned baseline, plus risk hints", "Code"],
    ["LLM review", "Changes, then each config section, checked against the retrieved design text", "LLM"],
    ["Guards", "Drop anything ungrounded, duplicated, no-op or self-contradicting", "Code"],
    ["Store + show", "Findings, states (new / recurring / regressed / accepted), score", "Code"],
  ];
  const sw = 12.1 / steps.length;
  s.addShape(pres.shapes.LINE, { x: 0.6 + sw / 2, y: 2.05, w: sw * (steps.length - 1), h: 0.001, line: { color: "C9D3D8", width: 2 }, objectName: "pipeline line" });
  steps.forEach(([h, b, who], i) => {
    const cx = 0.6 + i * sw + sw / 2;
    const llm = who === "LLM";
    s.addShape(pres.shapes.OVAL, { x: cx - 0.4, y: 1.65, w: 0.8, h: 0.8, fill: { color: llm ? C.accent2 : C.accent1 }, line: { color: C.background1, width: 3 }, objectName: "step " + (i + 1) });
    s.addText(String(i + 1), { isTextBox: true, x: cx - 0.4, y: 1.65, w: 0.8, h: 0.8, align: "center", valign: "middle", fontSize: 22, bold: true, color: C.background1, margin: 0 });
    txt(s, h, { x: cx - sw / 2 + 0.08, y: 2.7, w: sw - 0.16, h: 0.45, fontSize: 16, bold: true, align: "center", fontFace: THEME.headFontFace });
    txt(s, b, { x: cx - sw / 2 + 0.08, y: 3.2, w: sw - 0.16, h: 1.8, fontSize: 12, align: "center", color: "3A4A55" });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx - 0.45, y: 5.05, w: 0.9, h: 0.32, rectRadius: 0.15, fill: { color: llm ? "FCECDC" : "DCEFEF" }, line: { type: "none" }, objectName: "who " + (i + 1) });
    s.addText(who, { isTextBox: true, x: cx - 0.45, y: 5.05, w: 0.9, h: 0.32, align: "center", valign: "middle", fontSize: 11, bold: true, color: llm ? "8A4A12" : C.accent1, margin: 0 });
  });
  card(s, 0.6, 5.75, 12.1, 0.85, "timing card");
  txt(s, "About 3 minutes for 2 devices with the model warm: collection about 20 s, rules under 1 s, LLM about 25 s per config section.", { x: 0.85, y: 5.9, w: 11.6, h: 0.55, fontSize: 14, valign: "middle", color: "3A4A55" });
  s.addNotes("Six of the seven stages are deterministic code. The LLM sits in one stage and code checks its output before it reaches the dashboard.");

  // ---------------------------------------------------------------- 6 knowledge
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "How it works" });
  s.addText("What the tool checks against", { placeholder: "title" });
  const kn = [
    [I.file, "Design docs", "knowledge/design/*.md", "Prose HLD/LLD. Split by heading, embedded, and retrieved per config section for the LLM."],
    [I.code, "Templates", "knowledge/templates/{base,infra,services}", "Junos set lines grouped into rules with ID, severity and design reference. Checked exactly by code."],
    [I.cubes, "Inventory", "config/inventory.yaml", "Roles, the devices in each, which templates apply, per-role variables and drift-ignore patterns."],
  ];
  kn.forEach(([img, h, path, b], i) => {
    const y = 1.45 + i * 1.65;
    badge(s, img, 0.6, y + 0.1, 0.7, C.accent1, h);
    txt(s, h, { x: 1.5, y, w: 4.6, h: 0.4, fontSize: 18, bold: true, fontFace: THEME.headFontFace });
    txt(s, path, { x: 1.5, y: y + 0.42, w: 4.6, h: 0.3, fontSize: 11, fontFace: "Courier New", color: C.accent1 });
    txt(s, b, { x: 1.5, y: y + 0.78, w: 4.6, h: 0.8, fontSize: 13, color: "3A4A55" });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.6, y: 1.45, w: 6.1, h: 4.0, rectRadius: 0.08, fill: { color: "0F1A22" }, line: { type: "none" }, objectName: "template example" });
  txt(s, "templates/services/sipt-vr.set", { x: 6.85, y: 1.6, w: 5.6, h: 0.3, fontSize: 11, color: "93A3AE", fontFace: "Courier New" });
  s.addText([
    { text: "# @id SVC-BGP-AUTH @sev 4", options: { color: "7FD1A0", breakLine: true } },
    { text: "#   @title \"eBGP session has no auth\"", options: { color: "7FD1A0", breakLine: true } },
    { text: "#   @doc \"HLD-qinq-edge §4.2\"", options: { color: "7FD1A0", breakLine: true } },
    { text: "# @scope ^set routing-instances", options: { color: "E6C24A", breakLine: true } },
    { text: "#   (?P<vr>SIPT\\S*) protocols bgp", options: { color: "E6C24A", breakLine: true } },
    { text: "#   group CISCO-ASR\\s", options: { color: "E6C24A", breakLine: true } },
    { text: "set routing-instances {{vr}} protocols", options: { color: "D8E3EA", breakLine: true } },
    { text: "  bgp group CISCO-ASR authentication-key {{*}}", options: { color: "D8E3EA", breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "# forbidden line: prefix with !", options: { color: "93A3AE", breakLine: true } },
    { text: "!set system services telnet{{*}}", options: { color: "F19A95" } },
  ], { isTextBox: true, x: 6.85, y: 2.0, w: 5.6, h: 4.2, fontFace: "Courier New", fontSize: 13, valign: "top", margin: 0 });
  s.addNotes("Templates are the exact checks. @scope repeats a rule per SIPT virtual-router. The design doc is what the LLM reads.");

  // ---------------------------------------------------------------- 7 LLM role
  pres.addSection({ title: "The LLM" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The LLM" });
  s.addText("How the LLM is used", { placeholder: "title" });
  const llmRows = [
    [I.search, "Retrieve", "nomic-embed-text indexes 40 passages: HLD sections plus template rules. The 4 closest are sent with each config section."],
    [I.brain, "Review", "qwen3.5:9b gets one config section at a time (system, interfaces, routing), plus what the rules already found."],
    [I.hist, "Change review", "Each diff is summarised with an intent and a 1–5 risk. Code risk hints set the floor."],
    [I.shield, "Guards", "Every LLM claim must quote real config lines and a design sentence word for word, or it's dropped."],
  ];
  llmRows.forEach(([img, h, b], i) => {
    const y = 1.45 + i * 1.3;
    badge(s, img, 0.6, y + 0.05, 0.65, C.accent2, h);
    txt(s, h, { x: 1.45, y, w: 4.9, h: 0.4, fontSize: 17, bold: true, fontFace: THEME.headFontFace });
    txt(s, b, { x: 1.45, y: y + 0.42, w: 4.9, h: 0.85, fontSize: 13, color: "3A4A55" });
  });
  s.addChart(pres.charts.BAR, [{ name: "Suggestions", labels: ["Duplicate of a rule finding", "Self-cleared (\"this is correct\")", "No-op or unrelated fix", "Kept"], values: [15, 3, 1, 0] }], {
    x: 6.75, y: 1.45, w: 5.95, h: 4.3, barDir: "bar", showTitle: true, title: "What happened to the LLM's 19 suggestions (latest scan)",
    titleFontSize: 13, titleColor: HEX.dk1, titleFontFace: "+mj-lt", chartColors: [HEX.accent2], showValue: true, dataLabelPosition: "outEnd",
    dataLabelColor: HEX.dk1, dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt", catAxisLabelColor: "3A4A55", catAxisLabelFontSize: 12, catAxisLabelFontFace: "+mn-lt",
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false, catAxisOrientation: "maxMin", barGapWidthPct: 60,
    objectName: "llm guard chart",
  });
  txt(s, "The guards work: nothing wrong reached the dashboard. But at 9B the model finds nothing the rules don't already catch.", { x: 6.75, y: 5.9, w: 5.95, h: 0.75, fontSize: 13, italic: true, color: "8A4A12" });
  s.addNotes("Honest result: the guards filter everything the 9B model makes up. Its real value now is change summaries. Deeper reasoning needs a bigger model.");

  // ---------------------------------------------------------------- 8 rules vs LLM
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The LLM" });
  s.addText("Code vs LLM: who does what", { placeholder: "title" });
  const col = (x, title, fill, headColor, img, items, name) => {
    card(s, x, 1.45, 5.9, 4.3, name, fill);
    badge(s, img, x + 0.35, 1.7, 0.65, headColor, name);
    txt(s, title, { x: x + 1.15, y: 1.75, w: 4.5, h: 0.55, fontSize: 20, bold: true, fontFace: THEME.headFontFace, valign: "middle" });
    s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })), { isTextBox: true, x: x + 0.35, y: 2.6, w: 5.25, h: 3.8, fontSize: 14, color: C.text1, paraSpaceAfter: 8, valign: "top", margin: 0 });
  };
  col(0.6, "Code (deterministic)", "DCEFEF", C.accent1, I.code, [
    "Template compliance: exact, repeatable, instant",
    "Scoped checks per VR, interface or VLAN",
    "Drift between devices in the same role",
    "Config diffs, commit window, regressions",
    "Risk hints for known-dangerous changes",
    "Fact-checking every LLM claim",
  ], "code column");
  col(6.8, "LLM (judgement)", "FCECDC", C.accent2, I.brain, [
    "Reads the prose design docs",
    "Plain-English summary and intent for each change",
    "Spots issues that span sections, where templates can't",
    "Best next uses: draft template rules from the HLD and explain findings for the NOC",
    "Limited by a 9B model on a 12 GB GPU",
  ], "llm column");
  s.addNotes("The design principle: if it can be checked exactly, code does it. The LLM is for judgement and language, and code checks its output.");

  // ---------------------------------------------------------------- 9 change tracking
  pres.addSection({ title: "Features" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Features" });
  s.addText("Scans as backups: change tracking", { placeholder: "title" });
  s.addImage({ path: "/home/claude/deck/changes.png", x: 0.6, y: 1.45, w: 7.4, h: 7.4 * 820 / 2784, altText: "Config changes panel showing a qfx2 diff rated High", objectName: "changes screenshot" });
  txt(s, "Lab simulation: qfx2 enabled telnet, removed LLDP and reverted a root-login fix", { x: 0.6, y: 1.45 + 7.4 * 820 / 2784 + 0.1, w: 7.4, h: 0.3, fontSize: 10, color: "5D6B76", italic: true });
  const feats = [
    ["Snapshots", "Every scan stores each device's config. The last 50 scans are kept, and pinned baselines are never deleted."],
    ["Diff + commits", "Compared with the previous scan, with show system commit for who, when and the comment."],
    ["Risk", "17 code hints (telnet, root SSH, BGP auth/policy removed…) plus the LLM summary."],
    ["Regressions", "A finding that was fixed and comes back is flagged REGRESSED."],
    ["Baselines", "Pin a known-good scan per device and see drift from it on every scan."],
  ];
  feats.forEach(([h, b], i) => {
    const y = 1.45 + i * 1.03;
    txt(s, h, { x: 8.4, y, w: 4.3, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
    txt(s, b, { x: 8.4, y: y + 0.36, w: 4.3, h: 0.65, fontSize: 12, color: "3A4A55" });
  });
  card(s, 0.6, 4.4, 7.4, 1.8, "regression explainer");
  badge(s, I.hist, 0.85, 4.65, 0.6, C.accent3, "regression");
  txt(s, "Finding states", { x: 1.65, y: 4.65, w: 6, h: 0.4, fontSize: 16, bold: true });
  s.addText([
    { text: "NEW", options: { bold: true, color: HEX.accent2 } }, { text: "  first time seen     ", options: { color: "3A4A55" } },
    { text: "RECURRING", options: { bold: true, color: "5D6B76" } }, { text: "  also in last scan", options: { color: "3A4A55", breakLine: true } },
    { text: "REGRESSED", options: { bold: true, color: HEX.accent3 } }, { text: "  gone last scan, back now     ", options: { color: "3A4A55" } },
    { text: "ACCEPTED", options: { bold: true, color: HEX.accent5 } }, { text: "  exception, kept across scans", options: { color: "3A4A55" } },
  ], { isTextBox: true, x: 1.65, y: 5.15, w: 6.2, h: 1.2, fontSize: 13, paraSpaceAfter: 6, margin: 0, valign: "top" });
  s.addNotes("No separate backup system needed. Every scan is a snapshot.");

  // ---------------------------------------------------------------- 10 dashboard
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Features" });
  s.addText("The dashboard", { placeholder: "title" });
  const dw = 9.2, dh = dw * 1620 / 2880;
  s.addImage({ path: "/home/claude/deck/dash.png", x: 0.6, y: 1.35, w: dw, h: dh, altText: "Config Check dashboard with compliance score, changes panel, fleet tiles and anomalies table", objectName: "dashboard screenshot", shadow: { type: "outer", color: "000000", opacity: 0.18, blur: 8, offset: 2, angle: 90 } });
  txt(s, "Lab simulation data", { x: 0.6, y: 1.35 + dh + 0.08, w: 4, h: 0.3, fontSize: 10, italic: true, color: "5D6B76" });
  const dashPts = [
    ["Summary", "Score, counts by severity, trend"],
    ["Config changes", "Diff, risk, commits, pin baseline"],
    ["Fleet by role", "Device tiles coloured by worst finding"],
    ["Anomalies", "Filter by severity, source, category"],
    ["Detail", "Evidence, design ref, Junos fix, accept"],
  ];
  dashPts.forEach(([h, b], i) => {
    const y = 1.35 + i * 1.02;
    txt(s, h, { x: 10.1, y, w: 2.65, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
    txt(s, b, { x: 10.1, y: y + 0.36, w: 2.65, h: 0.6, fontSize: 12, color: "3A4A55" });
  });
  s.addNotes("Served by the backend on port 8080. Run scan triggers an on-demand scan; progress shows live.");

  // ---------------------------------------------------------------- 11 security
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Features" });
  s.addText("Read-only by design: three layers", { placeholder: "title" });
  const layers = [
    [I.user, "1 · Device", "Junos login class cc-ro", "permissions view + view-configuration; request / clear / restart / file / configure denied. SSH key only."],
    [I.server, "2 · MCP server", "block.cfg + block.cmd", "Every config load blocked; only show commands allowed. Bound to localhost with bearer-token auth."],
    [I.code, "3 · Backend", "Tool allow-list", "Calls only get_junos_config, gather_device_facts and show commands. Write tools are never called."],
  ];
  layers.forEach(([img, h, sub, b], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.45, 3.85, 3.3, "layer " + (i + 1));
    badge(s, img, x + 0.3, 1.75, 0.75, C.accent1, h);
    txt(s, h, { x: x + 0.3, y: 2.7, w: 3.3, h: 0.45, fontSize: 20, bold: true, fontFace: THEME.headFontFace });
    txt(s, sub, { x: x + 0.3, y: 3.15, w: 3.3, h: 0.35, fontSize: 12, fontFace: "Courier New", color: C.accent1 });
    txt(s, b, { x: x + 0.3, y: 3.6, w: 3.3, h: 1.45, fontSize: 13, color: "3A4A55" });
  });
  badge(s, I.lock, 0.6, 5.2, 0.6, "5D6B76", "data");
  txt(s, "Data never leaves the lab: local Ollama only (cloud models refused by an allow-list). Secrets are masked by Junos in configs, and keys and tokens are stored with mode 600.", { x: 1.4, y: 5.05, w: 11.3, h: 0.9, fontSize: 14, color: "3A4A55", valign: "middle" });
  s.addNotes("Tested: request system reboot and a config load through MCP were both rejected before reaching the device.");

  // ---------------------------------------------------------------- 12 results
  pres.addSection({ title: "Results" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  s.addText("PoC results on the lab", { placeholder: "title" });
  const stats = [["2", "vJunos leaves scanned"], ["23", "template rules"], ["28", "real findings, 6 High"], ["~3 min", "per scan, model warm"]];
  stats.forEach(([n, l], i) => {
    const x = 0.6 + i * 3.08;
    txt(s, n, { x, y: 1.5, w: 2.9, h: 1.1, fontSize: 60, bold: true, color: C.accent1, fontFace: THEME.headFontFace });
    txt(s, l, { x, y: 2.65, w: 2.9, h: 0.4, fontSize: 15, color: "3A4A55" });
  });
  card(s, 0.6, 3.5, 12.1, 2.55, "top findings");
  txt(s, "What it found on the real leaves", { x: 0.9, y: 3.7, w: 11.5, h: 0.4, fontSize: 17, bold: true });
  s.addText([
    { text: "eBGP to the Cisco ASR has no authentication and no import/export policy (both VRs, both leaves)", options: { bullet: true, breakLine: true } },
    { text: "Root SSH login allowed; no NTP, so devices run on local clock; no remote syslog", options: { bullet: true, breakLine: true } },
    { text: "VLAN QINQ-117-111 carries outer tag 107: the name doesn't match the service", options: { bullet: true, breakLine: true } },
    { text: "No BFD or prefix limits; leftover MC-LAG config; IPv6 RA on fxp0; syslog drift between the leaves", options: { bullet: true } },
  ], { isTextBox: true, x: 0.9, y: 4.2, w: 11.5, h: 2.2, fontSize: 14, color: C.text1, paraSpaceAfter: 6, margin: 0, valign: "top" });
  s.addNotes("These are real findings against the starter design doc and templates, which will be replaced with the real standards.");

  // ---------------------------------------------------------------- 13 next steps
  s = pres.addSlide({ masterName: "CLOSE_DARK", sectionTitle: "Results" });
  s.addText("Next steps", { placeholder: "title" });
  const next = [
    [I.file, "Real standards", "Replace the starter HLD and templates with production design docs."],
    [I.brain, "LLM where it adds value", "Draft template rules from the HLD for review; explain findings for the NOC."],
    [I.flask, "Bigger model trial", "Try gpt-oss:20b for cross-section and cross-device reasoning."],
    [I.net, "More roles and devices", "PE, P and RR roles; MX and PTX; scheduled scans with alerts."],
  ];
  next.forEach(([img, h, b], i) => {
    const x = 0.6 + (i % 2) * 6.15, y = 1.9 + Math.floor(i / 2) * 2.2;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.95, h: 1.9, rectRadius: 0.08, fill: { color: "16404A" }, line: { type: "none" }, objectName: "next " + (i + 1) });
    badge(s, img, x + 0.35, y + 0.35, 0.75, C.accent2, h);
    txt(s, h, { x: x + 1.35, y: y + 0.35, w: 4.3, h: 0.5, fontSize: 20, bold: true, color: C.background1, fontFace: THEME.headFontFace });
    txt(s, b, { x: x + 1.35, y: y + 0.9, w: 4.3, h: 1.1, fontSize: 14, color: "CFE3E5" });
  });
  s.addNotes("Close: the platform works end to end. Value now comes from real standards and choosing where the LLM earns its place.");

  await pres.writeFile({ fileName: "/home/claude/deck/Config-Check.pptx" });
  await applyTheme("/home/claude/deck/Config-Check.pptx", THEME);
  console.log("written");
})();
