# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**foremanctl** is a next-generation installer and lifecycle management tool for Foreman/Katello infrastructure. It uses Ansible playbooks to deploy Foreman ecosystem services as rootless Podman containers with comprehensive network isolation.

## Repository Structure

```
src/
├── roles/              # Ansible roles for service deployment
│   ├── postgresql/     # PostgreSQL database container
│   ├── redis/          # Redis cache container
│   ├── candlepin/      # Candlepin subscription management
│   ├── pulp/           # Pulp content management
│   ├── foreman/        # Foreman Rails application
│   ├── rootless_user/  # Rootless user environment setup
│   └── ...
├── vars/               # Variable files (database configs, network settings)
└── playbooks/          # Deployment playbooks
development/
└── playbooks/          # Development/testing playbooks
```

## Key Branches

- **master**: Stable releases
- **networks_rootless**: Network isolation + rootless Podman deployment (primary development)
- **rootless_iop**: networks_rootless + IOP (Insights-on-Prem) features
- **foremanctl_networks**: Legacy root-mode network isolation (archived)

## Technology Stack

- **Ansible**: Automation and orchestration
- **Podman**: Rootless container runtime
- **Quadlet**: Systemd-native container management
- **Netavark + pasta/slirp4netns**: Rootless networking
- **PostgreSQL**: Database (sclorg container image)
- **Redis**: Cache layer
- **Ruby on Rails**: Foreman application
- **Sinatra**: Smart Proxy services

## Network Architecture

### Network Segmentation (foremanctl_networks pattern)

Dedicated Podman bridge networks for isolation:

```
foreman-db:         PostgreSQL, Redis (backend services)
foreman-app:        Foreman, Candlepin, Pulp (application tier)
foreman-cache:      Redis/cache (if isolated)
foreman-proxy-net:  Smart proxy communication
```

**What this provides**:
- Logical network isolation between tiers
- Lateral movement prevention
- Defense in depth
- Network policy enforcement via iptables

**What this does NOT provide**:
- See "Security Model" section below

### Rootless Networking Implementation

Rootless Podman uses a fundamentally different networking stack than root Podman:

**Root Podman**:
- **CNI (Container Network Interface)** plugins
- **Real Linux kernel bridge** (e.g., `cni-podman1`)
- Native kernel routing with iptables rules
- All containers share host network namespace (different interfaces)
- **"Leaky localhost"**: Containers on same bridge may reach each other's localhost-bound services

**Rootless Podman**:
- **Netavark** network manager + **pasta/slirp4netns** user-mode networking
- **No kernel bridge** - user-space network emulation
- Containers run in completely separate user namespaces
- Network traffic proxied through user-space processes
- **Strict loopback isolation**: `localhost` is private to each container

### PostgreSQL Networking Differences

The same PostgreSQL container image behaves differently in root vs rootless mode:

**Why `listen_addresses='localhost'` works differently**:

| Aspect | Root Podman | Rootless Podman |
|--------|-------------|-----------------|
| **Network implementation** | Kernel CNI bridge | User-mode pasta/slirp4netns |
| **Loopback isolation** | Shared/leaky across bridge | Strictly isolated per container |
| **Bridge-to-localhost** | Sometimes works (kernel allows) | Never works (user-space proxy) |
| **`listen_addresses='localhost'`** | May accept bridge connections | Only accepts same-container connections |

**Container network interfaces in rootless mode**:
```
Container's perspective:
  lo:       127.0.0.1 (loopback - isolated to this container only)
  eth0:     10.89.0.5 (virtual interface via pasta/slirp4netns)
```

The loopback interface (`lo`) is **strictly isolated** within the container's user namespace. Other containers cannot reach it, even on the same Podman-managed bridge.

**Solution for rootless PostgreSQL on bridge networks**:
1. `POSTGRESQL_LISTEN_ADDRESSES: "*"` - Bind to all interfaces (including eth0)
2. **pg_hba.conf configuration** - Allow connections from bridge network IPs:
   ```
   host all all 0.0.0.0/0 scram-sha-256
   ```

This makes PostgreSQL listen on the bridge interface (`eth0`) so other containers can connect via the bridge network.

## Security Model

### Application-Level Isolation (foremanctl_networks)

**Network segmentation provides**:
- Defense in depth
- Reduces attack surface
- Enforces architectural boundaries
- Required for compliance/best practices

**But it's "soft" isolation**:
- Enforced by **iptables rules** (which root can modify)
- Enforced by **CNI plugins** (which root can bypass)
- Not enforced by **user namespace boundaries**

### Security-Level Isolation (Rootless Mode)

**User namespace isolation**:
```
Container "root" (UID 0) → Host UID 100000 (foremanctl's subuid range)
Container user 1000     → Host UID 101000
```

**Protection boundaries**:

| Attack Scenario | Root Mode | Rootless Mode |
|----------------|-----------|---------------|
| **Compromised web app** | ✅ Can't reach DB (network isolation) | ✅ Can't reach DB |
| **Container escape** | ❌ Attacker = host root (game over) | ✅ Attacker = foremanctl user (contained) |
| **Lateral movement** | ✅ Blocked by iptables | ✅ Blocked by iptables + user namespace |
| **Disable iptables** | ❌ Root can flush rules | ✅ foremanctl can't (no CAP_NET_ADMIN) |
| **Network policy bypass** | ❌ Root can modify CNI | ✅ foremanctl can't (no privileges) |
| **Kernel exploit** | ❌ Affects all containers = root | ✅ Gets foremanctl, needs 2nd exploit for root |

