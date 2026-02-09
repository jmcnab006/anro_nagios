#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import shutil
import re
import subprocess
import sys
import glob
from pathlib import Path

# --- GLOBAL CONFIGURATION PATHS ---
NAGIOS_CONFIG_FILE = '/usr/local/nagios/etc/nagios.cfg'
NAGIOS_BIN = '/usr/local/nagios/bin/nagios'
PARENT_DIR = Path('/usr/local/nagios/etc/objects')
TPL_DIR = Path('/usr/local/nagios/servicedefs')
BACKUP_DIR = Path('/usr/local/nagios/backup')
# Files to be included in the backup tarball
BACKUP_FILES = [
    Path('/usr/local/nagios/libexec'),
    Path('/usr/local/nagios/etc')
]
NAGIOS_SERVICE_CMD = ['sudo', 'systemctl', 'restart', 'nagios']
# Directory where your management scripts are located (used for listing)
CMD_PATH = Path('/usr/local/bin/')

# --- UTILITY FUNCTIONS ---

def print_msg(msg, style="INFO"):
    """Simple message formatter for console output."""
    styles = {
        "INFO": "\033[94m",
        "ACTION": "\033[93m",
        "SUCCESS": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "PROCESS": "\033[96m",
        "CRITICAL": "\033[41m\033[97m" # Red background, White text
    }
    ENDC = "\033[0m"
    style_code = styles.get(style.upper(), styles["INFO"])
    print(f"\n{style_code}[{style.upper()}] {msg}{ENDC}\n")

def set_objproperties(obj, options):
    """Sets object attributes from a list of key=value strings."""
    if not options:
        return
    for o in options:
        try:
            k, v = o.split('=', 1)
            setattr(obj, k.strip(), v.strip())
        except ValueError:
            print_msg(f"Invalid option format: {o}. Expected key=value.", "ERROR")

def read_config_file(filepath: Path) -> str:
    """Reads a file and returns contents."""
    return filepath.read_text()

# --- NAGIOS LIFECYCLE MANAGEMENT CLASS ---

class NagiosAdmin:
    """Handles system-level Nagios operations: Check, Backup, Reload."""

    @staticmethod
    def _run_command(cmd, desc, critical=True):
        """Helper to run system commands and check return code."""
        print_msg(f"Running: {' '.join(str(x) for x in cmd)} ({desc})", "PROCESS")
        try:
            result = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            if result.returncode != 0:
                print_msg(f"{desc} FAILED!\nOutput:\n{result.stdout}", "ERROR")
                if critical:
                    raise RuntimeError(f"Critical command failed: {desc}")
            else:
                print_msg(f"{desc} successful.", "SUCCESS")
            return result
        except FileNotFoundError:
            print_msg(f"Command not found. Check if '{cmd[0]}' is installed and in PATH.", "FATAL")
            raise

    @classmethod
    def check_config(cls, config_file: Path = Path(NAGIOS_CONFIG_FILE)) -> bool:
        """Validates the Nagios configuration file."""
        cmd = [NAGIOS_BIN, '-v', str(config_file)]
        return cls._run_command(cmd, "Nagios Configuration Check", critical=False).returncode == 0

    @classmethod
    def backup_config(cls):
        """
        Creates a timestamped tar.gz backup of the Nagios configuration.
        Also cleans up old backups (replicates logic from nagios-backup).
        """
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = os.strftime('%Y%m%d-%H%M%S')
        archive_file = BACKUP_DIR / f'nagios-backup-{timestamp}.tar.gz'

        # Build the tar command
        cmd = [
                  'tar', 'czfP', str(archive_file)
              ] + [str(p) for p in BACKUP_FILES]

        cls._run_command(cmd, f"Configuration Backup to {archive_file}")

        # Cleanup logic (replicates find command from nagios-backup)
        # Note: Your original script used /var/log, but for safety,
        # this version targets the specific BACKUP_DIR for cleanup.
        print_msg("Removing backup files older than 30 days...", "PROCESS")
        for f in BACKUP_DIR.glob('nagios-backup-*.tar.gz'):
            if (Path.stat(f).st_mtime < (os.time() - (30 * 86400))):
                f.unlink()
        print_msg("Cleanup complete.", "SUCCESS")


    @classmethod
    def reload_nagios(cls):
        """
        Performs the complete lifecycle: Backup -> Check -> Reload.
        """
        print_msg("Starting Nagios Configuration Reload Process...", "START")

        # 1. Backup Configuration
        cls.backup_config()

        # 2. Check Configuration Validity
        if not cls.check_config():
            print_msg("Configuration check failed! Nagios service was NOT reloaded. Fix config errors before retrying.", "CRITICAL")
            return False

        # 3. Reload Nagios Service
        cls._run_command(NAGIOS_SERVICE_CMD, "Nagios Service Reload (systemctl)")

        print_msg("Nagios Configuration Reload Process Complete.", "END")
        return True

# --- BASE CLASS FOR NAGIOS OBJECTS ---

