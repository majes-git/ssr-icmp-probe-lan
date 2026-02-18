{% set sbin_path = "/usr/local/sbin" %}
{% set prefix = "ssr-icmp-probe-lan-" %}
{% set scripts = ("monitoring", "state") %}
{% set base_dir = "/etc/128technology/plugins/network-scripts/host" %}
{% set target_dir = "/etc/128technology/plugins/network-scripts/default/kni_namespace" %}

{% for script in scripts %}
{% set pyz = prefix ~ script ~ ".pyz" %}
Install {{ script }} script:
  file.managed:
    - name: {{ sbin_path }}/{{ pyz }}
    - mode: 755
    - source: salt://{{ pyz }}
{% endfor %}

# Iterate over all host interfaces that are referenced by static routes
# as next-hop interface
{% set jq_filter = ".datastore.config.authority.router[] as $r
| $r.routing[].\"static-route\"[]
| .[\"next-hop-interface\"][].interface as $ifname
| $r.node[].\"device-interface\"[]
| select(.name == $ifname and .type == \"host\")
| .name" %}
{% set cmd = "jq -r '%s' /var/lib/128technology/t128-running.json" % jq_filter %}

{% for interface in salt['cmd.run'](cmd).splitlines() %}
{% set interface_dir = base_dir ~ "/" ~ interface %}
{% set interface_config = "/var/lib/128technology/kni/host/" ~ interface ~ ".conf" %}
Create {{ interface_dir }}:
  file.directory:
    - name: {{ interface_dir }}
    - mode: 755
    - makedirs: True

{% for script in ["init", "startup", "shutdown"] %}
Install {{ script }} symlink for interface {{ interface }}:
  file.symlink:
    - name: {{ interface_dir }}/{{ script }}
    - target: {{ target_dir }}/{{ script }}
{% endfor %}

{% for script in scripts %}
{% set pyz = prefix ~ script ~ ".pyz" %}
Install {{ script }} wrapper script for interface {{ interface }}:
  file.managed:
    - name: {{ interface_dir }}/{{ script }}
    - mode: 755
    - contents: |
        #!/bin/sh
        exec {{ sbin_path }}/{{ pyz }} "$@"
{% endfor %}

{% endfor %}
