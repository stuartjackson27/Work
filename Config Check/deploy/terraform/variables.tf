# ---- Proxmox connection --------------------------------------------------
variable "proxmox_endpoint" {
  description = "Proxmox API URL, e.g. https://192.168.1.14:8006/"
  type        = string
}
variable "proxmox_api_token" {
  description = "API token: user@realm!tokenid=secret"
  type        = string
  sensitive   = true
}
variable "proxmox_insecure" {
  description = "Skip TLS verification (self-signed Proxmox cert)"
  type        = bool
  default     = true
}
variable "proxmox_ssh_user" {
  type    = string
  default = "root"
}
variable "proxmox_ssh_agent" {
  description = "Use your local ssh-agent for the node SSH login"
  type        = bool
  default     = true
}
variable "proxmox_ssh_password" {
  description = "Only if not using ssh-agent"
  type        = string
  default     = null
  sensitive   = true
}
variable "node_name" {
  type    = string
  default = "pve"
}

# ---- VM ------------------------------------------------------------------
variable "vm_id" {
  type    = number
  default = 111
}
variable "vm_name" {
  type    = string
  default = "config-check"
}
variable "cores" {
  type    = number
  default = 2
}
variable "memory_mb" {
  type    = number
  default = 4096
}
variable "disk_gb" {
  type    = number
  default = 32
}
variable "vm_datastore" {
  description = "Storage for the VM disk (local-zfs, local-lvm, ...)"
  type        = string
  default     = "local-zfs"
}
variable "image_datastore" {
  description = "Storage with 'import' and 'snippets' content enabled"
  type        = string
  default     = "local"
}
variable "bridge" {
  type    = string
  default = "vmbr0"
}
variable "ip_cidr" {
  description = "Static IP for the VM"
  type        = string
  default     = "192.168.1.39/24"
}
variable "gateway" {
  type    = string
  default = "192.168.1.1"
}
variable "dns_servers" {
  type    = list(string)
  default = ["192.168.1.1"]
}
variable "admin_user" {
  type    = string
  default = "stuart"
}
variable "admin_ssh_keys" {
  description = "Public keys allowed to log in as admin_user"
  type        = list(string)
}

# ---- Config Check --------------------------------------------------------
variable "repo_url" {
  type    = string
  default = "git@github.com:stuartjackson27/config-check.git"
}
variable "repo_ref" {
  type    = string
  default = "main"
}
variable "github_deploy_key" {
  description = "Private key of a read-only GitHub deploy key (private repo). Leave empty for a public repo over https."
  type        = string
  default     = ""
  sensitive   = true
}
variable "ollama_url" {
  type    = string
  default = "http://192.168.1.232:11434"
}
variable "ollama_model" {
  type    = string
  default = "deepseek-r1:14b"
}
variable "backup_dir" {
  description = "Nightly backup target inside the VM (mount an NFS/SMB share here for off-host backups). Empty = no backup job."
  type        = string
  default     = "/var/backups/config-check"
}