class NagiosConfigObject(object):
    """Base class for all Nagios configuration objects."""

    # Must be defined in subclasses
    object_type = 'base'
    extension = '.cfg'
    config_format = '\t{0:<25}{1:<20}\n' # Standard Nagios format
    path = PARENT_DIR

    def __init__(self, name, options=None, overwrite=False):
        self.name = name
        self.overwrite = overwrite
        self.data = ""
        self.filepath = None
        self.hasconfig = False

        if name:
            self.filename = f'{name}{self.extension}'
            # Search for existing file path
            self.filepath = self._find_path(self.filename, self.path)

            if self.filepath:
                self.hasconfig = True
                self._load_config()

            # If no existing config, set path for new file (assumes default location)
            else:
                self.filepath = self.path / self.filename

            # Set initial properties
            # This is key for the define block, e.g., 'host_name'
            setattr(self, self.object_type + '_name', name)
            set_objproperties(self, options)
            self._generate_data()

    def _find_path(self, name, base_path):
        """Walks the directory structure to find the file (supports sub-directories like maps)."""
        for root, _, files in os.walk(base_path):
            if name in files:
                return Path(root) / name
        return None

    def _load_config(self):
        """Generic method to parse the configuration file and set attributes."""
        if not self.filepath or not self.filepath.exists():
            return

        data = read_config_file(self.filepath)

        # Simple regex to capture key-value pairs inside the define block
        # This handles the default format but might be brittle for complex configs
        pattern = re.compile(r'^\s*(\w+)\s+([^\s].*)$', re.MULTILINE)

        for match in pattern.finditer(data):
            key = match.group(1).strip()
            value = match.group(2).strip()
            setattr(self, key, value)

    def _generate_data(self):
        """Generates the Nagios configuration block string."""
        tpl = f'''define {self.object_type}{{\n'''

        # Use an attribute specific to the object type for its name
        name_attr = f'{self.object_type}_name'
        if hasattr(self, name_attr):
            tpl += self.config_format.format(name_attr, getattr(self, name_attr))

        # Iterate over all instance attributes, filtering out internal ones
        for attr, value in self.__dict__.items():
            # Skip internal attributes and the name we already added
            if attr.startswith('_') or attr in ['name', 'overwrite', 'data', 'filepath', 'hasconfig', 'filename', name_attr]:
                continue

            # Format and add to the template
            tpl += self.config_format.format(attr, value)

        tpl += '''}'''
        self.data = tpl

    # --- PUBLIC METHODS ---

    def save(self):
        """Saves the configuration file and triggers the reload cycle."""
        if self.filepath.exists() and not self.overwrite:
            print_msg(f"[{self.name}] file exists, not writing without -f | --force: {self.filepath}", "WARNING")
        else:
            print_msg(f"[{self.name}] SAVING file {self.filepath}", "ACTION")
            # Ensure parent directories exist (crucial for 'map' logic)
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self.filepath.write_text(self.data)
            NagiosAdmin.reload_nagios()

    def display(self):
        """Displays the object's current configuration or file content."""
        if self.filepath and self.filepath.exists():
            print_msg(f"Path: {self.filepath}", "INFO")
            print(read_config_file(self.filepath))
        else:
            print_msg(f"[{self.name}] no configuration file found.", "INFO")

    def delete(self):
        """Deletes the configuration file with confirmation and triggers reload."""
        if self.filepath and self.filepath.exists():
            can_delete = self.overwrite

            if not self.overwrite:
                prompt = input(f"\n[{self.name}] Please confirm deleting {self.filepath} [y/N]: ") or "N"
                can_delete = prompt.lower() == "y"

            if can_delete:
                print_msg(f"[{self.name}] DELETING file {self.filepath}", "ACTION")

                # Check if it's a directory (for 'map' object)
                if self.filepath.is_dir():
                    try:
                        # Deletes the entire map directory
                        shutil.rmtree(self.filepath)
                        print_msg(f"Deleted directory {self.filepath}", "SUCCESS")
                    except OSError as e:
                        print_msg(f"Error: {e.filename} - {e.strerror}", "ERROR")
                else:
                    self.filepath.unlink()
                    print_msg(f"Deleted file {self.filepath}", "SUCCESS")

                NagiosAdmin.reload_nagios()
            else:
                print_msg("Deletion cancelled.", "INFO")
        else:
            print_msg(f"[{self.name}] no configuration file found to delete.", "INFO")

# --- NAGIOS CONFIGURATION OBJECTS ---

class Host(NagiosConfigObject):
    """Host object definition."""
    object_type = 'host'
    extension = '.host.cfg'
    path = PARENT_DIR / 'hosts'

    def __init__(self, name, address, mapname=None, options=None, overwrite=False):
        self.address = address
        self.use = 'generic-host'
        self.parents = mapname or 'default'
        self.hostgroups = mapname or 'default'

        # Override path if a map is specified (creates a subdirectory)
        if mapname:
            self.path = self.path / mapname

        super().__init__(name, options, overwrite)

