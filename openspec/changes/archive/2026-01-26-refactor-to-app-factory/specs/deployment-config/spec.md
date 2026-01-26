## ADDED Requirements

### Requirement: Gunicorn configuration file

The system SHALL provide a `gunicorn.conf.py` file with production-ready defaults.

#### Scenario: Default configuration for single worker
- **WHEN** gunicorn loads the config file
- **THEN** `workers` is set to 1
- **AND** `threads` is set to 4
- **AND** `worker_class` is set to `gthread`

#### Scenario: Bind address is configurable
- **WHEN** gunicorn starts
- **THEN** it binds to `0.0.0.0:8080` by default
- **AND** bind address can be overridden via environment variable

### Requirement: WSGI entry point

The system SHALL provide a WSGI-compatible entry point for gunicorn.

#### Scenario: Gunicorn can import the app
- **WHEN** gunicorn is started with `gunicorn "mes_dashboard:create_app()"`
- **THEN** the application starts successfully
- **AND** all routes are accessible

### Requirement: Development startup script

The system SHALL provide a development startup script.

#### Scenario: Run in development mode
- **WHEN** `python -m mes_dashboard` is executed
- **THEN** the Flask development server starts
- **AND** debug mode is enabled
- **AND** auto-reload is enabled

### Requirement: Production startup script

The system SHALL provide scripts for production deployment.

#### Scenario: Start with gunicorn on Linux
- **WHEN** `./scripts/start_server.sh` is executed
- **THEN** gunicorn starts with the config file settings
- **AND** logs are written to stdout

#### Scenario: Start on Windows
- **WHEN** `scripts\start_server.bat` is executed
- **THEN** the server starts using waitress (Windows-compatible WSGI server)
- **OR** gunicorn if running in WSL

### Requirement: Environment-based configuration

The system SHALL load configuration based on environment.

#### Scenario: Development environment
- **WHEN** `FLASK_ENV=development` (or not set)
- **THEN** development configuration is loaded
- **AND** `DEBUG=True`
- **AND** connection pool size is smaller (5)

#### Scenario: Production environment
- **WHEN** `FLASK_ENV=production`
- **THEN** production configuration is loaded
- **AND** `DEBUG=False`
- **AND** connection pool size can be larger

### Requirement: Cache backend abstraction

The system SHALL provide an abstract cache interface with no-op default implementation.

#### Scenario: NoOpCache is used by default
- **WHEN** cache is accessed without Redis configuration
- **THEN** `NoOpCache` backend is used
- **AND** `get()` always returns `None`
- **AND** `set()` does nothing

#### Scenario: Cache interface is extensible
- **WHEN** a `RedisCache` implementation is added in the future
- **THEN** it can implement the same `CacheBackend` interface
- **AND** switching requires only configuration change
