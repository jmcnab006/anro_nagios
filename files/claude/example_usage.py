#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nagios Manager Usage Examples
Version: 3.0

This script demonstrates how to use the improved Nagios Manager
for various configuration management tasks.
"""

import sys
import time
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from nagios_manager import (
        NagiosManager, NagiosConfig, NagiosManagerError,
        ConfigValidationError, BackupError
    )
except ImportError:
    print("Error: nagios_manager module not found. Please ensure it's installed.")
    sys.exit(1)


def example_basic_usage():
    """Basic usage example with default configuration."""
    print("=== Basic Usage Example ===")

    # Initialize manager with default configuration
    manager = NagiosManager(log_level='INFO')

    try:
        # Create a backup before making changes
        backup_path = manager.backup_manager.create_backup("example_basic")
        print(f"Created backup: {backup_path}")

        # Create a simple host
        with manager.safe_operation("create_web_server"):
            host = manager.create_host(
                name="web-server-01",
                address="192.168.1.100",
                alias="Production Web Server",
                overwrite=True
            )

            # Set additional properties
            host.set_property('parents', 'core-switch')
            host.set_property('hostgroups', 'web-servers')
            host.set_property('check_command', 'check-host-alive')
            host.set_property('max_check_attempts', '3')
            host.set_property('notification_interval', '60')

            # Save the host configuration
            if host.save():
                print("Host created successfully")
                print(f"Configuration saved to: {host.filepath}")
            else:
                print("Failed to save host")
                return False

        # Create services for the host
        with manager.safe_operation("create_web_services"):
            # HTTP service
            http_service = manager.create_service(
                name="http-service",
                host_name="web-server-01",
                service_description="HTTP Service",
                check_command="check_http",
                overwrite=True
            )

            # HTTPS service
            https_service = manager.create_service(
                name="https-service",
                host_name="web-server-01",
                service_description="HTTPS Service",
                check_command="check_https",
                overwrite=True
            )

            # SSH service
            ssh_service = manager.create_service(
                name="ssh-service",
                host_name="web-server-01",
                service_description="SSH Service",
                check_command="check_ssh",
                overwrite=True
            )

            # Save all services
            services = [http_service, https_service, ssh_service]
            for service in services:
                if service.save():
                    print(f"Service '{service.get_property('service_description')}' created")
                else:
                    print(f"Failed to create service: {service.name}")

        # Validate configuration
        if manager.validator.validate_syntax():
            print("Configuration validation passed")

            # Reload Nagios (commented out for safety)
            # if manager.reload_nagios():
            #     print("Nagios configuration reloaded")
        else:
            print("Configuration validation failed")

    except (NagiosManagerError, ConfigValidationError) as e:
        print(f"Error: {e}")
        return False

    return True


def example_custom_configuration():
    """Example with custom configuration paths."""
    print("\n=== Custom Configuration Example ===")

    # Custom configuration for a different setup
    custom_config = NagiosConfig(
        nagios_dir=Path('/opt/nagios'),
        objects_dir=Path('/opt/nagios/conf.d'),
        templates_dir=Path('/opt/nagios/templates'),
        backup_dir=Path('/opt/nagios/backups')
    )

    manager = NagiosManager(custom_config, log_level='DEBUG')

    try:
        # Create a database server host
        with manager.safe_operation("create_db_server"):
            db_host = manager.create_host(
                name="db-server-01",
                address="192.168.1.200",
                alias="Primary Database Server"
            )

            # Configure database-specific properties
            db_host.set_property('parents', 'core-switch')
            db_host.set_property('hostgroups', 'database-servers')
            db_host.set_property('contact_groups', 'dba-group')
            db_host.set_property('check_interval', '2')  # More frequent checks
            db_host.set_property('retry_interval', '1')
            db_host.set_property('max_check_attempts', '5')

            if db_host.save():
                print(f"Database host created: {db_host.filepath}")

        # Create database-specific services
        db_services = [
            {
                'name': 'mysql-service',
                'description': 'MySQL Database',
                'check_command': 'check_mysql'
            },
            {
                'name': 'mysql-replication',
                'description': 'MySQL Replication',
                'check_command': 'check_mysql_replication'
            },
            {
                'name': 'disk-usage',
                'description': 'Disk Usage',
                'check_command': 'check_disk!/var/lib/mysql!80!90'
            }
        ]

        for service_config in db_services:
            with manager.safe_operation(f"create_{service_config['name']}"):
                service = manager.create_service(
                    name=service_config['name'],
                    host_name="db-server-01",
                    service_description=service_config['description'],
                    check_command=service_config['check_command']
                )

                # Database services need more frequent monitoring
                service.set_property('check_interval', '2')
                service.set_property('retry_interval', '1')
                service.set_property('max_check_attempts', '3')
                service.set_property('notification_interval', '30')

                if service.save():
                    print(f"Service '{service_config['description']}' created")

    except Exception as e:
        print(f"Error in custom configuration example: {e}")
        return False

    return True


def example_command_management():
    """Example of managing custom commands."""
    print("\n=== Command Management Example ===")

    manager = NagiosManager()

    try:
        # Create custom check commands
        commands = [
            {
                'name': 'check_custom_web',
                'command_line': '/usr/local/nagios/libexec/check_http -H $HOSTADDRESS$ -p $ARG1$ -u $ARG2$'
            },
            {
                'name': 'check_database_size',
                'command_line': '/usr/local/nagios/libexec/check_mysql_query -H $HOSTADDRESS$ -u $ARG1$ -p $ARG2$ -q "SELECT COUNT(*) FROM information_schema.tables"'
            },
            {
                'name': 'check_ssl_certificate',
                'command_line': '/usr/local/nagios/libexec/check_http -H $HOSTADDRESS$ -p 443 -S -C $ARG1$'
            }
        ]

        for cmd_config in commands:
            with manager.safe_operation(f"create_command_{cmd_config['name']}"):
                command = manager.create_command(
                    name=cmd_config['name'],
                    command_line=cmd_config['command_line']
                )

                if command.save():
                    print(f"Command '{cmd_config['name']}' created")
                    print(f"  Command line: {cmd_config['command_line']}")

    except Exception as e:
        print(f"Error in command management example: {e}")
        return False

    return True


def example_backup_management():
    """Example of backup and restore operations."""
    print("\n=== Backup Management Example ===")

    manager = NagiosManager()

    try:
        # Create a manual backup
        backup_path = manager.backup_manager.create_backup("manual_example_backup")
        print(f"Manual backup created: {backup_path}")

        # List all backups
        backups = manager.backup_manager.list_backups()
        print(f"\nAvailable backups ({len(backups)}):")
        for backup in backups[:5]:  # Show latest 5
            print(f"  {backup['timestamp']} - {backup['description']}")
            print(f"    Path: {backup['path']}")

        # Simulate making some changes, then restore
        print("\nSimulating configuration changes...")
        time.sleep(1)

        # In a real scenario, you might restore like this:
        # manager.backup_manager.restore_backup(backup_path)
        # print(f"Configuration restored from: {backup_path}")

        print("Backup management example completed")

    except BackupError as e:
        print(f"Backup error: {e}")
        return False

    return True


def example_bulk_operations():
    """Example of bulk operations with error handling."""
    print("\n=== Bulk Operations Example ===")

    manager = NagiosManager()

    # Define multiple servers to create
    servers = [
        {'name': 'web-01', 'address': '192.168.1.101', 'type': 'web'},
        {'name': 'web-02', 'address': '192.168.1.102', 'type': 'web'},
        {'name': 'app-01', 'address': '192.168.1.201', 'type': 'app'},
        {'name': 'app-02', 'address': '192.168.1.202', 'type': 'app'},
        {'name': 'db-01', 'address': '192.168.1.301', 'type': 'db'},
    ]

    try:
        # Create backup before bulk operations
        backup_path = manager.backup_manager.create_backup("before_bulk_operations")

        successful_hosts = []
        failed_hosts = []

        for server in servers:
            try:
                with manager.safe_operation(f"bulk_create_{server['name']}"):
                    host = manager.create_host(
                        name=server['name'],
                        address=server['address'],
                        alias=f"{server['type'].upper()} Server {server['name']}"
                    )

                    # Set type-specific properties
                    host.set_property('hostgroups', f"{server['type']}-servers")

                    if server['type'] == 'web':
                        host.set_property('parents', 'web-switch')
                        host.set_property('check_interval', '5')
                    elif server['type'] == 'app':
                        host.set_property('parents', 'app-switch')
                        host.set_property('check_interval', '3')
                    elif server['type'] == 'db':
                        host.set_property('parents', 'db-switch')
                        host.set_property('check_interval', '2')

                    if host.save():
                        successful_hosts.append(server['name'])
                        print(f"✓ Created host: {server['name']}")
                    else:
                        failed_hosts.append(server['name'])
                        print(f"✗ Failed to save host: {server['name']}")

            except Exception as e:
                failed_hosts.append(server['name'])
                print(f"✗ Error creating host {server['name']}: {e}")

        # Summary
        print(f"\nBulk operation summary:")
        print(f"  Successful: {len(successful_hosts)} hosts")
        print(f"  Failed: {len(failed_hosts)} hosts")

        if successful_hosts:
            print(f"  Success list: {', '.join(successful_hosts)}")
        if failed_hosts:
            print(f"  Failed list: {', '.join(failed_hosts)}")

        # Validate final configuration
        if manager.validator.validate_syntax():
            print("\nFinal configuration validation: PASSED")
        else:
            print("\nFinal configuration validation: FAILED")
            return False

    except Exception as e:
        print(f"Error in bulk operations: {e}")
        return False

    return True


def example_validation_and_testing():
    """Example of configuration validation and testing."""
    print("\n=== Validation and Testing Example ===")

    manager = NagiosManager()

    try:
        # Test configuration syntax validation
        print("Testing configuration syntax validation...")

        if manager.validator.validate_syntax():
            print("✓ Current configuration syntax is valid")
        else:
            print("✗ Current configuration has syntax errors")
            return False

        # Create a test configuration with intentional issues
        print("\nTesting error detection...")

        # This would normally fail validation
        test_host = manager.create_host("test-validation", "invalid-ip-address")

        # Test individual object validation
        config_content = test_host.generate_config()
        if manager.validator.validate_object(config_content, "host"):
            print("✓ Object validation passed")
        else:
            print("✗ Object validation failed (expected for demo)")

        # Test safe operation rollback
        print("\nTesting safe operation rollback...")

        try:
            with manager.safe_operation("test_rollback"):
                # Create a host that would cause validation to fail
                problem_host = manager.create_host("problem-host", "192.168.1.999")
                problem_host.set_property('check_command', 'non-existent-command')

                if problem_host.save():
                    print("Problem host saved (will be rolled back)")

                # Force a validation error
                raise ConfigValidationError("Simulated validation failure")

        except ConfigValidationError as e:
            print(f"✓ Safe operation rollback triggered: {e}")

        print("Validation and testing example completed")

    except Exception as e:
        print(f"Error in validation example: {e}")
        return False

    return True


def main():
    """Main function to run all examples."""
    print("Nagios Manager Usage Examples")
    print("=" * 50)

    examples = [
        ("Basic Usage", example_basic_usage),
        ("Custom Configuration", example_custom_configuration),
        ("Command Management", example_command_management),
        ("Backup Management", example_backup_management),
        ("Bulk Operations", example_bulk_operations),
        ("Validation and Testing", example_validation_and_testing)
    ]

    results = []

    for name, example_func in examples:
        print(f"\nRunning {name} example...")
        try:
            success = example_func()
            results.append((name, success))
            if success:
                print(f"✓ {name} completed successfully")
            else:
                print(f"✗ {name} failed")
        except Exception as e:
            print(f"✗ {name} crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 50)
    print("EXAMPLE EXECUTION SUMMARY")
    print("=" * 50)

    successful = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status} {name}")

    print(f"\nOverall: {successful}/{total} examples completed successfully")

    if successful == total:
        print("\n🎉 All examples completed successfully!")
        print("\nNext steps:")
        print("- Review the generated configuration files")
        print("- Customize the examples for your environment")
        print("- Integrate with your existing Nagios setup")
        print("- Set up automated backups and monitoring")
    else:
        print(f"\n⚠️  {total - successful} examples had issues")
        print("- Check the error messages above")
        print("- Ensure Nagios is properly installed")
        print("- Verify file permissions")
        print("- Review configuration paths")

    return successful == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)