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
{% set router_name = salt['cmd.run']("jq -r '.init.routerName' /etc/128technology/global.init") %}
{% set jq_filter = '.datastore.config.authority.router[]
| select(.name == "' ~ router_name ~ '") as $r
| $r.routing[]?."static-route"[]?
| .["next-hop-interface"][]?.interface as $ifname
| $r.node[]?."device-interface"[]?
| select(.type == "host")."network-interface"[]?
| select(.name == $ifname)
| .name' %}
{% set cmd = "jq -r '%s' /var/lib/128technology/t128-running.json" % jq_filter %}

{% for interface in salt['cmd.run'](cmd).splitlines() %}
{% set interface_dir = base_dir ~ "/" ~ interface %}
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
