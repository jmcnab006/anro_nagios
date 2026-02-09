#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nagios Configuration Manager - Improved Version
Filename: nagios_manager.py (Python module - underscores required)
Created By: Assistant
Version: 3.0

A comprehensive tool for managing Nagios configuration objects with backup,
validation, and status checking capabilities.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
import re


# Configuration Classes
@dataclass
class NagiosConfig:
    """Main configuration settings for Nagios manager - Ubuntu/Debian apt package defaults."""
    nagios_dir: Path = Path('/etc/nagios4')
    objects_dir: Path = Path('/etc/nagios4/conf.d')
    templates_dir: Path = Path('/etc/nagios4/templates')
    backup_dir: Path = Path('/var/backups/nagios4')
    nagios_binary: Path = Path('/usr/sbin/nagios4')
    nagios_config: Path = Path('/etc/nagios4/nagios.cfg')
    plugins_dir: Path = Path('/usr/lib/nagios/plugins')
    log_dir: Path = Path('/var/log/nagios4')
    var_dir: Path = Path('/var/lib/nagios4')

    def __post_init__(self):
        """Ensure all paths are Path objects."""
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, str):
                setattr(self, field_name, Path(field_value))


@dataclass
class ObjectMetadata:
    """Metadata for configuration objects."""
    name: str
    object_type: str
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
    backup_count: int = 0


class NagiosManagerError(Exception):
    """Base exception for Nagios Manager errors."""
    pass


class ConfigValidationError(NagiosManagerError):
    """Raised when configuration validation fails."""
    pass


class BackupError(NagiosManagerError):
    """Raised when backup operations fail."""
    pass


# Logging Setup
def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """Setup logging configuration."""
    logger = logging.getLogger('nagios_manager')
    logger.setLevel(getattr(logging, log_level.upper()))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Utility Functions
class FileOperations:
    """Handle file operations with error handling."""

    @staticmethod
    def read_file(filepath: Path) -> str:
        """Read file content safely."""
        try:
            return filepath.read_text(encoding='utf-8')
        except FileNotFoundError:
            raise NagiosManagerError(f"File not found: {filepath}")
        except PermissionError:
            raise NagiosManagerError(f"Permission denied: {filepath}")
        except UnicodeDecodeError:
            raise NagiosManagerError(f"Unable to decode file: {filepath}")

    @staticmethod
    def write_file(filepath: Path, content: str, backup: bool = True) -> None:
        """Write file content safely with optional backup."""
        if backup and filepath.exists():
            backup_path = filepath.with_suffix(f"{filepath.suffix}.bak")
            shutil.copy2(filepath, backup_path)

        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding='utf-8')
        except PermissionError:
            raise NagiosManagerError(f"Permission denied writing to: {filepath}")

    @staticmethod
    def find_file(filename: str, search_paths: List[Path]) -> Optional[Path]:
        """Find file in given paths."""
        for path in search_paths:
            if path.is_dir():
                for filepath in path.rglob(filename):
                    return filepath
        return None


