# Config Check operator guide

How to manage everything that you, not the code, look after: devices, roles, design docs,
templates, the security baseline, settings, keys, and the decisions you make on the dashboard.

## 1. What you manage, and when changes apply

| What | Where | Applies |
|---|---|---|
| Devices and roles | `config/inventory.yaml` | Next scan. **New, removed or re-addressed devices** also need `scripts/gen_devices.py` + `docker compose restart junos-mcp` |
| Design docs | `knowledge/design/*.md` | Next scan |
| Security baseline | `knowledge/security/*.md` | Next scan |
| Rule templates | `knowledge/templates/**/*.set` | Next scan |
| Runtime settings (LLM, scoring, retention) | `config/settings.yaml` | Next scan |
| MCP command policy | `mcp/policy/block.cmd`, `block.cfg` | `docker compose restart junos-mcp` |
| Switch login key, MCP token | `secrets/` (never in git) | See §7 |
| Exceptions, baselines, scan history | Dashboard → `data/config-check.db` | Immediately. **Back up `data/`** |
| Dashboard / backend code | `app/` | `docker compose up -d --build` |

Config and knowledge are re-read at the start of every scan; there's no cache to clear. Design and
baseline text is re-embedded automatically when it changes (the cache is keyed on content).

**Always run the checker after an edit:**

```bash
cd /opt/config-check
docker compose exec backend python scripts/check_knowledge.py
```

It catches duplicate rule IDs, template names that don't exist, bad regexes, unknown built-ins,
placeholders with no value, docs without headings, and PDFs/Word files that won't be read.
Errors stop it with exit code 1; warnings are advice.

### Recommended workflow

1. Edit in git (GitHub web or a local clone), commit.
2. On the VM, pull and copy into place:
   ```bash
   cd /root/Work && git pull && cp -r "Config Check/." /opt/config-check/
   ```
3. Run the checker; if a device was added, regenerate `devices.json` (§2).
4. Press **Run scan**.

This keeps git as the record of who changed which rule and when. That matters because templates
can silence findings (§4.3).

---

## 2. Adding a device

### 2.1 Prepare the device
Apply [DEVICE-PREP.md](DEVICE-PREP.md): NETCONF over SSH, the read-only `cc-ro` class and the
`configcheck` user with the key from `secrets/configcheck_ed25519.pub`.

Test from the VM (a copy of the key is needed because the real file belongs to the MCP user):
```bash
install -m 600 secrets/configcheck_ed25519 /root/.cc_test_key
ssh -i /root/.cc_test_key -o StrictHostKeyChecking=accept-new configcheck@<mgmt-ip> "show version | match Junos"
rm -f /root/.cc_test_key
```

### 2.2 Add it to the inventory
Put it under its role in `config/inventory.yaml`:

```yaml
roles:
  evpn-leaf:
    devices:
      qfx1: { host: 192.168.1.52, model: vJunos-switch, lab: EVPN_VXLAN_QFX, vars: { lo0: 10.255.0.11, asn: 65011 } }
      qfx3: { host: 192.168.1.56, model: QFX5120, vars: { lo0: 10.255.0.13, asn: 65013 } }   # new
```

| Field | Required | Meaning |
|---|---|---|
| key (`qfx3`) | ✅ | Device name shown on the dashboard. Unique, lowercase, no spaces |
| `host` | ✅ | Management IP or DNS name the VM can reach on port 830 |
| `vars` | For fabric roles | Per-device values that templates check: `lo0` (loopback) and `asn`. Unique per device |
| `model`, `lab` | ❌ | Labels only |
| `port`, `username`, `key_file` | ❌ | Override `defaults` (830 / configcheck / `/secrets/configcheck_ed25519`) for this device |

### 2.3 Tell the MCP server
```bash
python3 scripts/gen_devices.py          # rewrites config/devices.json from the inventory
docker compose restart junos-mcp
docker compose exec backend python scripts/check_knowledge.py
```
Then **Run scan**.

Things to know:
- **Fabric peers follow the inventory.** The `fabric_peers` check expects every device of the
  other role to peer with the new one. Add a leaf, and the spines get findings until their BGP
  sessions to it exist. That's intended, because it shows the change is incomplete.
- **Drift is per role.** The new device is compared with its role peers. Lines that legitimately
  differ per device (hostname, addresses, descriptions) are ignored by `drift_ignore` (§6).
- **Removing a device:** delete its line, run `gen_devices.py`, restart `junos-mcp`. Its history
  stays in the database until retention removes it.
