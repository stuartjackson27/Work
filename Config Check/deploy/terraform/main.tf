# Ubuntu 24.04 cloud image, imported straight into the VM disk.
resource "proxmox_virtual_environment_download_file" "ubuntu" {
  content_type = "import"
  datastore_id = var.image_datastore
  node_name    = var.node_name
  url          = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
  file_name    = "noble-server-cloudimg-amd64.qcow2" # *.qcow2 so Proxmox imports it as qcow2
  overwrite    = false
}

# cloud-init: admin user, deploy key, then clone the repo and run scripts/deploy.sh.
resource "proxmox_virtual_environment_file" "cloud_init" {
  content_type = "snippets"
  datastore_id = var.image_datastore
  node_name    = var.node_name

  source_raw {
    file_name = "${var.vm_name}-user-data.yaml"
    data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
      hostname     = var.vm_name
      admin_user   = var.admin_user
      ssh_keys     = var.admin_ssh_keys
      deploy_key   = var.github_deploy_key
      repo_url     = var.repo_url
      repo_ref     = var.repo_ref
      ollama_url   = var.ollama_url
      ollama_model = var.ollama_model
      backup_dir   = var.backup_dir
    })
  }
}

resource "proxmox_virtual_environment_vm" "config_check" {
  name        = var.vm_name
  vm_id       = var.vm_id
  node_name   = var.node_name
  description = "Config Check (NetOps config anomaly + security dashboard). Managed by Terraform."
  tags        = ["config-check", "terraform"]
  on_boot     = true

  agent {
    enabled = true # qemu-guest-agent is installed by deploy.sh
  }

  cpu {
    cores = var.cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.memory_mb
  }

  disk {
    datastore_id = var.vm_datastore
    import_from  = proxmox_virtual_environment_download_file.ubuntu.id
    interface    = "virtio0"
    iothread     = true
    discard      = "on"
    size         = var.disk_gb
  }

  network_device {
    bridge = var.bridge
    model  = "virtio"
  }

  operating_system {
    type = "l26"
  }

  serial_device {} # cloud images log to the serial console

  initialization {
    datastore_id = var.vm_datastore
    ip_config {
      ipv4 {
        address = var.ip_cidr
        gateway = var.gateway
      }
    }
    dns {
      servers = var.dns_servers
    }
    user_data_file_id = proxmox_virtual_environment_file.cloud_init.id
  }

  lifecycle {
    # Re-running cloud-init on an existing VM would redeploy; change the VM by hand or taint it.
    ignore_changes = [initialization]
  }
}
