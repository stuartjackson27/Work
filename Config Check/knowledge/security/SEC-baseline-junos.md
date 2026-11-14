# Junos Security Baseline

Version 1.0. Applies to every Junos device in every role.

Primary reference: *This Week: Hardening Junos Devices, 2nd Edition* (John Weidley, Juniper
Networks Books, 2015) and its companion checklist. Sections below follow the checklist's
headings, and each one names the book chapter it comes from. The book is not copied here:
statements are written for this tool, and the book is the place to read the reasoning and
worked examples. Where the book was written against Junos 12.3 and current releases do
better, this baseline uses the current option and says so (see §12). Items the book does not
cover come from this tool's earlier draft baseline and are marked *(local addition)*.

This baseline is the reference for the Security tab. Each statement is a best practice; a
device that does not meet it has a gap. Where a role design document approves a deviation
(for example LLDP on every fabric interface), the gap is still reported here so it stays
visible, and can be accepted as an exception on the dashboard.

Secrets are masked in collected configs (`/* SECRET-DATA */`). Checks can confirm a key or
password is configured, not how strong it is.

## 1 Severity guidance

| Rating | Meaning | Examples |
|---|---|---|
| 5 Critical | Direct exposure now, exploitable without credentials | Telnet, FTP or HTTP management enabled; SNMP community with write access; a filter that permits any source to management protocols |
| 4 High | Material weakness an attacker can use | No routing-engine protection filter; root login over SSH; external BGP without authentication |
| 3 Medium | Missing defence in depth or audit | No central AAA or accounting; SNMPv1/v2c in use; no login retry limits; no SSH limits; one NTP or syslog server only; source routing or directed broadcast enabled |
| 2 Low | Hardening hygiene | No NTP authentication; ICMP redirects on; weak password policy; console not logged out on disconnect; no idle timeouts |
| 1 Info | Advisory | Ping record-route or timestamp answered; ICMP source quench; no enhanced syslog timestamps |

## 2 Administrative (book Ch. 1)

- Check the Juniper Security Advisories for every release in use, and run the release Juniper recommends for the platform. *(Process item: not visible in a configuration.)*
- Before redeploying a device that was used elsewhere, reinstall it from media so no previous configuration or data remains. *(Process item.)*
- Encrypt the configuration file where the platform supports it. *(Process item; operational command.)*

## 3 Physical and console security (book Ch. 2)

### 3.1 Ports

- Unused network ports should be disabled (`set interfaces <port> disable`) and described as unused.
- The console port must log the session out when the cable is unplugged (`system ports console log-out-on-disconnect`), so the next person does not inherit a logged-in session.
- The console port should be marked `insecure` (`system ports console insecure`), which stops root logging in on the console and forces password recovery to require the root password. Make sure the root password is known and stored safely first.
- Where the platform has an auxiliary port, it should be disabled and marked insecure (`system ports auxiliary disable`, `system ports auxiliary insecure`).
- Where the platform has diagnostic or PIC console ports, they should be password protected (`system diag-port-authentication`, `system pic-console-authentication`).
- Where the platform has a craft interface or LCD menu, unneeded functions should be disabled (for example `chassis craft-lockout` on MX).

## 4 Network and IP stack security (book Ch. 3 and 4)

- Management traffic should use the out-of-band management interface (fxp0/em0/re0:mgmt) and not in-band interfaces.
- Traffic the routing engine originates (NTP, SNMP, syslog, RADIUS/TACACS+) should use the loopback address as its source (`system default-address-selection`).
- ICMP redirects must be disabled (`system no-redirects`).
- IP source routing must not be enabled (`routing-options source-routing`); it is off by default since Junos 8.5.
- IP directed broadcast must not be enabled (`family inet targeted-broadcast` on an interface); it is off by default.
- Proxy ARP should not be configured; if it is needed it must be restricted to the interfaces that need it and must not be `proxy-arp unrestricted`.
- TCP packets with both SYN and FIN set must be dropped (`system internet-options tcp-drop-synfin-set`).
- Ping record-route and timestamp requests should not be answered (`system no-ping-record-route`, `system no-ping-time-stamp`).
- ICMP source quench should be ignored (`system internet-options no-source-quench`).
- ICMP to the routing engine should be rate limited (`system internet-options icmpv4-rate-limit`). *(local addition)*
- Host-bound DDoS protection must not be disabled. *(local addition)*

