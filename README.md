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

## Contents

Notable contents of this repository:

1. OpenAPI\PilotApi_v1.yaml - An OpenAPI specification for an API based upon the Northwind database.
2. tests\OpenApi - Validation tests for the OpenAPI specification.

## Validating the OpenAPI Specification

The tests in `tests/OpenApi` read `OpenAPI/PilotApi_v1.yaml` directly. They do not need a running API or a database, and they do not modify the specification.

| Check | What it verifies |
| --- | --- |
| Document validity | The YAML has no duplicate keys, the document is valid OpenAPI 3.1, every `$ref` resolves, and no component is unused. |
| Schema consistency | Patterns compile, minimum and maximum values are ordered, required properties exist, and examples and defaults match their schemas. |
| Endpoint conventions | Each operation is documented and tagged. Each `/v1` operation has bearer security, the shared headers, and the standard responses. Each resource has all five CRUD operations with the expected request and response shapes. |
| DTO sample payloads | Each DTO accepts valid sample payloads and rejects payloads that break the Northwind database constraints. |

### Running the tests

Python 3.10 or later is required. Run these commands from the repository root.

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r tests/OpenApi/requirements.txt
python -m pytest tests/OpenApi
```

Windows (Command Prompt):

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r tests/OpenApi/requirements.txt
python -m pytest tests/OpenApi
```

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r tests/OpenApi/requirements.txt
python -m pytest tests/OpenApi
```

To test a different copy of the specification, set the `OPENAPI_SPEC` environment variable to its path before running `pytest`. From a consuming repository, replace `tests/OpenApi` with `shared/PilotSharedSource/tests/OpenApi`.

### Running the tests in VS Code

This repository includes a [.vscode/launch.json](./.vscode/launch.json) debug configuration named **Python: Run Pilot API v1 Tests** that runs `tests/OpenApi/test_pilot_api_v1.py` with `pytest`.

1. Install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) (which includes the `debugpy` debugger) in VS Code.
2. Create and activate a virtual environment, then install the test dependencies as shown above, so VS Code has an interpreter with `pytest` and the other required packages available.
3. Select that interpreter as the workspace's Python interpreter (`Python: Select Interpreter` from the Command Palette).
4. Open the **Run and Debug** view (`Ctrl+Shift+D`), choose **Python: Run Pilot API v1 Tests** from the configuration dropdown, and press `F5` (or click the green run arrow) to run or debug the tests, including setting breakpoints in the test code.

Alternatively, with the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) installed, use the **Testing** view (the flask icon in the Activity Bar) to discover and run the tests individually. The repository's [.vscode/settings.json](./.vscode/settings.json) already configures `pytest` as the test framework against the `tests/OpenApi` directory, so no manual `Python: Configure Tests` step is required.

### Reading the results

- `pytest` exits with `0` when the run succeeds and a non-zero code when any test fails or the specification cannot be loaded, so the command can be used as a CI step.
- The "Failures" section at the end of the output lists each failure and error, with the line of test code that raised it. Rule violations also give the specification file and line, the problem found there, and how to fix it:

  ```text
  FAILED: test_schema_is_internally_consistent[#/components/schemas/CategoriesDto]
    Test code: tests\OpenApi\test_pilot_api_v1.py:336
    OpenAPI\PilotApi_v1.yaml:1482 (#/components/schemas/CategoriesDto/required)
      Problem: categoryName is required but is not defined under properties.
      Fix: Define categoryName, or remove it from required.
  ```

- Any other exception is reported as it was raised, with the test code line, so failures caused by unexpected changes can still be traced.
