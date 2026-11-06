# QinQ Service Edge — High Level Design

Version 0.1 (lab starter). Role: `qinq-edge`.

## 1 Scope

The QinQ service edge terminates double-tagged customer hand-offs from the
aggregation layer (Cisco ASR) and routes each service into its own
virtual-router. The first service type is SIP trunking (SIPT). Each hand-off
carries one S-VLAN (outer tag) per customer site and one C-VLAN (inner tag)
per service.

## 2 Base configuration

### 2.1 Management access

- SSH protocol version 2 only.
- Root login over SSH is denied (`root-login deny`). Operators use named
  accounts; root is console-only.
- A root password (`system root-authentication`) must be set on every device for
  console recovery. Its presence is required and correct; do not flag it.
- NETCONF over SSH is enabled for automation.
- Telnet and FTP are never enabled. All management is over SSH.
- Automation tools use a dedicated read-only login class with `view` and
  `view-configuration` permissions only.
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

## 3 Infrastructure

### 3.1 QinQ hand-off interfaces

Every physical interface that carries double-tagged units must have:

- `flexible-vlan-tagging`
- `encapsulation flexible-ethernet-services`
- `mtu 9192` (aggregation transport MTU)
- a description naming the far-end device and the S-VLAN it carries

### 3.2 Service units

- Each service unit uses `encapsulation vlan-bridge` and
  `vlan-tags outer <S-VLAN> inner <C-VLAN>`.
- Unit number equals the C-VLAN.
- Each unit has a description: `QinQ service outer <S> inner <C>`.

### 3.3 Bridge domains (VLANs) and naming

- One VLAN per service, named `QINQ-<S-VLAN>-<C-VLAN>`.
- `vlan-id` equals the C-VLAN.
- The VLAN name must match the tags of its member unit. NOC tooling and the
  service inventory key on this name, so a name that disagrees with the tags
  causes mis-routed tickets and wrong service impact during outages.
- Exactly one member interface unit and one `l3-interface irb.<C-VLAN>`.

### 3.4 IRB interfaces

- IRB unit number equals the C-VLAN.
- `family inet mtu 1500` (customer-facing SIP MTU).
- /30 or /31 point-to-point addressing.
- A description naming the service.

### 3.5 Discovery protocols

- LLDP is enabled on all interfaces.

### 3.6 Approved deviations from platform defaults

- `system arp aging-timer 5` is approved on this role for fast SIP failover.
  Do not flag it.

### 3.7 Features not used in this role

- MC-LAG is not used on the QinQ service edge. No `multi-chassis` stanzas
  should be present. Leftover stanzas suggest a copied template and confuse
  troubleshooting.

## 4 Services — SIP trunk virtual-routers (SIPT-*)

### 4.1 Instance

- `instance-type virtual-router`.
- The instance contains only the IRB(s) of its service.

### 4.2 eBGP to aggregation

Every SIPT instance peers with the aggregation router in BGP group
`CISCO-ASR`:

- `type external`, correct `peer-as` for the service, edge `local-as`.
- Neighbor description.
- MD5 authentication (`authentication-key`) is mandatory. An unauthenticated
  customer-facing session is a security finding.
- BFD: `minimum-interval 300`, `multiplier 3`.
- Import policy `SIPT-IN` (accept customer SIP prefixes, /24 to /32 only).
- Export policy `SIPT-OUT` (advertise SBC prefixes only).
- Without import/export policies, Junos eBGP accepts nothing and advertises
  nothing by default, so the trunk carries no routes. Treat missing policy as
  service-affecting.
- Prefix limit: `family inet unicast prefix-limit maximum 100` with
  `teardown`.
- `log-updown`.

### 4.3 Policy objects

- `policy-options policy-statement SIPT-IN` and `SIPT-OUT` must exist if any
  instance references them.

## 5 Severity guidance

| Rating | Meaning | Examples |
|---|---|---|
| 5 Critical | Outage or black-hole now, or a direct security exposure | Service unit in the wrong VLAN, RT/AS mismatch that drops routes |
| 4 High | Service at risk or a material security weakness | No BGP auth, no BGP policy, root SSH allowed, SNMPv2c |
| 3 Medium | Deviation that hurts operations or resilience | No NTP, no remote syslog, no BFD, VLAN name ≠ tags |
| 2 Low | Hygiene or consistency | Missing descriptions, leftover stanzas, peer drift |
| 1 Info | Cosmetic or advisory | Missing banner, log-updown |
