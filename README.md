# PilotSharedSource

`PilotSharedSource` contains reusable shared assets (scripts, templates, and utility content) that are consumed by other Pilot repositories through a Git submodule.

## Repository Purpose

- Centralize shared source used by multiple Pilot repositories.
- Reduce duplication and drift between repositories.
- Version shared content independently and consume pinned revisions from each dependent repository.

## Shared Source Best Practices

1. Keep content modular and reusable across repositories.
2. Prefer backward-compatible changes; document breaking changes in commit messages and PR descriptions.
3. Avoid repository-specific assumptions (paths, branch names, environment variables) unless clearly parameterized.
4. Keep scripts idempotent where possible so repeat executions are safe.
5. Include usage examples for any new script or shared asset.

## Language and Content Policy

- **Do not add high-level application languages** (for example: C#, Java) to this repository.
- **Allowed scripting languages** include Python and PowerShell when they provide automation value across repositories.
- Every script must include clear documentation covering:
  - Purpose
  - Required inputs/arguments
  - Required environment/dependencies
  - Example usage
  - Expected outputs and failure behavior

## Using This Repository as a Submodule

The recommended approach in a consuming repository is to place this submodule under a shared path such as `shared/PilotSharedSource`.

### Add the submodule

```bash
git submodule add https://github.com/MikeLooper/PilotSharedSource.git shared/PilotSharedSource
git submodule update --init --recursive
```

### Clone a repository that already contains the submodule

```bash
git clone --recurse-submodules <consumer-repo-url>
```

If already cloned without submodules:

```bash
git submodule update --init --recursive
```

### Pull latest submodule changes in a consuming repository

```bash
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
git commit -m "Update PilotSharedSource submodule"
```

### CI/build considerations for consuming repositories

- Ensure CI checks out submodules (`submodules: recursive` or equivalent).
- Pin submodule revisions through regular commits in the consuming repository for predictable builds.
- Do not make local edits inside the submodule directory in consuming repositories; contribute changes to this repository directly.