**Key insight**: Network isolation in root mode is **policy-based** (enforced by iptables rules that root can change). In rootless mode, it's **capability-based** (enforced by kernel user namespace boundaries that processes can't bypass).

### Combined Protection Model

**Real protection requires BOTH**:
1. **Network segmentation** (foremanctl_networks pattern)
   - Application-level isolation
   - Enforces architecture
   - Reduces attack surface

2. **Rootless deployment** (user namespace isolation)
   - Security-level isolation
   - Container escape ≠ root compromise
   - Makes network isolation enforcement harder to bypass

**Analogy**:
- **Root mode**: Locked doors between rooms, but every lock uses the same master key (root privileges)
- **Rootless mode**: Different locks AND different owners for each room (privilege separation)

## Development Workflow

### Git Workflow

**Remotes**:
- `origin`: https://github.com/theforeman/foremanctl.git (upstream, read-only)
- `pablomh`: git@github.com:pablomh/foremanctl.git (personal fork, SSH)

**Workflow**:
1. Always push to `pablomh` remote (personal fork)
2. Use `--force-with-lease` when rewriting history
3. Squash commits for clean PR diffs
4. Create PRs from fork to upstream

### Common Commands

```bash
# Run deployment
cd development/playbooks/deploy-dev
ansible-playbook deploy-dev.yaml

# Check rootless user setup
ansible-playbook -i inventory rootless-user-setup.yaml

# Run tests
cd development/playbooks/test
ansible-playbook test-network-isolation.yaml

# Check CI status
gh run list --repo pablomh/foremanctl --branch networks_rootless --limit 5
gh run view <run-id> --log-failed
```

### Ansible Conventions

- Role variables must use role name as prefix (ansible-lint rule)
- Internal variables (register/set_fact) use leading underscore: `_internal_var`
- Use `is successful` and `is failed`, not deprecated `is succeeded`
- Never commit secrets (postgresql passwords, manifest files)

## Key Variables

**Database connectivity** (src/vars/database_iop.yml):
```yaml
iop_database_host: "/var/run/postgresql"  # Unix socket path
```

**PostgreSQL networking** (src/roles/postgresql/defaults/main.yml):
```yaml
postgresql_network: foreman-db            # Bridge network
postgresql_socket_dir: /var/lib/foremanctl/postgresql-socket
```

**Rootless user** (src/roles/rootless_user/defaults/main.yaml):
```yaml
rootless_user_name: foremanctl
rootless_user_subuid_start: 100000
rootless_user_subuid_count: 65536
```

## Testing

### CI Pipeline

- **ansible-lint**: Code quality checks
- **tests**: Matrix of OS/config combinations
- **devel-tests**: Development environment deployment
- **upgrade**: Upgrade path testing

### Local Testing

```bash
# Syntax check
ansible-playbook --syntax-check <playbook>.yaml

# Dry run
ansible-playbook --check <playbook>.yaml

# Targeted deployment
ansible-playbook deploy-dev.yaml --tags postgresql,redis
```

## Troubleshooting

### PostgreSQL Connection Refused on Bridge Network

**Symptom**: Services can't connect to PostgreSQL on bridge network

**Root cause**: PostgreSQL default `listen_addresses='localhost'` + pg_hba.conf only allows localhost

**Solution**:
1. Set `POSTGRESQL_LISTEN_ADDRESSES: "*"` in container env
2. Configure pg_hba.conf to allow bridge network connections:
   ```bash
   podman exec postgresql bash -c \
     "echo 'host all all 0.0.0.0/0 scram-sha-256' >> /var/lib/pgsql/data/pg_hba.conf"
   ```
3. Restart PostgreSQL container

### Rootless Socket Permission Issues

**Symptom**: sclorg PostgreSQL entrypoint changes host bind-mounted directory permissions

**Root cause**: Entrypoint runs `chown postgres:postgres /var/run/postgresql && chmod 0700`

In rootless mode, this changes the HOST directory to uid 100026 mode 0700, blocking access.

**Solution**: Mount socket directory to `/tmp/socket` instead of `/var/run/postgresql`, configure PostgreSQL:
```yaml
unix_socket_directories = '/var/run/postgresql,/tmp/socket'
unix_socket_permissions = 0777
```

### Container Can't Reach Another Container on Same Network

**Check**:
1. Both containers on same Podman network: `podman network inspect <network>`
2. PostgreSQL listening on all interfaces: `POSTGRESQL_LISTEN_ADDRESSES: "*"`
3. Firewall rules (if any): `iptables -L -n`
4. Service using correct hostname (container name) or IP

**Rootless-specific**: Ensure pasta/slirp4netns is running correctly:
```bash
ps aux | grep pasta
loginctl show-user foremanctl | grep Linger
```

## References

- [Podman Rootless Networking](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
- [User Namespaces](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)
- [sclorg PostgreSQL Container](https://github.com/sclorg/postgresql-container)
- [Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