- **Changing a device's IP:** edit `host`, regenerate, restart, then `ssh-keygen -R <old-ip>` on the VM.

---

## 3. Adding a role

A role is a group of devices built to the same design: same templates, same design doc, drift
compared between them.

```yaml
roles:
  border-leaf:
    description: EVPN border leaf (Type-5 to the WAN)
    design:   [design/HLD-evpn-fabric.md, design/HLD-border.md]   # docs the LLM checks against
    security: [security/SEC-baseline-junos.md]                    # baseline for the Security tab
    templates: [base, infra/fabric-underlay, infra/fabric-overlay, infra/border-leaf,
                security/common, security/l2-edge]
    vars:
      peer_role: evpn-spine        # used by fabric_peers
      vrf_target: target:65000:1
    drift_ignore: *fabric_drift    # reuse the shared list, or write your own
    devices:
      bl1: { host: 192.168.1.60, vars: { lo0: 10.255.0.21, asn: 65021 } }
```

| Key | Meaning |
|---|---|
| `description` | Shown on the dashboard and given to the LLM as context |
| `design` | Design docs (paths under `knowledge/`). **Always set it.** If it's missing, the LLM uses *every* doc in `knowledge/design/` |
| `security` | Security baseline docs for the Security tab |
| `templates` | Template folders (`base`) or files without `.set` (`infra/evpn-leaf`), applied in order |
| `vars` | Values shared by the role. Device `vars` override role `vars`, which override `defaults.vars` |
| `drift_ignore` | Regexes for lines allowed to differ between devices in the role |

Role vars used by the built-in checks:

| Var | Used by | Meaning |
|---|---|---|
| `peer_role` | `fabric_peers` | The role this role must peer with |
| `vrf_target` | `infra/evpn-leaf` | Expected EVPN route target |
| `vni_base`, `vlan_prefix` | `vni_mapping` | VNI = `vni_base` + VLAN ID; VLAN name = `vlan_prefix` + ID |
| `ntp1`, `ntp2`, `syslog_host` (defaults) | `base`, `security` | Standard servers |

---

## 4. The knowledge folder

```
knowledge/
├── design/        Design docs per role (Anomalies tab, LLM reference)
├── security/      Security baseline (Security tab, LLM reference)
├── templates/
│   ├── base/      Every role: management, time, logging, SNMP     → Anomalies tab
│   ├── infra/     Interfaces, underlay, overlay, role specifics   → Anomalies tab
│   ├── services/  Customer/L2/L3 services                         → Anomalies tab
│   └── security/  Security controls                              → Security tab
└── archive/       Retired designs and templates (never read)
```

The top-level template folder sets the finding's category, and `security/` puts findings on the
**Security** tab. A new folder name becomes its own category on the Anomalies tab.

### 4.1 Design docs and the security baseline

The LLM reads these in passages, one per heading, and every finding must quote a sentence from
them **word for word**. How you write them decides how good the LLM's findings are.

**Format rules**
- **Markdown (`.md`) or plain text (`.txt`) only.** Convert Word/PDF first, e.g.
  `pandoc HLD.docx -t gfm -o knowledge/design/HLD-x.md`, then tidy the headings.
- **Number every heading:** `## 3 Underlay`, `### 3.1 Loopback`. Findings then cite
  "HLD-x §3.1 Loopback" and the reference is shown on the finding.
- **Keep each section focused**, about 5–20 lines. A huge section can't be retrieved precisely.
- **The file name is the reference name** (`HLD-evpn-fabric.md` → "HLD-evpn-fabric").

**Writing rules** (these directly reduce false positives)

| Do | Why |
|---|---|
| One rule per bullet, as a full sentence with **must / must not / should** | The LLM quotes one sentence; a rule split across bullets can't be quoted |
| Put the exact Junos statement in backticks, e.g. `` `multihop no-nexthop-change` `` | Matches the config the LLM is reading |
| State approved deviations explicitly, e.g. "X is approved on this role. Do not flag it." | Without it, the LLM flags your deliberate choices |
| Say *why* for important rules ("…otherwise EVPN routes are dropped") | Gives the LLM the impact, so its severity is better |
| End with a severity table (5 Critical … 1 Info, with examples) | The LLM rates findings against it |
| Keep values **per section**: underlay values in the underlay section, overlay in overlay | Mixed sections are how the BFD 1000/3000 false positive happened |

**Adding a design doc for a role:** create `knowledge/design/HLD-<name>.md`, list it under
the role's `design:`, run the checker, scan.

