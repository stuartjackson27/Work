# Hardening Config Check for production

Status as of the PoC (Nov 2026). **P1** = must have before production, **P2** = should have.

## Web dashboard and API
| # | Item | PoC status | Pri |
|---|---|---|---|
| 1.1 | HTTPS via reverse proxy (Caddy/nginx/Traefik) with an internal-CA cert | Plain HTTP :8080 | P1 |
| 1.2 | SSO (OIDC: Entra ID / Keycloak, e.g. oauth2-proxy) | None | P1 |
| 1.3 | Roles: viewer / operator (scan, accept exception) / admin | None | P1 |
| 1.4 | Audit trail: who accepted an exception or pinned a baseline, with a required comment | Changes recorded, no identity | P1 |
| 1.5 | Bind :8080 to 127.0.0.1 behind the proxy (Docker publishing bypasses ufw/iptables) | 0.0.0.0:8080 | P1 |
| 1.6 | CSRF on POSTs; CSP/HSTS/X-Frame-Options headers | None | P2 |
| 1.7 | Rate-limit `/api/scan` | One scan at a time | P2 |
| 1.8 | Audit HTML escaping of config text and LLM output | Mostly escaped | P2 |

## LLM (Ollama)
| # | Item | PoC status | Pri |
|---|---|---|---|
| 2.1 | Ollama has no auth: put it behind TLS + API key/mTLS, or firewall it to the VM only | Open on LAN :11434 | P1 |
| 2.2 | Configs travel to the LLM host in clear text | Plaintext | P1 |
| 2.3 | Dedicated managed GPU host, not a desktop | Desktop RTX 3060 | P1 |
| 2.4 | Local models only (allow-list blocks `:cloud`); any cloud key in a secrets manager | Allow-list ✅ | P1 |
| 2.5 | Prompt-injection containment: LLM has no tools, JSON only, guarded output, fixes never auto-applied | ✅ keep | P1 |
| 2.6 | Pin model digests | Model recorded per scan | P2 |

## Device access
| # | Item | PoC status | Pri |
|---|---|---|---|
| 3.1 | Read-only login class | ✅ | done |
| 3.2 | Secrets masked (no `secret` permission); add a redaction pass as second layer | Masking ✅ | P1 |
| 3.3 | MCP server localhost-only, bearer token, block.cfg/block.cmd | ✅ | done |
| 3.4 | Pinned SSH host keys (managed known_hosts) | accept-new | P1 |
| 3.5 | SSH key in a vault / agent, rotated | File, mode 600 | P2 |
| 3.6 | lo0 filter on devices: SSH/NETCONF only from the Config Check IP | Not done | P1 |
| 3.7 | TACACS+/RADIUS read-only profile with accounting | Local user | P2 |
| 3.8 | Rotate the MCP token | Static | P2 |

## Data at rest
| # | Item | PoC status | Pri |
|---|---|---|---|
| 4.1 | Encrypt the disk: the DB holds full network configs | Unencrypted | P1 |
| 4.2 | Encrypted, off-host backups (the Nov 2026 Proxmox failure is the lesson) | Local tarballs | P1 |
| 4.3 | Retention | 50 scans ✅ | done |
| 4.4 | Templates outrank the LLM, so protect `knowledge/` with git review + signed commits | Read-only mount ✅ | P1 |

## Host, containers, operations
| # | Item | Pri |
|---|---|---|
| 5.1 | Host firewall: 443 from ops subnet, SSH from admin hosts | P1 |
| 5.2 | Containers: read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, limits | P2 |
| 5.3 | Pin image digests / pip hashes, scan images (Trivy) | P2 |
| 5.4 | Management VLAN, not the general LAN | P1 |
| 6.1 | Logs + audit to syslog/SIEM; alert on failed scans and unreachable devices | P2 |
| 6.2 | Backup/restore test and DR runbook | P2 |
