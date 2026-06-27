# GitHub Setup Guide — Push DRIFT to Public Repo

> This guide walks you through creating the DRIFT GitHub repository and pushing your code.
> You must run these commands in your terminal — I cannot log into your accounts.

---

## Step 1: Create the GitHub Repository

1. Go to https://github.com/new
2. **Repository name**: `drift`
3. **Description**: `Cognitive middleware for AI agents — consciousness, embodiment, homeostasis, intuition`
4. **Visibility**: Public
5. **Initialize**: ✅ Add a README (we'll overwrite it)
6. **Add .gitignore**: Python
7. **License**: None (we have our own dual license)
8. Click **Create repository**

Your repo will be at: `https://github.com/timeless-hayoka/drift`

---

## Step 2: Configure Git (if not already done)

```bash
git config --global user.name "Julien James"
git config --global user.email "hiimju3@icloud.com"
```

---

## Step 3: Initialize and Push

```bash
cd /home/crexs/drift

# Initialize git
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial commit: DRIFT cognitive middleware for AI agents

- 22 self-registering cognitive plugins
- IIT consciousness measurement (Φ proxy)
- Embodied cognition with body schema
- Homeostatic regulation (7 survival needs)
- Global Workspace Theory attention
- FastAPI SaaS layer
- Python SDK
- Docker deployment

Built by Julien James (timeless-hayoka)"

# Link to GitHub
git remote add origin https://github.com/timeless-hayoka/drift.git

# Push
git branch -M main
git push -u origin main
```

---

## Step 4: Enable GitHub Features

After pushing, go to your repo settings and enable:

### Issues
- Settings → General → Issues → ✅ Enable
- This lets people report bugs and request features

### Discussions
- Settings → General → Discussions → ✅ Enable
- Use for community Q&A and feature proposals

### Wiki (optional)
- Settings → General → Wikis → ✅ Enable
- For longer documentation

### GitHub Pages (for docs)
- Settings → Pages → Source: Deploy from a branch → Branch: main → /docs
- Or use a separate `gh-pages` branch

---

## Step 5: Add Repo Topics

On the main repo page, click the gear next to "About" and add:

```
ai, artificial-intelligence, cognitive-architecture, consciousness, embodiment,
homeostasis, intuition, agents, ai-agents, middleware, fastapi, python,
llm, langchain, crewai, iit, global-workspace-theory
```

---

## Step 6: Pin Important Info

Create these issues and pin them:

1. **"Welcome to DRIFT — Read this first"**
   - Link to README, docs, API reference
   - How to get started
   - How to contribute (link to CLA)

2. **"Roadmap"**
   - Q2 2026: SaaS API launch, SDK expansion
   - Q3 2026: Enterprise features, custom plugins
   - Q4 2026: Multi-agent coordination, gaming integration

3. **"Good first issues"**
   - Tag beginner-friendly tasks
   - This attracts contributors

---

## Step 7: Set Up Branch Protection

Settings → Branches → Add rule:

- **Branch name pattern**: `main`
- ✅ Require a pull request before merging
- ✅ Require approvals (1)
- ✅ Dismiss stale PR approvals when new commits are pushed
- ✅ Require status checks to pass before merging

---

## Step 8: Add Secrets (for CI/CD later)

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `PYPI_API_TOKEN` | (when you publish to PyPI) |
| `DOCKER_USERNAME` | (when you set up Docker Hub) |
| `DOCKER_PASSWORD` | (when you set up Docker Hub) |

---

## Step 9: First Release

After pushing and verifying everything works:

```bash
# Tag v0.1.0
git tag -a v0.1.0 -m "DRIFT v0.1.0 — Initial release"
git push origin v0.1.0
```

Then on GitHub:
- Go to Releases → Draft a new release
- Choose tag `v0.1.0`
- Title: `DRIFT v0.1.0 — Cognitive Middleware for AI Agents`
- Description: Copy key points from README
- Attach binaries: None (Python package)
- Publish release

---

## Step 10: Publish to PyPI (Optional, Later)

When you're ready for `pip install drift-cognition`:

```bash
# Build
python -m build

# Upload to TestPyPI first
python -m twine upload --repository testpypi dist/*

# Then real PyPI
python -m twine upload dist/*
```

Requires:
```bash
pip install build twine
```

---

## Verification Checklist

- [ ] Repo created at github.com/timeless-hayoka/drift
- [ ] Code pushed to main branch
- [ ] README renders correctly on GitHub
- [ ] LICENSE.md visible in repo root
- [ ] Topics added
- [ ] Issues enabled
- [ ] v0.1.0 release created
- [ ] Repo is public

---

*Questions? Check the main README or open an issue.*
