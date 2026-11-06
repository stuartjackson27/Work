# EVPN-VXLAN Fabric — High Level Design

Version 0.2 (lab). Roles: `evpn-spine`, `evpn-leaf`. Lab: EVE-NG `EVPN_VXLAN_QFX`.
Replaces the QinQ service edge design (v0.1), which is retired (see §9).

## 1 Scope and topology

A two-tier IP fabric with two spines and two leaves on vJunos-switch.

- Underlay: eBGP over point-to-point /31 links. Every device has its own ASN.
- Overlay: eBGP EVPN between loopbacks. Leaves peer with every spine; spines
  peer with every leaf. There are no leaf-to-leaf or spine-to-spine sessions.
- Data plane: VXLAN. Leaves are the VTEPs. Spines are lean IP transit and do
  not run EVPN instances or VXLAN.
- Services: Layer 2 only (bridged VLANs stretched over VXLAN). No IRB or
  routed overlay in this release.

Every leaf connects to every spine. The same port number is used at both ends
of a fabric link (SPINE1 ge-0/0/0 to QFX1 ge-0/0/0), so cabling can be checked
from either end. Leaf ports ge-0/0/0 and ge-0/0/1 are fabric uplinks; ge-0/0/2
and up are host-facing access ports.

## 2 Base configuration (all roles)

### 2.1 Management access

- SSH protocol version 2 only.
- Root login over SSH is denied (`root-login deny`). Operators use named
  accounts; root is console-only.
- A root password (`system root-authentication`) must be set on every device for
  console recovery. Its presence is required and correct; do not flag it.
- NETCONF over SSH is enabled for automation.
- Telnet and FTP are never enabled. All management is over SSH.
- Automation tools use a dedicated read-only login class `cc-ro` with `view` and
  `view-configuration` permissions only. The `configcheck` user and its SSH key
  are expected on every device; do not flag them.
- Management is out-of-band on `fxp0` only. IPv6 router advertisements must not
  be sent on the management interface.

### 2.2 Time

- Two NTP servers: 10.250.0.1 and 10.250.0.2.
- Time zone UTC on all devices so logs correlate across the estate.
- A device on LOCAL CLOCK is non-compliant: BGP and syslog timestamps cannot
  be trusted during incident analysis.

### 2.3 Logging

- Remote syslog to 10.250.0.20, facility `any`, level `notice`.
- Local files: `messages` (any notice) and `interactive-commands`
  (interactive-commands any) for audit.

### 2.4 SNMP

- SNMPv3 only. No SNMPv2c communities of any name.

### 2.5 Login banner

- A legal login banner (`system login message`) is required on every device.

### 2.6 Platform defaults

- No deviations from platform defaults are approved in the fabric. In
  particular `system arp aging-timer` must not be set (the 5-minute timer was a
  QinQ edge exception and does not apply here).

## 3 Addressing and ASN plan

The Config Check inventory (`config/inventory.yaml`) is the source of truth for
per-device values: `lo0` (loopback), `asn`, and the role of each device. A
device whose loopback, router-id or ASN disagrees with the inventory is
misconfigured, not the inventory.

| Device | Role | Mgmt (fxp0) | Loopback lo0.0 | ASN |
|---|---|---|---|---|
| SPINE1 | evpn-spine | 192.168.1.54/24 | 10.255.0.1/32 | 65001 |
| SPINE2 | evpn-spine | 192.168.1.55/24 | 10.255.0.2/32 | 65002 |
| QFX1 (Leaf_1) | evpn-leaf | 192.168.1.52/24 | 10.255.0.11/32 | 65011 |
| QFX2 (Leaf_2) | evpn-leaf | 192.168.1.53/24 | 10.255.0.12/32 | 65012 |

- Loopbacks come from 10.255.0.0/24: spines .1–.9, leaves .11 and up.
- Spine ASNs 65001–65009, leaf ASNs 65011 and up.
- Fabric links come from 10.0.0.0/16, one /31 per link: 10.0.<spine>.x, the
  spine takes the even address and the leaf the odd one.

| Link | Spine end | Leaf end |
|---|---|---|
| SPINE1–QFX1 | ge-0/0/0 10.0.1.0/31 | ge-0/0/0 10.0.1.1/31 |
| SPINE1–QFX2 | ge-0/0/1 10.0.1.2/31 | ge-0/0/1 10.0.1.3/31 |
| SPINE2–QFX2 | ge-0/0/0 10.0.2.2/31 | ge-0/0/0 10.0.2.3/31 |
| SPINE2–QFX1 | ge-0/0/1 10.0.2.0/31 | ge-0/0/1 10.0.2.1/31 |

## 4 Underlay

### 4.1 Loopback and router-id

- `lo0 unit 0 family inet address <lo0>/32`.
- `routing-options router-id` equals the loopback address.
- `routing-options autonomous-system` equals the device ASN.

### 4.2 Fabric links

Every routed fabric port (a ge/xe/et interface with `unit 0 family inet
address`) must have:

- `mtu 9192`, so VXLAN-encapsulated jumbo frames are not fragmented or
  dropped. An MTU mismatch on a fabric link causes silent drops of large
  frames in the overlay.
