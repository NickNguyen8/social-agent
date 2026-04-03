# Social Agent Project Overview

## Project Description
A Python-based multi-agent system for autonomous research, content generation, and social media management. Uses Gemini for reasoning, search grounding, and creative writing. Supports Facebook (Pages/Groups/Profiles) and LinkedIn (Profiles/Companies).

## 🏗️ Multi-Agent Architecture
1.  **Internet Research Agent**: `ResearchAgent` using Gemini Grounding + `WebFetcher`.
2.  **Social Discovery Agent**: `DynamicSourceResolver` for finding FB Pages/Groups.
3.  **Writing Agent**: `ContentGenerator` with few-shot learning and rule extraction.
4.  **Memory Agent**: `WritingMemoryDB` (SQLite) for profile-specific learning.
5.  **Publisher Agent**: `SocialAgent` dispatching to Facebook/LinkedIn APIs.

## 📂 Repository Structure
```
social-agent/
├── src/social_agent/          ← Core Package
│   ├── agent.py               ← Orchestrator (Multi-Agent Coordinator)
│   ├── cli.py                 ← Command Line Interface
│   ├── research/              ← Discovery & Information Agents
│   ├── content/               ← Writing Agent & Scenario logic
│   ├── platforms/             ← API wrappers (FB, LinkedIn, Playwright)
│   ├── storage/               ← SQLite (Memory, Review, Audit)
│   └── utils/                 ← Paths & Init logic
│
├── profiles/                  ← Target configurations (YAML)
├── topics/                    ← Research topics (YAML)
├── formats/                   ← Content structures (YAML)
├── cross_post_groups/         ← Multi-target groups (YAML)
├── config.yaml                ← Global LLM/Scheduler settings
├── .env                       ← API Keys & Secrets
└── data/                      ← SQLite Database (social_agent.db)
```

## 🚀 Key Commands
```bash
# Setup & Maintenance
social-agent validate          # Check environment & configs
social-agent token --refresh-all # Update FB tokens from .env seeds

# Research & Discovery
social-agent discover -t ai_vietnam  # Find new sources for a topic
social-agent sources -t ai_vietnam   # List discovered sources & quality

# Post Management
social-agent post --target fastdx_page # Generate & post (or queue)
social-agent preview -t fastdx_page   # Preview without posting
social-agent review                    # Manage the review queue
social-agent review --approve ID       # Approve + Learn pattern
social-agent review --reject ID --reason "..." # Reject + Extract rule

# Scheduler
social-agent run               # Start continuous auto-posting
```

## 🧠 Memory & Learning Loop
The system implements a **Three-Pillar Learning** architecture:
1.  **Research Loop**: Registry tracks source success/fail rates. Bad sources are auto-deactivated.
2.  **Writing Loop**:
    *   **Approved Samples**: Best posts are saved as few-shot examples for the LLM.
    *   **Learned Rules**: Rejection reasons are synthesized by Gemini into actionable rules (e.g., "Don't use emoji X", "Avoid tone Y").
3.  **Review Loop**: Human-in-the-loop gatekeeper provides the feedback signal for loops 1 & 2.

## 🛠️ Developer Rules
-   **Config First**: Never hardcode targets/topics. Always use `profiles/` or `topics/` folders.
-   **Branding**: Use `profile.get("brand_name")`, `website`, etc. in `generator.py`.
-   **Dedup**: Every post is hashed via SHA-256 before dispatch to prevent double-posting.
-   **LLM Model**: Use `gemini-2.0-flash` (fast, capable, handles large JSON well).
-   **Vietnamese Support**: Ensure all prompts specify Vietnamese. Stripping Markdown from FB posts is mandatory.
-   **Tokens**: Page Tokens must be exchanged to long-lived (permanent) via the `token` command.

## 📅 Roadmap & Progress
-   ✅ Modular YAML Profiles/Topics (Directory-based loading)
-   ✅ SQLite persistence for Registry, Memory, and Review Queue
-   ✅ Multi-step Discovery (Gemini Grounding + FB API)
-   ✅ Continuous Learning Loop (Few-shot samples + Rule extraction)
-   ✅ Dynamic Branding (Profile-specific URL/Hashtags/Tagline)
-   ⏳ UI Dashboard (pywebview/FastAPI)
-   ⏳ Automated AI Gatekeeper (Pre-screening rejections)
-   ⏳ Advanced LinkedIn Integration (Company polls/carousel)
-   ⏳ Enhanced Multi-Account Proxy Support

## 🔄 Git & Development Workflow
To ensure repository stability and a clean history, the following rules are mandatory:

### 1. Branching Strategy
-   **Base Branch**: All work MUST start from `develop`.
-   **Feature Branches**: Create a new branch for every task: `feature/<task-name>`.
-   **Main Branch**: Reserved for production-ready, stable releases.

### 2. Synchronization (Pull First)
Before starting any work or checking out a new branch, you MUST pull the latest changes:
```bash
git checkout develop
git pull origin develop
```

### 3. Merging Policy (GitHub Only)
-   **No Local Merges**: Never merge feature branches into `develop` or `main` locally.
-   **Pull Requests**: Push your feature branch to `origin` and open a Pull Request.
-   **Review & Merge**: Merges to `develop` and eventually to `main` are handled exclusively via the GitHub web interface.

### 4. Commits
- Use descriptive, conventional commit messages (e.g., `feat: ...`, `fix: ...`, `docs: ...`).
- Split large changes into logical, smaller commits where applicable.

---
© 2026 Social Agent Framework.
