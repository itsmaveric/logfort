# Admin Authentication Setup

## Overview
The monitor admin endpoints are now protected with basic authentication to prevent unauthorized access to filesystem monitoring configuration.

## Environment Variable
Set the `ADMIN_PASSWORD` environment variable to configure the admin password:

```bash
export ADMIN_PASSWORD="your-secure-password-here"
```

**Default Password**: `admin123` (development only - change in production!)

## Protected Endpoints
The following endpoints now require admin authentication:
- `/monitor` - Monitor status and configuration
- `/monitor/settings` - Configure monitoring settings  
- `/monitor/start` - Start monitoring service
- `/monitor/stop` - Stop monitoring service
- `/monitor/folders/<id>/delete` - Delete monitored folders

## Path Security
Monitor folder paths are restricted to:
- `/tmp/*` - Temporary directory paths only
- Current working directory and subdirectories

This prevents unauthorized access to sensitive system directories.

## Usage
1. Navigate to `/admin/login` or click "Admin Login" in the navigation
2. Enter the admin password
3. Access monitor endpoints as authenticated admin
4. Use "Logout" from the admin dropdown when finished

## Security Features
- Session-based authentication
- Path validation to prevent sensitive directory access
- Clear visual indicators for authentication status
- Automatic redirect to login for unauthorized access attempts