- a description naming the far-end device and port, `to <DEVICE> <port>`.
- a /31 address on unit 0 only.

### 4.3 eBGP underlay (group UNDERLAY)

- `type external`.
- Export policy `UNDERLAY-EXPORT`, which advertises the loopback (`from
  interface lo0.0`) only. Without it no loopbacks are learnt and the overlay
  cannot come up.
- `multipath multiple-as`, plus the `ECMP` policy (`then load-balance
  per-packet`) applied as `routing-options forwarding-table export ECMP`, so
  traffic uses all spines.
- BFD `minimum-interval 1000`, `multiplier 3`.
- One neighbor per fabric link, with a `description` naming the far-end device
  and `peer-as` equal to that device's ASN.
- A leaf must have an underlay session to every spine, and a spine to every
  leaf. A missing session removes a path and halves fabric capacity.

### 4.4 Discovery protocols

- LLDP is enabled on all interfaces.

## 5 Overlay (group OVERLAY)

- `type external`, `multihop no-nexthop-change`, so the leaf VTEP stays the
  BGP next hop for EVPN routes as they pass through the spines.
- `local-address` equals the device loopback.
- `family evpn signaling`.
- `multipath multiple-as`.
- BFD `minimum-interval 3000`, `multiplier 3`.
- Leaves peer with the loopback of every spine; spines peer with the loopback
  of every leaf. Each neighbor has a `description` and a `peer-as` equal to
  the far-end ASN. An overlay neighbor that is not a fabric device in the
  inventory is a finding.
- No BGP authentication is used on fabric sessions in the lab (closed fabric);
  do not flag its absence.

## 6 Spine role (`evpn-spine`)

- Spines are lean IP transit: they carry EVPN routes but do not originate them.
- `protocols bgp group OVERLAY keep all` is mandatory on spines. Spines have no
  EVPN instance or route-target import, so without `keep all` they discard
  every EVPN route they receive and leaves never learn each other's MACs.
- Spines must not have `protocols evpn`, `switch-options`, VXLAN VLANs or
  `family ethernet-switching` host ports. Any of these suggests a leaf
  template was applied to a spine.

## 7 Leaf role (`evpn-leaf`)

### 7.1 EVPN and VTEP

- `protocols evpn encapsulation vxlan` and `extended-vni-list all`.
- `switch-options vtep-source-interface lo0.0`.
- `switch-options route-distinguisher <lo0>:1`. The RD must be unique per leaf;
  a duplicated RD hides one leaf's routes behind the other's.
- `switch-options vrf-target target:65000:1` on every leaf. A leaf with a
  different route target does not import the other leaves' routes, which
  black-holes traffic for every stretched VLAN.
- Leaves do not set `keep all`.

### 7.2 VLANs and VNIs (Layer 2 services)

- Each stretched VLAN is named `V<vlan-id>` (for example `V100`).
- Each VLAN has `vxlan vni` equal to 10000 + VLAN ID (VLAN 100 = VNI 10100).
- The same VLAN must use the same VNI on every leaf. A VNI mismatch between
  leaves splits the broadcast domain and is an outage for that VLAN.
- The factory `default` VLAN (vlan-id 1) is not stretched and is ignored.

### 7.3 Host access ports

- Host ports use `unit 0 family ethernet-switching interface-mode access` and
  `vlan members V<id>`.
- Each host port has a description naming the host and VLAN, for example
  `"VPC1 - VLAN 100"`.
- Host ports must not be configured on fabric uplinks (ge-0/0/0, ge-0/0/1).

### 7.4 Bridged only

- No `irb` interfaces and no `l3-interface` on VLANs in this release. Routing
  between VLANs is out of scope; an IRB is an unapproved change.

## 8 Features not used in the fabric

- MC-LAG and ESI-LAG are not used. No `multi-chassis` stanzas should be
  present. Leftover stanzas suggest a copied template and confuse
  troubleshooting.
- No routing instances (virtual-router or VRF) in this release.

## 9 Retired design

The QinQ service edge (S/C-VLAN hand-off into SIPT virtual-routers, VLANs
named `QINQ-<S>-<C>`, BGP group `CISCO-ASR`) is retired. Any of its remaining
configuration on a fabric device (`vlan-tags`, `flexible-vlan-tagging`,
`SIPT-*` routing instances, `QINQ-*` VLANs) is leftover config and should be
removed. The old design is kept in `knowledge/archive/` for reference only.

## 10 Severity guidance

| Rating | Meaning | Examples |
|---|---|---|
| 5 Critical | Outage or black-hole now, or a direct security exposure | VNI mismatch between leaves, wrong vrf-target, spine without `keep all` |
| 4 High | Service at risk or a material security weakness | Missing overlay/underlay session, no UNDERLAY-EXPORT, fabric MTU wrong, root SSH allowed, SNMPv2c |
| 3 Medium | Deviation that hurts operations or resilience | No NTP, no remote syslog, no BFD, loopback/ASN differs from plan, no ECMP |
| 2 Low | Hygiene or consistency | Missing descriptions, leftover stanzas, VLAN naming, peer drift |
| 1 Info | Cosmetic or advisory | Missing banner, time zone |
