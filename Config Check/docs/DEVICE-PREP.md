# Device preparation (Junos)

Config Check logs in over NETCONF (port 830) as a read-only user. Apply this on
every device, replacing the key with `secrets/configcheck_ed25519.pub`.

```
set system services netconf ssh
set system login class cc-ro permissions view
set system login class cc-ro permissions view-configuration
set system login class cc-ro deny-commands "(request|clear|restart|start|file|configure)"
set system login user configcheck uid 2000
set system login user configcheck class cc-ro
set system login user configcheck authentication ssh-ed25519 "ssh-ed25519 AAAA... configcheck@config-check"
```

Why this is safe:

- `view-configuration` without `secret` means secrets come back as `/* SECRET-DATA */`.
- The class denies every state-changing verb, the MCP server's `block.cmd`/`block.cfg`
  refuse anything but `show`, and the backend only calls read tools. Three
  independent layers.
- After a device rebuild, refresh its host key on the VM (`ssh-keygen -R <ip>`).

Then add the device to `config/inventory.yaml` (with `lo0` and `asn` for fabric
roles), run `python3 scripts/gen_devices.py` and `docker compose restart junos-mcp`.
