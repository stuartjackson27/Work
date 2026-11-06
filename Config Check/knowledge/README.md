# Knowledge folder

Config Check reads everything in this folder on every scan.

```
knowledge/
├── design/              Design docs (.md, .txt). Used by the LLM as reference.
├── archive/             Retired designs and templates. Never read by scans.
└── templates/
    ├── base/            Applies to every role
    ├── infra/           Interfaces, IGP/BGP underlay, VLANs
    └── services/        Customer services (VRs, VRFs, L2VPN, QoS)
```

Which templates apply to which role is set in `config/inventory.yaml`
(`roles.<role>.templates`). An entry can be a folder (`base`) or a file
without its extension (`infra/evpn-leaf`).

## Template syntax (`.set` files)

Templates are Junos `set` lines grouped into rule blocks. A block starts with a
metadata comment and runs until the next metadata comment.

```
# @id BASE-NTP @sev 3 @title "NTP not configured" @doc "HLD-evpn-fabric §2.2"
set system ntp server {{ntp1}}
set system ntp server {{ntp2}}
```

| Line | Meaning |
|---|---|
| `set ...` | Required. A finding is raised if no config line matches. |
| `!set ...` | Forbidden. A finding is raised for every config line that matches. |
| `# @scope <regex>` | Repeat the block once per match. Named groups (`(?P<vr>...)`) become placeholders. |
| `# @builtin <name>` | Run a built-in check (see below) instead of matching lines. |
| `# plain comment` | Ignored by the rule engine; still read by the LLM. |

Metadata keys: `@id` (unique), `@sev` 1–5, `@title`, `@doc` (design
reference shown on the finding).

Placeholders:

| Placeholder | Matches |
|---|---|
| `{{name}}` | One token, or a quoted string. If `name` is a scope group or an inventory var, it must equal that value. |
| `{{*}}` | The rest of the line (anything). |

Inventory vars (`defaults.vars`, `roles.<role>.vars` and per-device `vars`) fill
placeholders in both the match and the suggested fix, e.g. `ntp1: 10.250.0.1`.
Device vars win over role vars, which win over defaults. The fabric uses
per-device `lo0` and `asn`, so `set routing-options router-id {{lo0}}` checks
each device against the addressing plan.

## Built-in checks

| Name | What it checks |
|---|---|
| `fabric_peers` | UNDERLAY and OVERLAY BGP sessions match the inventory: one overlay session to every device of role `vars.peer_role` (its `lo0`, `peer-as` = its `asn`), at least one underlay session per peer ASN, and no unknown neighbors or ASNs |
| `vni_mapping` | Every VLAN (except `default`) has `vxlan vni` = `vni_base` + vlan-id and is named `<vlan_prefix><vlan-id>` |
| `vlan_name_tags` | Retired QinQ design: VLANs named `QINQ-<S>-<C>` match their unit's tags |
| `orphan_mclag` | `multi-chassis` stanzas present with no `mc-ae` interface |

Role drift (lines present on some devices in a role but not others) is checked
automatically. Ignore patterns live in `roles.<role>.drift_ignore`.

## Current roles

| Role | Templates | Design |
|---|---|---|
| `evpn-spine` | base, infra/fabric-underlay, infra/fabric-overlay, infra/evpn-spine | HLD-evpn-fabric |
| `evpn-leaf` | base, infra/fabric-underlay, infra/fabric-overlay, infra/evpn-leaf, services/l2-vni | HLD-evpn-fabric |

To add a device, add it under its role in `config/inventory.yaml` with its
`lo0` and `asn`, then run `scripts/gen_devices.py` and restart the stack. The
`fabric_peers` check then expects every device of the other role to peer
with it.
