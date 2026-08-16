# Contributing to Windows Power Explorer

Thank you for your interest in contributing to Windows Power Explorer! To keep our workflow organized and professional, we follow strict naming conventions for Issues, Branches, and Pull Requests. 

We loosely follow the [Conventional Commits](https://www.conventionalcommits.org/) specification to ensure readability and easy changelog generation.

---

## 📌 Issue Naming Conventions

All issues should have a clear, descriptive title that instantly explains the problem or request.

**Format:**
`[Type]: Short, imperative description of the issue`

**Allowed Types:**
* `[Bug]` - Something is not working as expected (e.g., crashes, incorrect Win32 API returns).
* `[Feature]` - A request for new functionality or an enhancement to an existing feature.
* `[Docs]` - Missing, incorrect, or outdated documentation in the vault.
* `[Refactor]` - Code improvements that do not change functionality.
* `[Task]` - Internal chores, CI/CD updates, or project management tasks.

**Examples:**
* ✅ `[Bug]: Access violation when querying hidden power scheme`
* ✅ `[Feature]: Add export support for custom power plans`
* ✅ `[Docs]: Update Win32 API reference for Windows 11 22H2`
* ❌ `Issue with power plans` *(Too vague, missing type)*
* ❌ `[Feature] please add a button to export` *(Not imperative, inconsistent bracket spacing)*

---

## 🌿 Branch Naming Conventions

When creating a branch to work on an issue, use a structured naming convention that references the issue number.

**Format:**
`<type>/<issue-number>-<short-description>`

**Allowed Types:**
* `feature/` or `feat/`
* `bugfix/` or `fix/`
* `docs/`
* `chore/`

**Examples:**
* ✅ `fix/42-access-violation-hidden-scheme`
* ✅ `feat/88-export-custom-power-plans`
* ❌ `my-new-feature`
* ❌ `fix-bug`

---

## 🚀 Pull Request Naming Conventions

Pull Request titles should clearly describe what the PR accomplishes. If the PR resolves a specific issue, the title format should be identical to the issue title, but without the brackets (standard Conventional Commits).

**Format:**
`<type>(<optional scope>): <description>`

**Allowed Types:**
* `feat`: A new feature
* `fix`: A bug fix
* `docs`: Documentation only changes
* `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc.)
* `refactor`: A code change that neither fixes a bug nor adds a feature
* `perf`: A code change that improves performance
* `test`: Adding missing tests or correcting existing tests
* `chore`: Changes to the build process or auxiliary tools and libraries

**Scopes (Optional but recommended):**
Scopes represent the area of the codebase the PR touches (e.g., `cli`, `gui`, `win32`, `core`, `ci`).

**Examples:**
* ✅ `fix(win32): resolve access violation on hidden scheme query`
* ✅ `feat(gui): add export button to active power plan overlay`
* ✅ `docs(vault): update threat model ADR`
* ❌ `Fixed the bug` *(Too vague, missing type)*
* ❌ `Update main.py` *(Does not describe the actual change)*

### PR Body Checklist
Ensure your PR description fills out the default template located at `.github/PULL_REQUEST_TEMPLATE.md` entirely, explicitly referencing the issue it closes (e.g., `Fixes #42`).
