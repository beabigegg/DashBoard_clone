# -*- coding: utf-8 -*-
"""Database configuration for MES Dashboard.

Centralized database connection settings used by all modules.
Loads credentials from environment variables (.env file).
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv

    # Find .env file in project root
    env_path = Path(__file__).resolve().parents[3] / '.env'
    load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, rely on system environment variables

# Database connection settings from environment variables
DB_HOST = os.getenv('DB_HOST', '10.1.1.58')
DB_PORT = os.getenv('DB_PORT', '1521')
DB_SERVICE = os.getenv('DB_SERVICE', 'DWDB')
DB_USER = os.getenv('DB_USER', '')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

# Oracle Database connection config (for direct oracledb connections)
DB_CONFIG = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'dsn': f'{DB_HOST}:{DB_PORT}/{DB_SERVICE}'
}

# SQLAlchemy connection string
# Note: Password is URL-encoded to handle special characters (@:/?# etc.)
CONNECTION_STRING = (
    f"oracle+oracledb://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/?service_name={DB_SERVICE}"
)
