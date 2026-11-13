# Config Check is read-only. Block every operational verb that can change state,
# reach out from the device, or enter config mode. Only "show" remains usable.
# (The device-side cc-ro login class enforces the same thing.)
^\s*(request|clear|restart|start|file|test|configure|edit|op|monitor|ping|traceroute|telnet|ssh|ftp|set|delete|load|commit|rollback|save|run|activate|deactivate)\b
\|\s*(save|tee)\b