class Services(NagiosConfigObject):
    """Services object definition (per-host)."""
    object_type = 'service'
    extension = '.service.cfg'
    path = PARENT_DIR / 'services'

    # Custom attributes for Services management
    service_options = None # for -s or service list
    variables = None # for -v variables
    remove_services = None # for -r remove list
    host_name = None # Services object needs a host_name attribute

    def __init__(self, name, services=None, options=None, variables=None, remove=None, overwrite=False):
        # 'name' here is the host name
        self.host_name = name
        self.service_options = services
        self.variables = variables
        self.remove_services = remove

        # The service config file is typically named after the host,
        # e.g., 'examplehost.service.cfg'
        super().__init__(name, options, overwrite)

    def _generate_data(self):
        """
        Custom data generation for Services to handle service_description
        (This logic is complex and assumes a template-based structure
        as implied by your nagios-service script).

        Since full template logic is extensive, this version generates a
        simple, single service for illustration, focusing on setting attributes.
        A proper implementation would parse/generate multiple services
        from templates (TPL_DIR).
        """
        tpl = f'''define service{{\n'''

        # Essential service properties
        tpl += self.config_format.format('host_name', self.host_name)
        # Check if the user specified services or if we are just updating
        if self.service_options:
            # For simplicity, we create one dummy service_description per object
            # A complete solution must handle service definition blocks for each template.
            tpl += self.config_format.format('service_description', f'CHECK_{self.service_options.split(",")[0].upper()}')
        else:
            tpl += self.config_format.format('service_description', 'generic_service')

        # Add all dynamic attributes (like use, check_command, etc.)
        for attr, value in self.__dict__.items():
            if attr.startswith('_') or attr in ['name', 'overwrite', 'data', 'filepath', 'hasconfig', 'filename', 'service_options', 'variables', 'remove_services', 'host_name']:
                continue
            tpl += self.config_format.format(attr, value)

        tpl += '''}'''
        self.data = tpl


class Hostgroup(NagiosConfigObject):
    """Hostgroup object definition."""
    object_type = 'hostgroup'
    extension = '.hostgroup.cfg'
    path = PARENT_DIR / 'hostgroups'

    def __init__(self, name, options=None, overwrite=False):
        self.alias = f'{name} Group'
        self.members = '' # Members are typically added via the Host object
        super().__init__(name, options, overwrite)

class Map(NagiosConfigObject):
    """
    Map object definition (used as a logical container/directory).
    This object is special because its primary function is to manage a directory
    structure rather than a Nagios config block, though it can contain one.
    The path for this object is the directory itself.
    """
    object_type = 'map'
    extension = '.map.cfg'
    # Maps live within the host directory structure
    path = PARENT_DIR / 'hosts'

    def __init__(self, name, options=None, overwrite=False):
        # Map objects primarily manage the directory,
        # so we set its path to the directory name
        self.filepath = self.path / name
        self.hasconfig = self.filepath.is_dir()

        super().__init__(name, options, overwrite)

    def save(self):
        """Saves the 'Map' by creating the directory structure."""
        if not self.filepath.exists():
            print_msg(f"[{self.name}] CREATING Map directory {self.filepath}", "ACTION")
            # Create the directory recursively
            self.filepath.mkdir(parents=True, exist_ok=True)

            # Since the map object also typically creates a hostgroup
            # with the same name (based on your nagios-map script),
            # we should add that functionality here for consistency.
            hg = Hostgroup(self.name, None, self.overwrite)
            if not hg.hasconfig:
                hg.save()

            NagiosAdmin.reload_nagios()
        else:
            print_msg(f"[{self.name}] Map directory already exists: {self.filepath}", "INFO")

    def display(self):
        """Displays the contents (hosts) within the map directory."""
        if self.filepath and self.filepath.is_dir():
            host_files = self.filepath.glob('*.host.cfg')
            print_msg(f"Hosts found in Map '{self.name}':", "INFO")
            hosts = [f.stem.split('.')[0] for f in host_files]
            if hosts:
                print('\n'.join(sorted(hosts)))
            else:
                print("No hosts found.")
        else:
            print_msg(f"[{self.name}] Map directory not found: {self.filepath}", "INFO")

    def delete(self):
        """Deletes the entire map directory structure (must be forced/confirmed)."""
        # Overriding the base delete method for directory removal
        if self.filepath and self.filepath.is_dir():
            if self.name.lower() == 'default':
                print_msg("Unable to delete default map.", "ERROR")
                return

            can_delete = self.overwrite
            if not self.overwrite:
                prompt = input(f"\n[{self.name}] WARNING: THIS WILL REMOVE ALL HOSTS AND SERVICES in {self.filepath}! Please confirm deleting map [y/N]: ") or "N"
                can_delete = prompt.lower() == "y"

            if can_delete:
                print_msg(f"[{self.name}] DELETING Map directory {self.filepath}", "ACTION")
                try:
                    shutil.rmtree(self.filepath)
                    print_msg(f"Deleted directory {self.filepath}", "SUCCESS")
                    # Also delete the associated hostgroup
                    Hostgroup(self.name, None, self.overwrite).delete()
                    NagiosAdmin.reload_nagios()
                except OSError as e:
                    print_msg(f"Error: {e.filename} - {e.strerror}", "ERROR")
            else:
                print_msg("Deletion cancelled.", "INFO")
        else:
            print_msg(f"[{self.name}] no map directory found to delete.", "INFO")