**Editing the security baseline:** `knowledge/security/SEC-baseline-junos.md` is a draft from Junos
hardening guidance. Replace or extend it with your organisation's standard using the same format.
To use a customer's standard for one role, add a second file and list it under that role's `security:`.

### 4.2 Templates (the rule engine)

Templates are Junos `set` lines grouped into rule blocks. They're **deterministic**: same config,
same findings, every scan. Use them for anything with a definite right answer.

```
# @id SEC-NTP-AUTH @sev 2 @title "NTP not authenticated" @doc "SEC-baseline-junos §6"
# @practice "Use NTP authentication keys (sha256) and trusted-key so time cannot be spoofed."
set system ntp authentication-key {{*}}
set system ntp trusted-key {{*}}
```

| Element | Meaning |
|---|---|
| `# @id` | Unique rule ID, e.g. `<AREA>-<THING>`. **Never rename it**: accepted exceptions are tied to it |
| `@sev` | 1 Info, 2 Low, 3 Medium, 4 High, 5 Critical |
| `@title` | Finding title, written as the problem ("NTP not authenticated") |
| `@doc` | Reference to the design or baseline section, shown on the finding |
| `# @practice "…"` | Best-practice text shown on the Security tab (use it for security rules) |
| `set …` | **Required**: a finding is raised if no config line matches |
| `!set …` | **Forbidden**: a finding is raised for each config line that matches |
| `# @scope <regex>` | Repeat the block per match; named groups become placeholders |
| `# @builtin <name>` | Run a coded check: `fabric_peers`, `vni_mapping`, `bgp_auth`, `orphan_mclag`, `vlan_name_tags` |
| `# plain comment` | Ignored by the rules, read by the LLM |

**Placeholders**

| Placeholder | Matches |
|---|---|
| `{{*}}` | Anything to the end of the line |
| `{{name}}`, where `name` is an inventory var | Must equal that value for this device, e.g. `{{lo0}}`, `{{ntp1}}` |
| `{{name}}`, where `name` is a scope group | Must equal what the scope matched, e.g. the interface |
| `{{name}}` with no value | Any single value (the checker warns you) |

**Examples**

*Per-interface rule with `@scope`:* every routed fabric port needs jumbo MTU and a description.
```
# @id FAB-LINK @sev 4 @title "Fabric link missing jumbo MTU or description" @doc "HLD-evpn-fabric §4.2"
# @scope ^set interfaces (?P<ifd>(?:ge|xe|et)-[\d/]+) unit 0 family inet address
set interfaces {{ifd}} mtu 9192
set interfaces {{ifd}} description {{*}}
```

*Forbidden config:*
```
# @id SEC-CLEARTEXT @sev 5 @title "Clear-text management service enabled" @doc "SEC-baseline-junos §2.2"
!set system services telnet{{*}}
!set system services ftp{{*}}
```

*Per-device value from the inventory:*
```
# @id FAB-LO0 @sev 3 @title "Loopback, router-id or ASN differs from the plan" @doc "HLD-evpn-fabric §4.1"
set interfaces lo0 unit 0 family inet address {{lo0}}/32
set routing-options autonomous-system {{asn}}
```

**Test a new rule before scanning** against a config saved by an earlier scan:
```bash
docker compose exec backend python scripts/check_knowledge.py --test qfx1 /opt/config-check/data/configs/<scan-id>/qfx1.set
```

**Important: templates outrank the LLM.** If a template requires a line, the LLM can never flag that
line, and the code drops any LLM finding that contradicts a template. A wrong template therefore
hides real problems. Review template changes like code (§1 workflow).

**Rules vs design doc:** if a rule has a definite answer, write a template, so it's checked
deterministically and fixed suggestions are exact. Put the *intent and reasoning* in the design doc
too, so the LLM understands context and can catch what templates can't express.

### 4.3 Retiring a design
Move the doc and its templates into `knowledge/archive/<name>/` and remove them from the role.
Nothing in `archive/` is read.

---

## 5. Settings (`config/settings.yaml`)

