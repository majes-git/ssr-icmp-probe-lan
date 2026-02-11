{% set sbin_path = "/usr/local/sbin" %}
{% set pyz = "ssr-icmp-probe-lan.pyz" %}
{% set monitoring = "ssr-icmp-probe-lan-monitoring.py" %}
{% set base_dir = "/etc/128technology/plugins/network-scripts/host" %}
{% set target_dir = "/etc/128technology/plugins/network-scripts/default/kni_namespace" %}
{% set interface = "probe-gw" %}
{% set interface_dir = base_dir ~ "/" ~ interface %}
{% set interface_config = "/var/lib/128technology/kni/host/" ~ interface ~ ".conf" %}
{% set service_name = "ssr-icmp-probe-lan" %}

Install {{ service_name }} script:
  file.managed:
    - name: {{ sbin_path }}/{{ pyz }}
    - mode: 755
    - source: salt://{{ pyz }}

Create {{ interface_dir }}:
  file.directory:
    - name: {{ interface_dir }}
    - mode: 755
    - makedirs: True

Generate interface config:
  file.managed:
    - name: {{ interface_config }}
    - contents: |
        routing:
            - "default dev {kni_interface} via {kni_gateway}"

{% for name in ["init", "startup", "shutdown"] %}
Install {{ service_name }} symlink for {{ name }}:
  file.symlink:
    - name: {{ interface_dir }}/{{ name }}
    - target: {{ target_dir }}/{{ name }}
{% endfor %}

Install {{ service_name }} monitoring:
  file.managed:
    - name: {{ sbin_path }}/{{ monitoring }}
    - mode: 755
    - source: salt://{{ monitoring }}

Install {{ service_name }} monitoring wrapper:
  file.managed:
    - name: {{ interface_dir }}/monitoring
    - mode: 755
    - contents: |
        #!/bin/sh
        exec /usr/sbin/ip netns exec {{ interface }} {{ sbin_path }}/{{ monitoring }}
    - require:
        - file: {{ sbin_path }}/{{ monitoring }}

Install {{ service_name }} service file:
  file.managed:
    - name: /etc/systemd/system/{{ service_name }}.service
    - contents: |
        [Unit]
        Description=SSR ICMP Probe LAN Service
        After=128T.service
        Requires=128T.service

        [Service]
        ExecStartPre=/usr/sbin/ip netns exec {{ interface }} true
        ExecStart=/usr/sbin/ip netns exec {{ interface }} {{ sbin_path }}/{{ pyz }}
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target

systemd-daemon-reload:
  cmd.run:
    - name: systemctl daemon-reload
    - onchanges:
      - file: /etc/systemd/system/{{ service_name }}.service

{{ service_name }}:
  service.running:
    - enable: True
    - watch:
      - file: /etc/systemd/system/{{ service_name }}.service
      - file: {{ sbin_path }}/{{ pyz }}
      - file: {{ sbin_path }}/{{ monitoring }}
    - require:
      - cmd: systemd-daemon-reload
