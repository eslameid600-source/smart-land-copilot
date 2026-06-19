# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 7.x     | :white_check_mark: |
| 6.x     | :white_check_mark: |
| < 6.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Smart Land Copilot, please report it responsibly:

1. **Do NOT** open a public issue for security vulnerabilities.
2. Send a detailed report to: **eslameid600@gmail.com**
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgement:** Within 48 hours
- **Initial assessment:** Within 7 days
- **Patch release:** Varies based on severity (critical: 72 hours, high: 7 days, medium: 30 days)

## Security Best Practices

- All dependencies are scanned with `bandit`, `safety`, and `pip-audit` in CI/CD.
- Docker images run as non-root users.
- Production secrets are never committed to the repository.
- Database and API credentials are managed via environment variables only.
- JWT tokens have short expiration times and are rotated regularly.
- Rate limiting is enforced via `slowapi`.

Thank you for helping keep Smart Land Copilot secure!