# anro_nagios

Ansible role for installing and managing Nagios Core on Ubuntu 20.04 and newer.

The role installs Nagios from the Ubuntu package repositories, configures a clean separation between Ansible-managed configuration and administrator-managed custom configuration, and provides the `nagios-cmd` utility for day-to-day management of hosts, services, commands, templates, contacts, and time periods.

---

# Features

* Installs Nagios Core using Ubuntu apt packages
* Supports Ubuntu 20.04+
* Uses native `nagios4` packages
* Creates a clean custom configuration hierarchy
* Separates Ansible-managed defaults from administrator-managed configuration
* Includes Nagios validation before service reload
* Provides `nagios-cmd` CLI for configuration management
* Supports bash tab completion
* Supports reusable service definition templates

---

# Installation

Example playbook:

```yaml
- hosts: nagios
  become: true

  roles:
    - role: anro_nagios
```

---

# Directory Layout

The role manages the base Nagios installation and creates the following directory structure:

```text
/etc/nagios/
├── nagios.cfg
├── objects/
│   ├── commands.cfg
│   ├── contacts.cfg
│   ├── templates.cfg
│   ├── timeperiods.cfg
│   │
│   ├── commands/
│   ├── contacts/
│   ├── templates/
│   ├── timeperiods/
│   │
│   └── hosts/
│       ├── default/
│       └── <hostgroup>/
│           ├── hostgroup.cfg
│           ├── host1.cfg
│           ├── host2.cfg
│           └── host3.cfg
│
└── servicedefs/
    ├── ssh.tpl
    ├── http.tpl
    ├── https.tpl
    └── custom.tpl
```

---

# Configuration Ownership

## Ansible Managed

The following files are owned by Ansible and should never be modified manually:

```text
/etc/nagios/objects/commands.cfg
/etc/nagios/objects/contacts.cfg
/etc/nagios/objects/templates.cfg
/etc/nagios/objects/timeperiods.cfg
/etc/nagios/nagios.cfg
```

Changes to these files should only occur through role updates.

## Administrator Managed

The following directories are managed through `nagios-cmd`:

```text
/etc/nagios/objects/commands/
/etc/nagios/objects/contacts/
/etc/nagios/objects/templates/
/etc/nagios/objects/timeperiods/
/etc/nagios/objects/hosts/
/etc/nagios/servicedefs/
```

---

# Host Layout

Hosts are grouped by hostgroup.

Example:

```text
hosts/
├── default/
│   ├── hostgroup.cfg
│   └── web01.cfg
│
├── linux/
│   ├── hostgroup.cfg
│   ├── db01.cfg
│   └── db02.cfg
│
└── network/
    ├── hostgroup.cfg
    ├── sw01.cfg
    └── fw01.cfg
```

Hosts without a specified hostgroup are automatically placed into:

```text
hosts/default/
```

---

# Service Definitions

Service definitions are reusable templates stored in:

```text
/etc/nagios/servicedefs/
```

Examples:

```text
ssh.tpl
http.tpl
https.tpl
dns.tpl
mysql.tpl
```

A service template contains one or more Nagios service definitions that can be applied to a host.

Example:

```bash
nagios-cmd service add web01 -s ssh,http,https
```

This command imports:

```text
/etc/nagios/servicedefs/ssh.tpl
/etc/nagios/servicedefs/http.tpl
/etc/nagios/servicedefs/https.tpl
```

into the host configuration.

---

# Validation

Every configuration write operation performs:

1. Write temporary file
2. Run Nagios validation
3. Replace configuration
4. Reload Nagios

Equivalent command:

```bash
nagios4 -v /etc/nagios/nagios.cfg
```

If validation fails, no configuration changes are committed.

---

# nagios-cmd

`nagios-cmd` is the administrative interface for custom Nagios configuration.

---

# Host Management

## Add Host

```bash
nagios-cmd host add web01 10.10.10.10
```

Creates:

```text
/etc/nagios/objects/hosts/default/web01.cfg
```

---

## Add Host To Hostgroup

```bash
nagios-cmd host add \
    -g linux \
    web01 \
    10.10.10.10
```

Creates:

```text
/etc/nagios/objects/hosts/linux/web01.cfg
```

---

## Add Host With Options

```bash
nagios-cmd host add \
    -g linux \
    web01 \
    10.10.10.10 \
    -o use=generic-host,retry_interval=2,max_check_attempts=5
```

---

## List Hosts

```bash
nagios-cmd host show
```

---

## Show Host

```bash
nagios-cmd host show web01
```

Displays:

```text
Host: web01
Address: 10.10.10.10
Hostgroup: linux
File: /etc/nagios/objects/hosts/linux/web01.cfg
```

---

# Hostgroup Management

## Add Hostgroup

```bash
nagios-cmd hostgroup add linux
```

Creates:

```text
/etc/nagios/objects/hosts/linux/
├── hostgroup.cfg
```

---

## Show Hostgroups

```bash
nagios-cmd hostgroup show
```

---

## Remove Hostgroup

```bash
nagios-cmd hostgroup remove linux
```

Only empty hostgroups may be removed.

---

# Service Management

## List Available Service Definitions

```bash
nagios-cmd service show
```

Example:

```text
ssh
http
https
dns
mysql
```

---

## Add Services To Host

```bash
nagios-cmd service add web01 -s ssh,http,https
```

---

## Remove Services

```bash
nagios-cmd service remove web01 -s ssh
```

---

# Command Management

## Add Command

```bash
nagios-cmd command add check_custom \
    -o command_line='/usr/lib/nagios/plugins/check_custom -H $HOSTADDRESS$'
```

Creates:

```text
/etc/nagios/objects/commands/check_custom.cfg
```

---

## Show Commands

```bash
nagios-cmd command show
```

---

## Show Specific Command

```bash
nagios-cmd command show check_custom
```

---

# Template Management

## Add Template

```bash
nagios-cmd template add generic-linux \
    -o use=generic-host,max_check_attempts=5
```

Creates:

```text
/etc/nagios/objects/templates/generic-linux.cfg
```

---

## Show Templates

```bash
nagios-cmd template show
```

---

# Contact Management

## Add Contact

```bash
nagios-cmd contact add admin \
    -o email=admin@example.com
```

---

## Show Contacts

```bash
nagios-cmd contact show
```

---

# Timeperiod Management

## Add Timeperiod

```bash
nagios-cmd timeperiod add business-hours
```

---

## Show Timeperiods

```bash
nagios-cmd timeperiod show
```

---

# Configuration Commands

## Validate Configuration

```bash
nagios-cmd config check
```

Equivalent:

```bash
nagios4 -v /etc/nagios/nagios.cfg
```

---

## Reload Nagios

```bash
nagios-cmd config reload
```

Equivalent:

```bash
systemctl reload nagios4
```

---

# Bash Completion

The role installs shell completion.

Examples:

```bash
nagios-cmd <TAB>

host
hostgroup
service
command
template
contact
timeperiod
config
```

```bash
nagios-cmd host <TAB>

add
show
remove
```

```bash
nagios-cmd service add web01 -s <TAB>

ssh
http
https
dns
mysql
```

---

# Future Features

Planned enhancements:

* Host removal
* Hostgroup-wide service assignment
* Service inheritance
* Bulk host import
* YAML import/export
* Git integration
* Configuration backups
* Contact groups
* Service groups
* Dependency management
* REST API
* Web UI integration

---

# License

MIT