class ConfigValidator:
    """Validate Nagios configurations."""

    def __init__(self, config: NagiosConfig):
        self.config = config
        self.logger = logging.getLogger('nagios_manager.validator')

    def validate_syntax(self) -> bool:
        """Validate Nagios configuration syntax."""
        try:
            result = subprocess.run(
                [str(self.config.nagios_binary), '-v', str(self.config.nagios_config)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                self.logger.info("Configuration syntax validation passed")
                return True
            else:
                self.logger.error(f"Configuration syntax validation failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            self.logger.error("Configuration validation timed out")
            return False
        except FileNotFoundError:
            self.logger.error(f"Nagios binary not found: {self.config.nagios_binary}")
            return False

    def validate_object(self, obj_config: str, obj_type: str) -> bool:
        """Validate individual object configuration."""
        # Basic syntax validation
        if not obj_config.strip().startswith(f'define {obj_type}'):
            return False

        if not obj_config.strip().endswith('}'):
            return False

        # Check for balanced braces
        if obj_config.count('{') != obj_config.count('}'):
            return False

        return True


class BackupManager:
    """Handle configuration backups."""

    def __init__(self, config: NagiosConfig):
        self.config = config
        self.logger = logging.getLogger('nagios_manager.backup')
        self.backup_dir = config.backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, description: str = None) -> Path:
        """Create a full configuration backup."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"nagios_backup_{timestamp}"
        if description:
            backup_name += f"_{description}"

        backup_path = self.backup_dir / backup_name

        try:
            shutil.copytree(self.config.objects_dir, backup_path)

            # Create metadata file
            metadata = {
                'timestamp': timestamp,
                'description': description or 'Automated backup',
                'source_dir': str(self.config.objects_dir),
                'backup_path': str(backup_path)
            }

            metadata_file = backup_path / 'backup_metadata.json'
            metadata_file.write_text(json.dumps(metadata, indent=2))

            self.logger.info(f"Backup created: {backup_path}")
            return backup_path

        except Exception as e:
            raise BackupError(f"Failed to create backup: {e}")

    def restore_backup(self, backup_path: Path) -> None:
        """Restore configuration from backup."""
        if not backup_path.exists():
            raise BackupError(f"Backup path does not exist: {backup_path}")

        try:
            # Create current backup before restore
            self.create_backup("pre_restore")

            # Remove current configuration
            if self.config.objects_dir.exists():
                shutil.rmtree(self.config.objects_dir)

            # Restore from backup
            shutil.copytree(backup_path, self.config.objects_dir)

            self.logger.info(f"Configuration restored from: {backup_path}")

        except Exception as e:
            raise BackupError(f"Failed to restore backup: {e}")

    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups."""
        backups = []
        for backup_dir in self.backup_dir.iterdir():
            if backup_dir.is_dir() and backup_dir.name.startswith('nagios_backup_'):
                metadata_file = backup_dir / 'backup_metadata.json'
                if metadata_file.exists():
                    try:
                        metadata = json.loads(metadata_file.read_text())
                        metadata['path'] = str(backup_dir)
                        backups.append(metadata)
                    except json.JSONDecodeError:
                        pass

        return sorted(backups, key=lambda x: x['timestamp'], reverse=True)


# Base Configuration Object
class NagiosObject(ABC):
    """Abstract base class for Nagios configuration objects."""

    def __init__(self, name: str, config: NagiosConfig, **kwargs):
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f'nagios_manager.{self.__class__.__name__.lower()}')
        self.validator = ConfigValidator(config)
        self.overwrite = kwargs.get('overwrite', False)
        self.properties = {}
        self.template_properties = []

        # Initialize object-specific properties
        self._initialize_properties(**kwargs)

        # Set file paths
        self.filename = f"{name}.{self.file_extension}"
        self.filepath = self._get_filepath()

        # Load existing configuration if available
        if self.filepath and self.filepath.exists():
            self._load_existing_config()

    @property
    @abstractmethod
    def object_type(self) -> str:
        """Return the Nagios object type (host, service, etc.)."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension for this object type."""
        pass

    @property
    @abstractmethod
    def base_directory(self) -> Path:
        """Return the base directory for this object type."""
        pass

    @abstractmethod
    def _initialize_properties(self, **kwargs) -> None:
        """Initialize object-specific properties."""
        pass

    def _get_filepath(self) -> Path:
        """Get the full file path for this object."""
        search_paths = [self.base_directory]
        existing_path = FileOperations.find_file(self.filename, search_paths)

        if existing_path:
            return existing_path
        else:
            return self.base_directory / self.filename

    def _load_existing_config(self) -> None:
        """Load existing configuration from file."""
        try:
            content = FileOperations.read_file(self.filepath)
            self.properties.update(self._parse_config(content))
            self.logger.debug(f"Loaded existing configuration for {self.name}")
        except NagiosManagerError as e:
            self.logger.error(f"Failed to load existing config: {e}")

    def _parse_config(self, content: str) -> Dict[str, str]:
        """Parse Nagios configuration content."""
        properties = {}
        lines = content.split('\n')

        # Remove define line, closing brace, and empty lines
        lines = [line.strip() for line in lines
                 if line.strip() and
                 not line.strip().startswith(f'define {self.object_type}') and
                 line.strip() != '}']

        for line in lines:
            if line.startswith('#'):
                continue

            parts = line.split(None, 1)
            if len(parts) == 2:
                key, value = parts
                properties[key] = value

        return properties

    def set_property(self, key: str, value: str) -> None:
        """Set a property value."""
        self.properties[key] = value
        self.logger.debug(f"Set property {key}={value} for {self.name}")

    def get_property(self, key: str) -> Optional[str]:
        """Get a property value."""
        return self.properties.get(key)

    def generate_config(self) -> str:
        """Generate the Nagios configuration string."""
        lines = [f"define {self.object_type} {{"]

        # Add properties in a consistent order
        for prop in self.template_properties:
            if prop in self.properties and self.properties[prop]:
                lines.append(f"    {prop:<25} {self.properties[prop]}")

        # Add any additional properties not in template
        for key, value in self.properties.items():
            if key not in self.template_properties and value:
                lines.append(f"    {key:<25} {value}")

        lines.append("}")
        return '\n'.join(lines)

    def save(self, validate: bool = True) -> bool:
        """Save the configuration to file."""
        config_content = self.generate_config()

        if validate and not self.validator.validate_object(config_content, self.object_type):
            raise ConfigValidationError(f"Configuration validation failed for {self.name}")

        if self.filepath.exists() and not self.overwrite:
            self.logger.warning(f"File exists and overwrite is False: {self.filepath}")
            return False

        try:
            FileOperations.write_file(self.filepath, config_content)
            self.logger.info(f"Saved configuration for {self.name} to {self.filepath}")
            return True
        except NagiosManagerError as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False

    def delete(self) -> bool:
        """Delete the configuration file."""
        if not self.filepath.exists():
            self.logger.warning(f"Configuration file does not exist: {self.filepath}")
            return False

        if not self.overwrite:
            response = input(f"Delete {self.filepath}? [y/N]: ").lower()
            if response != 'y':
                return False

        try:
            self.filepath.unlink()
            self.logger.info(f"Deleted configuration file: {self.filepath}")
            return True
        except OSError as e:
            self.logger.error(f"Failed to delete file: {e}")
            return False

    def display(self) -> str:
        """Display the current configuration."""
        if self.filepath.exists():
            return FileOperations.read_file(self.filepath)
        else:
            return self.generate_config()


# Concrete Object Classes
class NagiosHost(NagiosObject):
    """Nagios Host configuration object."""

    object_type = "host"
    file_extension = "cfg"

    @property
    def base_directory(self) -> Path:
        return self.config.objects_dir / "hosts"

    def _initialize_properties(self, **kwargs) -> None:
        self.template_properties = [
            'use', 'host_name', 'alias', 'display_name', 'address', 'parents',
            'hostgroups', 'check_command', 'initial_state', 'max_check_attempts',
            'check_interval', 'retry_interval', 'active_checks_enabled',
            'passive_checks_enabled', 'check_period', 'contacts', 'contact_groups',
            'notification_interval', 'notification_period', 'notification_options',
            'notifications_enabled'
        ]

        # Set default values
        self.properties = {
            'use': 'generic-host',
            'host_name': self.name,
            'alias': self.name,
            'address': kwargs.get('address', '127.0.0.1')
        }

        # Apply any additional properties from kwargs
        for key, value in kwargs.items():
            if key in self.template_properties:
                self.properties[key] = str(value)


class NagiosService(NagiosObject):
    """Nagios Service configuration object."""

    object_type = "service"
    file_extension = "cfg"

    @property
    def base_directory(self) -> Path:
        return self.config.objects_dir / "services"

    def _initialize_properties(self, **kwargs) -> None:
        self.template_properties = [
            'use', 'host_name', 'hostgroup_name', 'service_description',
            'display_name', 'check_command', 'initial_state', 'max_check_attempts',
            'check_interval', 'retry_interval', 'active_checks_enabled',
            'passive_checks_enabled', 'check_period', 'contacts', 'contact_groups',
            'notification_interval', 'notification_period', 'notification_options',
            'notifications_enabled'
        ]

        self.properties = {
            'use': 'generic-service',
            'host_name': kwargs.get('host_name', self.name),
            'service_description': kwargs.get('service_description', self.name)
        }

        for key, value in kwargs.items():
            if key in self.template_properties:
                self.properties[key] = str(value)


class NagiosCommand(NagiosObject):
    """Nagios Command configuration object."""

    object_type = "command"
    file_extension = "cfg"

    @property
    def base_directory(self) -> Path:
        return self.config.objects_dir / "commands"

    def _initialize_properties(self, **kwargs) -> None:
        self.template_properties = ['command_name', 'command_line']

        self.properties = {
            'command_name': self.name,
            'command_line': kwargs.get('command_line', '')
        }


# Main Manager Class
class NagiosManager:
    """Main Nagios configuration manager."""

    def __init__(self, config: Optional[NagiosConfig] = None, log_level: str = 'INFO'):
        self.config = config or NagiosConfig()
        self.logger = setup_logging(log_level)
        self.validator = ConfigValidator(self.config)
        self.backup_manager = BackupManager(self.config)

        # Ensure directories exist
        self.config.objects_dir.mkdir(parents=True, exist_ok=True)
        self.config.templates_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def safe_operation(self, operation_name: str):
        """Context manager for safe configuration operations."""
        self.logger.info(f"Starting operation: {operation_name}")

        # Create backup before operation
        backup_path = self.backup_manager.create_backup(f"pre_{operation_name}")

        try:
            yield

            # Validate configuration after operation
            if not self.validator.validate_syntax():
                raise ConfigValidationError("Post-operation validation failed")

            self.logger.info(f"Operation completed successfully: {operation_name}")

        except Exception as e:
            self.logger.error(f"Operation failed: {operation_name} - {e}")

            # Restore from backup on failure
            try:
                self.backup_manager.restore_backup(backup_path)
                self.logger.info("Configuration restored from backup due to failure")
            except Exception as restore_error:
                self.logger.critical(f"Failed to restore backup: {restore_error}")

            raise

    def create_host(self, name: str, address: str, **kwargs) -> NagiosHost:
        """Create a new host configuration."""
        return NagiosHost(name, self.config, address=address, **kwargs)

    def create_service(self, name: str, **kwargs) -> NagiosService:
        """Create a new service configuration."""
        return NagiosService(name, self.config, **kwargs)

    def create_command(self, name: str, command_line: str, **kwargs) -> NagiosCommand:
        """Create a new command configuration."""
        return NagiosCommand(name, self.config, command_line=command_line, **kwargs)

    def reload_nagios(self) -> bool:
        """Reload Nagios configuration."""
        if not self.validator.validate_syntax():
            self.logger.error("Cannot reload: Configuration validation failed")
            return False

        try:
            # Try nagios4 first (Ubuntu package), then fall back to nagios
            for service_name in ['nagios4', 'nagios']:
                try:
                    result = subprocess.run(
                        ['systemctl', 'reload', service_name],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        self.logger.info(f"Nagios configuration reloaded successfully ({service_name})")
                        return True
                    else:
                        self.logger.debug(f"Failed to reload {service_name}: {result.stderr}")
                        continue

                except subprocess.CalledProcessError:
                    continue

            self.logger.error("Failed to reload Nagios with any service name")
            return False

        except subprocess.TimeoutExpired:
            self.logger.error("Nagios reload timed out")
            return False
        except FileNotFoundError:
            self.logger.error("systemctl not found")
            return False

    def list_objects(self, object_type: str) -> List[str]:
        """List all objects of a given type."""
        type_mapping = {
            'host': self.config.objects_dir / "hosts",
            'service': self.config.objects_dir / "services",
            'command': self.config.objects_dir / "commands",
            'contact': self.config.objects_dir / "contacts",
            'hostgroup': self.config.objects_dir / "hostgroups"
        }

        if object_type not in type_mapping:
            return []

        directory = type_mapping[object_type]
        if not directory.exists():
            return []

        extension = ".cfg"
        objects = []

        for filepath in directory.rglob(f"*{extension}"):
            name = filepath.name.replace(extension, '')
            objects.append(name)

        return sorted(objects)


if __name__ == "__main__":
    # Example usage
    manager = NagiosManager()

    with manager.safe_operation("create_test_host"):
        host = manager.create_host("test-server", "192.168.1.100", alias="Test Server")
        host.save()

        service = manager.create_service(
            "test-service",
            host_name="test-server",
            service_description="Test Service",
            check_command="check_http"
        )
        service.save()

    # List backups
    backups = manager.backup_manager.list_backups()
    print(f"Available backups: {len(backups)}")

    # Validate and reload
    if manager.validator.validate_syntax():
        manager.reload_nagios()