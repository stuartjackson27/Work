terraform {
  required_version = ">= 1.6"
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.98"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure

  # Snippet (cloud-init) upload and disk import use SSH to the node.
  ssh {
    agent    = var.proxmox_ssh_agent
    username = var.proxmox_ssh_user
    password = var.proxmox_ssh_password
  }
}
