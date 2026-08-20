# Phoenix Suite Manifest Format

## Overview

Phoenix suites are self-contained packages stored in the clonepool that can be executed without installation. A suite is defined by a `.suite.json` manifest file.

---

## Suite Manifest Structure

### Basic Format

```json
{
  "name": "my-suite",
  "version": "1.0.0",
  "description": "My Phoenix suite",
  "author": "username",
  "type": "script|module|service",
  "entry": "main.py",
  "runtime": "python|node|bash|powershell",
  "dependencies": [],
  "environment": {},
  "permissions": [],
  "metadata": {}
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Unique suite identifier |
| `version` | string | ✅ | Semantic version (e.g., "1.0.0") |
| `description` | string | ❌ | Human-readable description |
| `author` | string | ❌ | Suite author/maintainer |
| `type` | string | ✅ | Suite type: `script`, `module`, `service` |
| `entry` | string | ✅ | Entry point file (relative to suite root) |
| `runtime` | string | ✅ | Runtime: `python`, `node`, `bash`, `powershell`, `binary` |
| `dependencies` | array | ❌ | List of required dependencies |
| `environment` | object | ❌ | Environment variables to set |
| `permissions` | array | ❌ | Required permissions |
| `metadata` | object | ❌ | Additional metadata |

---

## Suite Types

### 1. Script Suite

Single-file or simple multi-file scripts.

```json
{
  "name": "backup-script",
  "version": "1.0.0",
  "type": "script",
  "entry": "backup.sh",
  "runtime": "bash",
  "description": "Automated backup script"
}
```

### 2. Module Suite

Reusable code modules/libraries.

```json
{
  "name": "utils-module",
  "version": "2.1.0",
  "type": "module",
  "entry": "index.js",
  "runtime": "node",
  "exports": ["formatDate", "parseJSON", "validateEmail"]
}
```

### 3. Service Suite

Long-running services or daemons.

```json
{
  "name": "api-service",
  "version": "1.5.0",
  "type": "service",
  "entry": "server.py",
  "runtime": "python",
  "port": 8080,
  "autostart": false
}
```

---

## Runtime Specifications

### Python Runtime

```json
{
  "runtime": "python",
  "python_version": ">=3.10",
  "requirements": ["requests>=2.28.0", "flask>=2.0.0"],
  "virtual_env": true
}
```

### Node.js Runtime

```json
{
  "runtime": "node",
  "node_version": ">=18.0.0",
  "npm_dependencies": {
    "express": "^4.18.0",
    "axios": "^1.4.0"
  }
}
```

### Bash Runtime

```json
{
  "runtime": "bash",
  "shell": "bash",
  "min_version": "4.0"
}
```

### PowerShell Runtime

```json
{
  "runtime": "powershell",
  "ps_version": ">=7.0",
  "modules": ["PSReadLine", "Pester"]
}
```

---

## Dependencies

### External Dependencies

```json
{
  "dependencies": [
    {
      "name": "git",
      "type": "binary",
      "required": true
    },
    {
      "name": "docker",
      "type": "binary",
      "required": false
    }
  ]
}
```

### Suite Dependencies

```json
{
  "dependencies": [
    {
      "suite": "utils-module",
      "version": ">=2.0.0",
      "source": "clonepool"
    }
  ]
}
```

---

## Environment Variables

```json
{
  "environment": {
    "API_KEY": "${PHOENIX_API_KEY}",
    "DEBUG": "false",
    "LOG_LEVEL": "info"
  }
}
```

Variable substitution:
- `${VAR_NAME}` - Required from environment
- `${VAR_NAME:-default}` - Optional with default value

---

## Permissions

```json
{
  "permissions": [
    "network",
    "filesystem:read",
    "filesystem:write:/tmp",
    "process:spawn"
  ]
}
```

Permission types:
- `network` - Network access
- `filesystem:read` - Read filesystem
- `filesystem:write:<path>` - Write to specific path
- `process:spawn` - Spawn child processes
- `env:read` - Read environment variables
- `env:write` - Modify environment

---

## Complete Example

```json
{
  "name": "data-processor",
  "version": "1.2.3",
  "description": "Process and transform data files",
  "author": "jwl247",
  "type": "script",
  "entry": "process.py",
  "runtime": "python",
  "python_version": ">=3.10",
  "requirements": [
    "pandas>=2.0.0",
    "numpy>=1.24.0"
  ],
  "dependencies": [
    {
      "name": "python3",
      "type": "binary",
      "required": true
    }
  ],
  "environment": {
    "DATA_DIR": "${PHOENIX_DATA_DIR:-/tmp/data}",
    "OUTPUT_FORMAT": "json"
  },
  "permissions": [
    "filesystem:read",
    "filesystem:write:/tmp",
    "network"
  ],
  "metadata": {
    "category": "data-processing",
    "tags": ["etl", "transform", "pandas"],
    "license": "GPL-3.0",
    "repository": "https://github.com/jwl247/data-processor"
  }
}
```

---

## Suite Directory Structure

```
clonepool/
└── 64617461-70726f636573736f72/  # hex-encoded suite name
    ├── .suite.json                # Suite manifest
    ├── process.py                 # Entry point
    ├── utils.py                   # Additional files
    ├── config.json                # Configuration
    └── README.md                  # Documentation
```

---

## Validation Rules

1. **Name**: Must be lowercase, alphanumeric, hyphens only
2. **Version**: Must follow semantic versioning (MAJOR.MINOR.PATCH)
3. **Entry**: Must exist in suite directory
4. **Runtime**: Must be one of supported runtimes
5. **Dependencies**: Must be resolvable
6. **Permissions**: Must be explicitly declared

---

## Usage

### Create a Suite

1. Create suite directory in clonepool
2. Add `.suite.json` manifest
3. Add entry point and supporting files
4. Clone to clonepool: `clone ./my-suite`

### Run a Suite

```bash
# Run by name
usys run data-processor

# Run with arguments
usys run data-processor --input data.csv --output result.json

# Run specific version
usys run data-processor@1.2.3

# Dry run (validate without executing)
usys run data-processor --dry-run
```

### List Available Suites

```bash
# List all suites
usys list-suites

# List by type
usys list-suites --type script

# List by runtime
usys list-suites --runtime python
```

---

## Security Considerations

1. **Sandboxing**: Suites run in isolated environment
2. **Permission Model**: Explicit permission declarations required
3. **Validation**: Manifest validated before execution
4. **Audit Logging**: All suite executions logged
5. **Code Signing**: Optional signature verification

---

**Built with ❤️ by jwl247 | Phoenix DevOps LLC**