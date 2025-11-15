# Project Setup Guide

## Python Version
This project requires **Python 3.13+**

## Dependencies Management

We maintain two requirements files for consistency across all environments:

### 1. Production/Deployment
```bash
pip install -r requirements.txt
```
- Contains all dependencies needed to run the application
- Includes testing tools (for CI/CD pipelines)
- All versions are pinned for reproducibility

### 2. Development Environment
```bash
pip install -r requirements-dev.txt
```
- Includes everything from requirements.txt
- Adds development tools (ipython, ipdb, pre-commit, sphinx)
- Use this for local development

## Quick Start

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Upgrade pip:
```bash
pip install --upgrade pip
```

3. Install dependencies:
```bash
# For development
pip install -r requirements-dev.txt

# For production/testing only
pip install -r requirements.txt
```

## Updating Dependencies

When adding new dependencies:
1. Add production dependencies to `requirements.txt` with pinned versions
2. Add dev-only tools to `requirements-dev.txt`
3. Test installation in a clean virtual environment
4. Commit both files together

## Version Pinning Strategy

- **Production deps**: Use exact versions (==) for reproducibility
- **Flexible constraints**: Use >= only for packages that need flexibility (e.g., huggingface-hub)
- **Test regularly**: Update and test dependencies monthly

## Troubleshooting

If you encounter dependency conflicts:
1. Delete and recreate virtual environment
2. Ensure you're using Python 3.13+
3. Clear pip cache: `pip cache purge`
4. Install with: `pip install --no-cache-dir -r requirements-dev.txt`

## Docker Deployment

For containerized deployments, use:
```dockerfile
FROM python:3.13-slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

## Notes

- The old `requirements-minimal.txt` is deprecated and will be removed
- All environments (dev, test, prod) now use the same dependency versions
- CI/CD should use `requirements.txt` for consistency