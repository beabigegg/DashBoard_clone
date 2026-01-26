## ADDED Requirements

### Requirement: Standard Python package layout

The system SHALL use src layout for Python package structure.

#### Scenario: Package is importable after installation
- **WHEN** `pip install -e .` is executed in the project root
- **THEN** `import mes_dashboard` succeeds
- **AND** `from mes_dashboard.app import create_app` succeeds

#### Scenario: No sys.path manipulation required
- **WHEN** any module within the package imports another module
- **THEN** standard relative or absolute imports are used
- **AND** no `sys.path.insert` or similar hacks are present

### Requirement: Package directory structure

The system SHALL organize code in the following structure:

```
src/mes_dashboard/
├── __init__.py
├── app.py           # create_app factory
├── config/
│   ├── __init__.py
│   ├── settings.py  # Config classes
│   ├── database.py  # DB connection settings
│   ├── tables.py    # Table metadata
│   └── workcenter_groups.py
├── core/
│   ├── __init__.py
│   ├── database.py  # Engine, get_db
│   ├── cache.py     # Cache abstraction
│   └── utils.py
├── services/
│   ├── __init__.py
│   └── *.py         # Business logic services
├── routes/
│   ├── __init__.py
│   └── *.py         # Flask blueprints
└── templates/
    └── *.html
```

#### Scenario: Config modules are importable
- **WHEN** importing `from mes_dashboard.config.settings import Config`
- **THEN** the Config class is available

#### Scenario: Services can import from core
- **WHEN** a service module imports `from mes_dashboard.core.database import get_db`
- **THEN** the import succeeds without errors

### Requirement: pyproject.toml configuration

The system SHALL provide a `pyproject.toml` file for package metadata and dependencies.

#### Scenario: Package metadata is defined
- **WHEN** `pyproject.toml` is read
- **THEN** package name is `mes-dashboard`
- **AND** Python version requirement is specified (>=3.9)
- **AND** all dependencies are listed

#### Scenario: Editable install works
- **WHEN** `pip install -e .` is executed
- **THEN** the package is installed in editable mode
- **AND** changes to source files are immediately reflected