## 5 Management services security (book Ch. 4)

### 5.1 NTP

- At least two NTP servers must be configured, preferably in different locations.
- NTP must be authenticated: an `authentication-key`, the key listed in `trusted-key`, and each `server` referencing the key. Use SHA-256 keys where supported (the book uses MD5; see §12).

### 5.2 SNMP

- Use SNMPv3 with authentication and privacy (`security-level privacy`, SHA authentication, AES privacy). This is the most secure SNMP method.
- If SNMPv1/v2c communities must exist, they must be read-only, hard to guess, and limited to named collectors with `clients` or `client-list-name` ending in `0.0.0.0/0 restrict`.
- An SNMP community with `authorization read-write` must never be configured.
- Allow SNMP queries from, and send traps to, more than one collector.
- Restrict what each user or community can read with SNMP views.

### 5.3 Syslog

- Logs must be sent to at least two remote syslog hosts.
- Syslog should use enhanced timestamps that include the year and milliseconds (`system syslog time-format year`, `time-format millisecond`).
- Interactive commands must be logged (`syslog file interactive-commands interactive-commands any`).
- Authorisation events must be logged (`syslog file messages authorization info`).

### 5.4 Configuration backup

- The configuration should be archived automatically to more than one secure off-box site on every commit (`system archival configuration transfer-on-commit` with `archive-sites` using scp or sftp). Config Check keeps a copy at every scan, but it is not a substitute: it only captures what was running when it scanned.

## 6 Access security (book Ch. 4)

### 6.1 Banner and services

- A warning banner must be displayed before login (`system login message`). It should state that unauthorised use is prohibited and give a contact; a placeholder text does not meet the requirement.
- Insecure or unnecessary access services must not be enabled: telnet, ftp, finger, rlogin, `web-management http` and `xnm-clear-text`.

### 6.2 SSH

- SSH version 2 only.
- Root login over SSH must be denied (`system services ssh root-login deny`).
- SSH must have a connection limit and a rate limit (`connection-limit`, `rate-limit`) to slow brute force and protect the routing engine.
- SSH ciphers, MACs and key-exchange algorithms should be restricted to strong algorithms. The book's list includes CBC ciphers and hmac-sha1, which are now considered weak; use for example `ciphers [ aes256-gcm@openssh.com chacha20-poly1305@openssh.com aes256-ctr ]`, `macs [ hmac-sha2-512 hmac-sha2-256 ]`, `key-exchange [ curve25519-sha256 ecdh-sha2-nistp384 ]`.
- NETCONF over SSH should have its own connection and rate limits (`system services netconf ssh connection-limit`, `rate-limit`). Set them high enough for automation: Config Check opens several sessions per device per scan, so a rate limit below 10 per minute can make scans fail.

### 6.3 J-Web

- If J-Web is used, it must be HTTPS only, with a certificate signed by a trusted CA.
- J-Web should only listen on authorised interfaces (`web-management https interface`).
- J-Web sessions should time out when idle and be limited in number (`web-management session idle-timeout`, `session-limit`).

## 7 User authentication security (book Ch. 4)

### 7.1 Password policy

