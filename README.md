# anro_nagios

`anro_nagios` installs Nagios Core from the Ubuntu apt repositories and provides a reusable baseline configuration for Ubuntu 20.04 and newer.

The role deliberately separates configuration ownership:

- Ansible owns the Nagios platform, Apache integration, standard shared objects, and baseline localhost checks.
- Administrators own site-specific objects below dedicated custom directories.
- `nagios-cmd` provides a safe interface for creating and changing administrator-owned objects while protecting Ansible-managed aggregate files.

## Features

- Installs Ubuntu `nagios4` packages and monitoring plugins with `ansible.builtin.apt`.
- Configures Nagios, Apache, optional Postfix, file authentication, and optional LDAP authentication.
- Validates Apache and Nagios configuration before service reloads.
- Supports standard commands, contacts, contact groups, templates, and time periods through role variables.
- Allows playbook-provided standard objects to override built-in objects with the same logical name.
- Provides configurable baseline localhost monitoring.
- Installs the dependency-free `nagios-cmd` helper for administrator-managed configuration.
- Preserves administrator-managed files across subsequent Ansible converges.

## Basic usage

```yaml
---
- name: Configure Nagios
  hosts: nagios
  become: true

  roles:
    - role: anro_nagios
      vars:
        anro_nagios_domain: example.com
        anro_nagios_users:
          - name: nagiosadmin
            password: "{{ vault_nagios_password }}"
```

Passwords and LDAP credentials should be supplied from Ansible Vault or another secret-management mechanism.

## Configuration ownership

The Ubuntu package configuration normally lives at `/etc/nagios4`. By default the role creates `/etc/nagios` as a compatibility symlink. The role refuses to replace `/etc/nagios` when it is an existing real directory.

### Ansible-managed files

These aggregate files are authoritative and should be changed through role variables rather than edited manually:

```text
/etc/nagios4/nagios.cfg
/etc/nagios4/cgi.cfg
/etc/nagios4/resource.cfg
/etc/nagios4/objects/commands.cfg
/etc/nagios4/objects/contacts.cfg
/etc/nagios4/objects/templates.cfg
/etc/nagios4/objects/timeperiods.cfg
/etc/nagios4/objects/localhost.cfg
```

### Administrator-managed directories

The role creates but does not purge or synchronize the contents of these directories:

```text
/etc/nagios4/objects/commands/
/etc/nagios4/objects/contacts/
/etc/nagios4/objects/contactgroups/
/etc/nagios4/objects/hosts/
/etc/nagios4/objects/servicegroups/
/etc/nagios4/objects/templates/
/etc/nagios4/objects/timeperiods/
/etc/nagios4/servicedefs/
```

Custom directories are `nagios:nagios` mode `0750`. Files written by `nagios-cmd` are normalized to `nagios:nagios` mode `0640`.

Ubuntu sample object files removed from the aggregate `objects/` directory are controlled by `anro_nagios_packaged_objects_remove`. Override that list if a deployment intentionally retains one of those packaged filenames.

Run mutating `nagios-cmd` operations as root or as the Nagios service account so the helper can maintain that ownership policy.

## Standard shared configuration through variables

Playbook/group variables can define objects that should remain consistent across multiple Nagios servers.

```yaml
anro_nagios_commands:
  - command_name: check_api_health
    command_line: >-
      /usr/lib/nagios/plugins/check_http -H $HOSTADDRESS$ -u /health

anro_nagios_contacts:
  - contact_name: operations
    use: generic-contact
    alias: Operations
    email: operations@example.com

anro_nagios_contactgroups:
  - contactgroup_name: oncall
    alias: On-call Operations
    members: operations

anro_nagios_templates_service:
  - name: standard-http-service
    use: generic-service
    check_interval: 5
    retry_interval: 1
    max_check_attempts: 3
    register: 0

anro_nagios_templates_timeperiod:
  - name: business-hours
    timeperiod_name: business-hours
    alias: Business Hours
    monday: 08:00-17:00
    tuesday: 08:00-17:00
    wednesday: 08:00-17:00
    thursday: 08:00-17:00
    friday: 08:00-17:00
```

When a playbook-provided command, contact, contact group, or template has the same logical name as a built-in role definition, the playbook definition replaces the built-in definition. Duplicate names within the user-provided list are rejected during role validation.

## Baseline localhost monitoring

The role creates a localhost host and hostgroup plus a baseline set of service checks. The service list is configurable:

```yaml
anro_nagios_local_services:
  - service_description: PING
    check_command: check_ping!100.0,20%!500.0,60%
  - service_description: Root Partition
    check_command: check_local_disk!20%!10%!/
  - service_description: Current Load
    auto_load: true
  - service_description: SSH
    check_command: check_ssh
```

Additional Nagios service directives can be supplied with `options`:

```yaml
anro_nagios_local_services:
  - service_description: HTTPS
    check_command: check_http!-S
    options:
      check_interval: 2
      retry_interval: 1
```

Automatic load thresholds are based on vCPU count and can be tuned with:

```yaml
anro_nagios_local_load_warning_multiplier: 1.0
anro_nagios_local_load_critical_multiplier: 1.5
```

