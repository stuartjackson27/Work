# EVE-NG lab: EVPN-VXLAN fabric

Lab `Juniper Labs/EVPN_VXLAN_QFX.unl`, vJunos-switch 25.4R1.12 (5120 MB RAM, 4 vCPU each).

| Node | Role | fxp0 | lo0 | ASN |
|---|---|---|---|---|
| Spine_1 | evpn-spine | 192.168.1.54 | 10.255.0.1 | 65001 |
| Spine_2 | evpn-spine | 192.168.1.55 | 10.255.0.2 | 65002 |
| Leaf_1 (QFX1) | evpn-leaf | 192.168.1.52 | 10.255.0.11 | 65011 |
| Leaf_2 (QFX2) | evpn-leaf | 192.168.1.53 | 10.255.0.12 | 65012 |

Links use matching ports at both ends: SPINE1 ge-0/0/0 ↔ QFX1 ge-0/0/0, SPINE1 ge-0/0/1 ↔ QFX2 ge-0/0/1,
SPINE2 ge-0/0/0 ↔ QFX2 ge-0/0/0, SPINE2 ge-0/0/1 ↔ QFX1 ge-0/0/1. The VPCs sit on leaf ge-0/0/2 (VLAN 100, VNI 10100).
In EVE, vJunos-switch eth0 = fxp0 and ethN = ge-0/0/(N-1).

- `fabric-configs.txt`: full spine configs, leaf additions, QinQ cleanup, base standards, VPC setup and checks.
- `spine1-restore.txt`: SPINE1 rebuilt from a Config Check scan backup (for a box that boots "Amnesiac").

Tips: start nodes 2–3 minutes apart. After pasting a config, run `request system configuration rescue save`
so a crash can be recovered with `rollback rescue`.