- A password complexity policy must be enforced: a minimum length (the book uses 15; at least 12), and a mix of upper case, lower case, numeric and punctuation characters (`system login password minimum-length`, `change-type character-sets`, `minimum-upper-cases`, `minimum-lower-cases`, `minimum-numerics`, `minimum-punctuations`).
- Passwords must be stored with a strong hash (`system login password format sha512`; the book's `sha1` is outdated, see §12).
- The root account must have a strong password (`system root-authentication`).

### 7.2 Login protection

- Login retry options must slow password guessing and lock out repeated failures (`system login retry-options tries-before-disconnect`, `backoff-threshold`, `backoff-factor`, `lockout-period`).

### 7.3 Login classes

- Engineers must use custom login classes built on least privilege: permissions and `allow-commands`/`deny-commands` matched to the job, not `super-user` for everyone.
- Every login class must have an idle timeout (`system login class <name> idle-timeout`).
- Access to secret data (`permissions secret`) must be limited to the few people who need it.
- Automation accounts must use a dedicated read-only class. A read-only class must not include `all`, `secret`, `shell`, `maintenance` or `configure` permissions. *(local addition)*

### 7.4 Centralised authentication

- Operators should authenticate against central TACACS+ or RADIUS, with local passwords as fallback only (`system authentication-order`).
- Shared secrets must be strong and follow the password policy.
- At least two authentication servers should be configured for resilience.
- Accounting must record logins, configuration changes and interactive commands (`system accounting events [ login change-log interactive-commands ]` with an accounting `destination`).
- An emergency local account should exist for when the authentication servers are unreachable.

### 7.5 Local accounts

- The origin and purpose of every local account must be known; remove accounts that are no longer needed.
- Local accounts must be limited to users who need them, with strong passwords.
- `authentication-order` must match the login security policy.

## 8 Routing protocol security (book Ch. 4)

- Routing protocols must only be configured on the interfaces that need them; loopbacks should be passive.
- BGP sessions to loopback addresses (internal and multihop sessions) must source from the loopback (`local-address`).
- Every routing protocol session must be authenticated with the strongest algorithm both ends support: BGP, OSPF, IS-IS, LDP, RSVP and RIP.
- External or customer-facing BGP sessions without authentication are a High risk; sessions inside a closed fabric without authentication are a Medium risk. *(local addition)*
- Authentication keys must be strong, follow the password policy, and differ between organisations (do not reuse the key you share with a provider on internal sessions).
- Keys should be changed periodically; use key chains with hitless rollover where the protocol supports it (`security authentication-key-chains`).
- External BGP sessions must have explicit import and export policies, a maximum-prefix limit, and log state changes (`log-updown`). *(local addition)*

## 9 Routing engine firewall filter (book Ch. 4)

- Every device must apply an input firewall filter to `lo0 unit 0 family inet` that protects the routing engine; if IPv6 is enabled, apply an equivalent `family inet6` filter.
- The filter must be default deny: it permits only the protocols the device needs, from authorised sources (prefix lists such as BGP neighbours, NTP servers, SNMP collectors and management networks).
- Terms for time-sensitive protocols (BGP, BFD, OSPF/IS-IS) should come first.
- TCP SYN packets to the routing engine should be rate limited to resist SYN floods.
- Permitted protocols should be rate limited with policers (ICMP and traceroute especially).
- The final default-deny term must discard (not reject) and must log and syslog what it drops.
- No filter term may permit management protocols (SSH, NETCONF, SNMP, HTTP/HTTPS) from any source address. *(local addition)*
- Every term should have a counter so its use can be audited. *(local addition)*

## 10 LLDP and unused features (book Ch. 4)

- LLDP should run only on the interfaces that need it (infrastructure links, phones), because it is unauthenticated and discloses device details to whatever is attached. The book's pattern is to disable LLDP on all interfaces and enable it per interface.
- LLDP-MED should only be enabled where voice or media endpoints need it, never on all interfaces.
- Note: the EVPN fabric design (HLD-evpn-fabric §4.4) enables LLDP on all interfaces. That conflicts with this section; resolve it in the design or accept the gap as an exception.

## 11 Layer 2 access edge *(local addition)*

- Host access ports must have storm control applied (`family ethernet-switching storm-control`).
- Host access ports must block BPDUs (`protocols layer2-control bpdu-block interface`) so a host cannot inject spanning-tree frames.
- Host access ports should limit learned MAC addresses.

## 12 Where this baseline departs from the book

The book was tested on Junos 12.3. Current releases support stronger options, so this baseline uses them:

| Book | This baseline | Why |
|---|---|---|
| Password `format sha1` | `format sha512` | SHA-1 is no longer considered strong; SHA-512 is supported on current Junos |
| SSH ciphers include CBC modes, MACs include hmac-sha1 | GCM/CTR ciphers, SHA-2 MACs, modern key exchange | CBC and SHA-1 are deprecated by current SSH guidance |
| NTP and routing-protocol keys use MD5 | SHA-256 / HMAC-SHA where both ends support it | MD5 is weak; keep MD5 only for peers that support nothing else |
| SSH version 2 is a setting to choose | Still checked, but v2 is the only option on current releases | |
| SNMPv2c communities shown in the sample | SNMPv3 preferred; communities only if read-only and restricted | Matches the checklist's "most secure method" |