| Setting | Default | When to change |
|---|---|---|
| `llm.enabled` | `true` | `false` = rules and drift only (fast, deterministic) |
| `llm.base_url` | `http://192.168.1.232:11434` | Ollama host moved |
| `llm.model` | `deepseek-r1:14b` | Testing another model (must be in `allowed_models`; pull it in Ollama first) |
| `llm.allowed_models` | local models | Add a model before using it; `:cloud` models are deliberately excluded |
| `llm.timeout_s` | 240 | Raise to 420 if scans show LLM timeouts |
| `llm.retrieve_k` | 4 | Doc passages per prompt (security pass uses +2). Higher = more context, slower |
| `llm.min_confidence` | 0.5 | Raise to drop more low-confidence LLM findings |
| `llm.num_ctx` | 8192 | Model context window; raise only if the GPU has room |
| `scoring.weights` | `[0,1,2,4,7,12]` | Penalty per open finding by severity (index = sev) |
| `retention.scans` | 50 | Scans kept (configs + findings); pinned baselines always kept |

---

## 6. Drift rules (`drift_ignore`)

Drift finds lines that some devices in a role have and others don't. List regexes for lines that are
**meant** to differ per device; they're skipped:

```yaml
_fabric_drift: &fabric_drift
  - '^set system host-name '
  - '^set interfaces \S+ description '
  - ' family inet address '
  - ' neighbor \S+'
```

If a drift finding is noise (a per-device value), add a pattern. If it's real (a device is missing
config its peers have), fix the device.

---

## 7. Keys, tokens and the MCP policy

**Switch login key** (`secrets/configcheck_ed25519`). To rotate:
```bash
ssh-keygen -t ed25519 -N "" -C "configcheck@config-check" -f secrets/configcheck_ed25519.new
# add secrets/configcheck_ed25519.new.pub to every switch, then:
mv secrets/configcheck_ed25519.new secrets/configcheck_ed25519
mv secrets/configcheck_ed25519.new.pub secrets/configcheck_ed25519.pub
chown 999:999 secrets/configcheck_ed25519 && chmod 600 secrets/configcheck_ed25519
docker compose restart junos-mcp
# then remove the old key from the switches
```

**MCP token** (backend → MCP server). To rotate:
```bash
out=$(docker run --rm -u 0 -v "$PWD/secrets:/out:z" config-check/junos-mcp:local sh -c \
  'python jmcp_token_manager.py generate --id config-check-backend && cp .tokens /out/jmcp-tokens.json')
printf '%s' "$(echo "$out" | awk '/Token:/ {print $2}')" > secrets/jmcp-backend.token
chown 999:999 secrets/jmcp-tokens.json && chown 1000:1000 secrets/jmcp-backend.token
chmod 600 secrets/jmcp-tokens.json secrets/jmcp-backend.token
docker compose restart junos-mcp backend
```

File ownership matters: the MCP server runs as UID **999** (token list, SSH key) and the backend as
UID **1000** (its token, `data/`).

**MCP policy** (`mcp/policy/block.cmd` / `block.cfg`). These are regexes for commands and config
loads the MCP server refuses. Config Check only needs `show`; `block.cfg` refuses every config load.
**Don't loosen these.** They're one of three read-only layers, with the device login class and the
backend's own tool allow-list.

---

## 8. Dashboard decisions

| Action | What it does | Stored in |
|---|---|---|
| **Accept as exception** | Moves a finding to Accepted, with your note, and keeps it there on later scans while the same rule fires on the same device and path | `data/` DB, keyed on device + source + rule ID + path |
| **Pin baseline** | Marks a device's current config as its reference for change tracking (kept even past retention) | `data/` DB |
| Config changes tab | Commit history and diffs: every scan is a config backup | `data/configs/<scan>/` |

Because exceptions are keyed on the rule ID, **renaming a template `@id` brings back every finding
you'd accepted for it**.

These decisions exist only in `data/`. **Back it up** off the VM (nightly cron in the README). If you
want an exception recorded in git, prefer changing the design doc ("approved deviation") or the
template, so it's reviewed and survives a rebuild.

---

## 9. Quick reference

| I want to… | Do this |
|---|---|
| Add a switch to an existing role | Device prep → inventory line → `gen_devices.py` → restart `junos-mcp` → checker → scan |
| Add a new kind of device | New role in the inventory + design doc + templates → checker → scan |
| Add a design rule | Bullet in the design doc; if it has a definite answer, a template too |
| Stop a false positive | Rule finding: fix the template. LLM finding: state the approval in the doc, or add a template so it outranks the LLM. One-off: accept as exception |
| Use my company's security standard | Replace or extend `knowledge/security/SEC-baseline-junos.md` and `templates/security/` |
| Make scans faster | `llm.enabled: false`, or a smaller model |
| Try a template before scanning | `check_knowledge.py --test <device> <saved .set file>` |
