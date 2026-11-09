output "dashboard_url" {
  value = "http://${split("/", var.ip_cidr)[0]}:8080"
}
output "ssh" {
  value = "ssh ${var.admin_user}@${split("/", var.ip_cidr)[0]}"
}
output "follow_install" {
  description = "First boot takes ~5-10 min (packages, Docker, image builds)"
  value       = "ssh ${var.admin_user}@${split("/", var.ip_cidr)[0]} 'sudo tail -f /var/log/config-check-deploy.log'"
}
output "switch_key" {
  value = "When the install finishes: ssh ${var.admin_user}@${split("/", var.ip_cidr)[0]} sudo cat /opt/config-check/secrets/configcheck_ed25519.pub  -> add to every switch"
}
