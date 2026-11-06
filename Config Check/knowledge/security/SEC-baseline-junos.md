# Junos Security Baseline

Version 0.1 (draft). Applies to every Junos device in every role. Based on Juniper's
Junos OS hardening guidance and common CIS-style controls. Edit to match your own standard.

This baseline is the reference for the Security tab. Each statement is a best practice; a
device that does not meet it has a gap. Where a role design document approves a deviation
(for example, no BGP authentication inside a closed lab fabric), the gap is still reported
here so it stays visible, and can be accepted as an exception on the dashboard.

Secrets are masked in collected configs (`/* SECRET-DATA */`). Checks can confirm a key or
password is configured, not how strong it is.

## 1 Severity guidance

| Rating | Meaning | Examples |
|---|---|---|
| 5 Critical | Direct exposure now, exploitable without credentials | Telnet or HTTP management enabled, SNMP community with write access, filter that permits any source to management protocols |
| 4 High | Material weakness an attacker can use | No loopback protection filter, root SSH login allowed, external BGP without authentication, SNMPv1/v2c |
| 3 Medium | Missing defence in depth or audit | No central AAA, internal routing protocols without authentication, no login retry limits, no SSH connection limits |
| 2 Low | Hardening hygiene | No NTP authentication, ICMP redirects enabled, LLDP on host-facing ports |
| 1 Info | Advisory | Ping record-route or timestamp answered |

## 2 Management plane access

### 2.1 SSH

- SSH must use protocol version 2 only.
- Root login over SSH must be denied (`system services ssh root-login deny`).
- SSH must have a connection limit and a rate limit (`connection-limit`, `rate-limit`) to slow brute-force attempts and protect the routing engine.
- SSH ciphers, MACs and key-exchange algorithms should be restricted to strong algorithms (for example aes256-gcm, chacha20-poly1305, hmac-sha2-256/512, curve25519-sha256).

### 2.2 Clear-text and unused management services

- Clear-text management services must never be enabled: telnet, ftp, finger, rlogin, `web-management http` and `xnm-clear-text`.
- Management protocols that are not used should not be enabled.

### 2.3 Login protection

- Login retry options must be set so repeated failures disconnect and lock out the session (`system login retry-options tries-before-disconnect` and `lockout-period`).
- A minimum password length of at least 12 characters should be enforced (`system login password minimum-length`).
- A legal login banner (`system login message`) is required.
- The console port should log out the session on disconnect (`system ports console log-out-on-disconnect`).

### 2.4 Authentication, authorisation and accounting

- Operator logins should authenticate against a central TACACS+ or RADIUS service, with local accounts as fallback only (`system authentication-order`).
- Command accounting should be sent to the central AAA service or logged locally.
- Automation accounts must use a dedicated login class with the minimum permissions needed. A read-only class must not include `all`, `secret`, `maintenance`, `shell` or `configure` permissions.
- A root password (`system root-authentication`) must be set for console recovery.

## 3 Control-plane protection

### 3.1 Loopback protection filter

- Every device must apply an input firewall filter to `lo0 unit 0 family inet` that protects the routing engine.
- The loopback filter must permit only the protocols the device needs (BGP from configured peers, BFD, SSH and NETCONF from management prefixes, SNMP from collectors, NTP from configured servers, rate-limited ICMP) and must end with a term that discards and counts everything else.
- If IPv6 is enabled, an equivalent filter must be applied to `lo0 unit 0 family inet6`.

### 3.2 ICMP and IP options

- ICMP redirects must be disabled (`system no-redirects`).
- ICMP traffic to the routing engine should be rate limited (`system internet-options icmpv4-rate-limit`).
- Ping record-route and timestamp options should not be answered (`system no-ping-record-route`, `system no-ping-time-stamp`).
- Host-bound DDoS protection must not be disabled.

## 4 Routing protocol security

### 4.1 BGP

- Every BGP session must be authenticated with an authentication key or key chain.
- External or customer-facing BGP sessions without authentication are a High risk; sessions inside a closed fabric without authentication are a Medium risk.
- External BGP sessions must have explicit import and export policies; Junos accepts and advertises all active BGP routes when no policy is configured.
- BGP sessions should have a maximum-prefix limit (`prefix-limit maximum`) so a peer cannot exhaust the routing table.
- BGP session state changes should be logged (`log-updown`).

### 4.2 IGP and BFD

- OSPF and IS-IS adjacencies must be authenticated if those protocols are used.
- BFD sessions may be authenticated; this is advisory.

## 5 SNMP

- SNMPv1 and SNMPv2c communities must not be configured. Use SNMPv3 with authentication and privacy (authPriv, SHA and AES).
- If a community must exist, it must be read-only and restricted with a `client-list` to named collectors.

## 6 Time

- At least two NTP servers must be configured.
- NTP should use authentication keys and `trusted-key` so time cannot be spoofed; log correlation and certificate checks depend on it.

## 7 Logging and audit

- At least one remote syslog host must be configured; two are preferred.
- Interactive commands must be logged (`syslog file interactive-commands interactive-commands any`).
- Authorisation events must be logged (`syslog file messages authorization info`).
- Firewall filter discard terms should count, and where useful log, the traffic they drop.

## 8 Services and unused features

- LLDP should run only on infrastructure links, not on host-facing or customer-facing ports, because it discloses device details to the attached host.
- LLDP-MED should only be enabled where voice or media endpoints need it.
- Unused physical interfaces should be disabled.

## 9 Firewall filter (ACL) practice

- Every firewall filter must end with an explicit term that discards (not rejects) and counts unmatched traffic.
- No filter term may permit management protocols (SSH, NETCONF, SNMP, HTTP/HTTPS) from any source address; sources must be restricted to management prefix lists.
- Terms should reference prefix lists rather than hard-coded addresses so filters stay consistent.
- A permit term must not shadow a later, more specific deny term.
- Every term should have a counter so its use can be audited.

## 10 Layer 2 access edge (leaf host ports)

- Host access ports must have storm control applied (`family ethernet-switching storm-control`).
- Host access ports must block BPDUs (`protocols layer2-control bpdu-block interface`) so a host cannot inject spanning-tree frames.
- Host access ports should limit learned MAC addresses.
