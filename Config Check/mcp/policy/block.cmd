# Junos MCP server: operational-command block list (execute_junos_command[_batch]).
# Config Check only needs "show" commands. Everything that can change state,
# reach a shell or move files is blocked. One regex per line.
# (The backend also refuses any command not starting with "show ", and the
#  device login class cc-ro denies the same verbs: three independent layers.)
^request
^clear
^restart
^start
^file
^configure
^edit
^load
^commit
^rollback
^op
^test
^monitor
^set
^delete
^ping
^traceroute
^ssh
^telnet
