#!/usr/bin/env python3
"""
Generate a list of accessible TABLE/VIEW objects under a specific owner (default: DWH)
and update docs/Oracle_Authorized_Objects.md.
"""

import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import oracledb


def load_env() -> None:
    """Load .env if available (best-effort)."""
    try:
        from dotenv import load_dotenv  # type: ignore

        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path)
        return
    except Exception:
        pass

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_connection():
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "1521")
    service = os.getenv("DB_SERVICE", "")
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    dsn = (
        "(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)"
        f"(HOST={host})(PORT={port})))(CONNECT_DATA=(SERVICE_NAME={service})))"
    )
    return oracledb.connect(user=user, password=password, dsn=dsn)


def main() -> int:
    owner = "DWH"
    output_path = Path("docs/Oracle_Authorized_Objects.md")
    if len(sys.argv) > 1:
        owner = sys.argv[1].strip().upper()

    load_env()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT USER FROM DUAL")
    user = cur.fetchone()[0]

    # Roles
    cur.execute("SELECT GRANTED_ROLE FROM USER_ROLE_PRIVS")
    roles = [r[0] for r in cur.fetchall()]

    # Accessible objects under owner
    cur.execute(
        """
        SELECT OBJECT_NAME, OBJECT_TYPE
        FROM ALL_OBJECTS
        WHERE OWNER = :p_owner
          AND OBJECT_TYPE IN ('TABLE', 'VIEW')
        ORDER BY OBJECT_NAME
        """,
        p_owner=owner,
    )
    objects = cur.fetchall()

    # Direct + PUBLIC grants
    cur.execute(
        """
        SELECT o.object_name, o.object_type, p.privilege,
               CASE WHEN p.grantee = 'PUBLIC' THEN 'PUBLIC' ELSE 'DIRECT' END AS source
        FROM all_tab_privs p
        JOIN all_objects o
          ON o.owner = p.table_schema
         AND o.object_name = p.table_name
        WHERE p.grantee IN (:p_user, 'PUBLIC')
          AND o.owner = :p_owner
          AND o.object_type IN ('TABLE', 'VIEW')
        """,
        p_user=user,
        p_owner=owner,
    )
    direct_rows = cur.fetchall()

    # Role grants
    role_rows = []
    for role in roles:
        cur.execute(
            """
            SELECT o.object_name, o.object_type, p.privilege, p.role AS source
            FROM role_tab_privs p
            JOIN all_objects o
              ON o.owner = p.owner
             AND o.object_name = p.table_name
            WHERE p.role = :p_role
              AND o.owner = :p_owner
              AND o.object_type IN ('TABLE', 'VIEW')
            """,
            p_role=role,
            p_owner=owner,
        )
        role_rows.extend(cur.fetchall())

    # Aggregate privileges by object
    info = {}
    for name, otype in objects:
        info[(name, otype)] = {"privs": set(), "sources": set()}

    for name, otype, priv, source in direct_rows + role_rows:
        key = (name, otype)
        if key not in info:
            info[key] = {"privs": set(), "sources": set()}
        info[key]["privs"].add(priv)
        info[key]["sources"].add(source)

    # Fill in missing privilege/source if object is visible but not in grants
    for key, data in info.items():
        if not data["privs"]:
            data["privs"].add("UNKNOWN")
        if not data["sources"]:
            data["sources"].add("SYSTEM")

    type_counts = Counter(k[1] for k in info.keys())
    source_counts = Counter()
    for data in info.values():
        for s in data["sources"]:
            if s in ("DIRECT", "PUBLIC"):
                source_counts[s] += 1
            elif s == "SYSTEM":
                source_counts["SYSTEM"] += 1
            else:
                source_counts["ROLE"] += 1

    # Render markdown
    lines = []
    lines.append("# Oracle 可使用 TABLE/VIEW 清單（DWH）")
    lines.append("")
    lines.append(f"**產生時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**使用者**: {user}")
    lines.append(f"**Schema**: {owner}")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(f"- 可使用物件總數: {len(info):,}")
    lines.append(f"- TABLE: {type_counts.get('TABLE', 0):,}")
    lines.append(f"- VIEW: {type_counts.get('VIEW', 0):,}")
    lines.append(
        "- 來源 (去重後物件數): "
        f"DIRECT {source_counts.get('DIRECT', 0):,}, "
        f"PUBLIC {source_counts.get('PUBLIC', 0):,}, "
        f"ROLE {source_counts.get('ROLE', 0):,}, "
        f"SYSTEM {source_counts.get('SYSTEM', 0):,}"
    )
    lines.append("")
    lines.append("## 物件清單")
    lines.append("")
    lines.append("| 物件 | 類型 | 權限 | 授權來源 |")
    lines.append("|------|------|------|----------|")

    for name, otype in sorted(info.keys()):
        data = info[(name, otype)]
        obj = f"{owner}.{name}"
        privs = ", ".join(sorted(data["privs"]))
        sources = ", ".join(
            sorted(
                "ROLE" if s not in ("DIRECT", "PUBLIC", "SYSTEM") else s
                for s in data["sources"]
            )
        )
        lines.append(f"| `{obj}` | {otype} | {privs} | {sources} |")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    cur.close()
    conn.close()
    print(f"Wrote {output_path} ({len(info)} objects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
