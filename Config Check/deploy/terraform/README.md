# Deploy Config Check to Proxmox with Terraform

One `terraform apply` creates the VM from the Ubuntu 24.04 cloud image. cloud-init then
clones this repo and runs `scripts/deploy.sh`, which installs Docker, builds the stack and
starts the dashboard. Provider: [bpg/proxmox](https://registry.terraform.io/providers/bpg/proxmox).

## One-time Proxmox prep (on the Proxmox host)

```bash
# 1. Let 'local' hold cloud-init snippets and importable disk images
pvesm set local --content iso,vztmpl,backup,snippets,import

# 2. API user + token for Terraform
pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role PVEAdmin   # narrow later if you like
pveum user token add terraform@pve tf --privsep 0   # copy the secret it prints
```

Terraform also SSHes to the node (snippet upload and disk import). Load your key into
ssh-agent (`ssh-add`) for `root@proxmox`, or set `proxmox_ssh_password`.

## Private repo access

Create a deploy key and add the **public** half on GitHub (repo → Settings → Deploy keys,
read-only). Put the **private** half in `github_deploy_key`:

```bash
ssh-keygen -t ed25519 -N "" -f ./gh_deploy -C config-check-deploy
```

## Deploy

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars    # fill in
terraform init
terraform apply
```

First boot takes about 5–10 minutes. Follow it with the `follow_install` output command. When it finishes:

1. Add the new switch key (the `switch_key` output) to every switch:
   `set system login user configcheck authentication ssh-ed25519 "<key>"`
2. Open the `dashboard_url` output and press **Run scan**.

## Notes

- **Re-deploying code** doesn't need Terraform: `ssh` in and run
  `sudo bash /opt/config-check/scripts/deploy.sh` (it pulls `main` and restarts).
- `initialization` is in `ignore_changes`, so editing tfvars won't silently rebuild the VM.
  To rebuild it on purpose: `terraform apply -replace=proxmox_virtual_environment_vm.config_check`.
- Back up `data/` off the host: mount an NFS/SMB share and point `backup_dir` at it.
- `terraform.tfvars` and the state files contain secrets and are git-ignored.