Set `anro_nagios_localhost_enabled: false` to omit the role-managed localhost object.

## Apache and authentication

File authentication is enabled by default through `anro_nagios_basic_auth_provider` and users in `anro_nagios_users`.

LDAP can be enabled with:

```yaml
anro_nagios_use_ldap: true
anro_nagios_ldap_provider: nagios-ldap
anro_nagios_basic_auth_provider:
  - file
  - nagios-ldap
anro_nagios_auth_ldap_url: ldaps://ldap.example.com/ou=people,dc=example,dc=com?uid?sub
anro_nagios_auth_ldap_bind_dn: cn=nagios,ou=service,dc=example,dc=com
anro_nagios_auth_ldap_bind_pw: "{{ vault_nagios_ldap_password }}"
```

When LDAP is disabled, the role removes the generated Apache LDAP configuration so bind credentials are not left on disk.

Apache service lifecycle is configurable independently from Nagios:

```yaml
anro_nagios_apache_service_enabled: true
anro_nagios_apache_service_state: started
```

Only durable service states (`started` and `stopped`) are accepted. Configuration-triggered reloads are handler-owned so repeated role executions remain idempotent.

The TLS certificate file should include any required intermediate certificates. `anro_nagios_certificate_chain_file` is retained only for v2 compatibility and is no longer rendered into Apache configuration.

## Postfix

Local Postfix support is enabled by default for email notifications and can be disabled completely:

```yaml
anro_nagios_postfix_enabled: false
```

Postfix settings exposed by the role include:

```yaml
anro_nagios_postfix_service_enabled: true
anro_nagios_postfix_service_state: started
anro_nagios_postfix_relayhost: "[smtp.example.com]:25"
anro_nagios_postfix_inet_interfaces: loopback-only
```

The default listener is loopback-only because this role needs an outbound mail transport for Nagios notifications, not a network-accessible SMTP server.

## `nagios-cmd`

`nagios-cmd` only modifies files below the explicit administrator-managed roots listed above. It refuses to modify Ansible-owned aggregate files such as `objects/commands.cfg`.

Every mutating operation writes atomically, validates the complete Nagios configuration, and restores the previous file content and metadata when validation fails. A successful write does not automatically reload Nagios; reload explicitly after completing a group of changes:

```bash
sudo nagios-cmd config check
sudo nagios-cmd config reload
```

### Hosts and hostgroups

```bash
sudo nagios-cmd host add web01 10.10.10.10
sudo nagios-cmd host add web02 10.10.10.11 --hostgroup linux
sudo nagios-cmd host show
sudo nagios-cmd host show web01
sudo nagios-cmd host set web01 10.10.10.20 --force
sudo nagios-cmd host remove web01 --force

sudo nagios-cmd hostgroup add linux
sudo nagios-cmd hostgroup show
```

Hosts without an explicit hostgroup are stored under `objects/hosts/default/`.

### Commands, contacts, contact groups, service groups, templates, and time periods

```bash
sudo nagios-cmd command add check_custom \
  --options 'command_line=/usr/lib/nagios/plugins/check_dummy 0 custom-ok'

sudo nagios-cmd contact add operator --options email=operator@example.com
sudo nagios-cmd contactgroup add operators --members operator
sudo nagios-cmd servicegroup add applications
sudo nagios-cmd template add generic-linux --options register=0,use=generic-host
sudo nagios-cmd timeperiod add maintenance --options sunday=01:00-03:00
```

### Reusable service definition files

Administrator-managed service definition templates live in `/etc/nagios4/servicedefs/*.tpl`. They can contain `{{ host_name }}` and other placeholders populated from the target host object.

Example `/etc/nagios4/servicedefs/ssh.tpl`:

```text
define service {
    use                     local-service
    host_name               {{ host_name }}
    service_description     SSH
    check_command           check_ssh
}
```

Apply the template to a custom host:

```bash
sudo nagios-cmd service add web01 --services ssh
```

## Role lifecycle controls

```yaml
anro_nagios_enabled: true
anro_nagios_install: true
anro_nagios_configure: true
anro_nagios_install_helper: true

anro_nagios_service_enabled: true
anro_nagios_service_state: started

anro_nagios_create_compat_symlink: true
anro_nagios_compat_symlink_path: /etc/nagios
```

`tasks/configure.yaml` is retained as a deprecated compatibility entry point for callers that imported it directly before v2. Apply the role normally instead. The compatibility task file is planned for removal in v3.

## Testing

The default Molecule scenario verifies the complete configured role, including:

- package and service state;
- Apache and Nagios syntax validation;
- authentication behavior;
- standard object rendering and built-in command overrides;
- custom-directory ownership and permissions;
- `nagios-cmd` host, command, and service changes;
- rollback of invalid `nagios-cmd` writes;
- refusal to modify Ansible-managed aggregate objects; and
- preservation of manual and `nagios-cmd` configuration after a role reconverge.

The `minimal` scenario verifies optional functionality can be disabled, including the helper and local Postfix support.

```bash
ansible-lint
molecule test -s default
molecule test -s minimal
```

## License

GNU General Public License v3.0. See `LICENSE`.
