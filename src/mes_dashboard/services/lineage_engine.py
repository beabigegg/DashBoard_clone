# -*- coding: utf-8 -*-
"""Unified LOT lineage resolution helpers."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.lineage_engine")

ORACLE_IN_BATCH_SIZE = 1000
MAX_SPLIT_DEPTH = 20


def _normalize_list(values: List[str]) -> List[str]:
    """Normalize string list while preserving input order."""
    if not values:
        return []
    seen = set()
    normalized: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _safe_str(value: Any) -> Optional[str]:
    """Convert value to non-empty string if possible."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value else None


class LineageEngine:
    """Unified split/merge genealogy resolver."""

    @staticmethod
    def resolve_split_ancestors(
        container_ids: List[str],
        initial_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Resolve split lineage with CONNECT BY NOCYCLE.

        Returns:
            {
                "child_to_parent": {child_cid: parent_cid},
                "cid_to_name": {cid: container_name},
            }
        """
        normalized_cids = _normalize_list(container_ids)
        child_to_parent: Dict[str, str] = {}
        cid_to_name: Dict[str, str] = {
            cid: name
            for cid, name in (initial_names or {}).items()
            if _safe_str(cid) and _safe_str(name)
        }

        if not normalized_cids:
            return {"child_to_parent": child_to_parent, "cid_to_name": cid_to_name}

        for i in range(0, len(normalized_cids), ORACLE_IN_BATCH_SIZE):
            batch = normalized_cids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("c.CONTAINERID", batch)

            sql = SQLLoader.load_with_params(
                "lineage/split_ancestors",
                CID_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params)
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                cid = _safe_str(row.get("CONTAINERID"))
                if not cid:
                    continue

                name = _safe_str(row.get("CONTAINERNAME"))
                if name:
                    cid_to_name[cid] = name

                depth_raw = row.get("SPLIT_DEPTH")
                depth = int(depth_raw) if depth_raw is not None else 0
                if depth > MAX_SPLIT_DEPTH:
                    continue

                parent = _safe_str(row.get("SPLITFROMID"))
                if parent and parent != cid:
                    child_to_parent.setdefault(cid, parent)

        logger.info(
            "Split ancestor resolution completed: seed=%s, edges=%s, names=%s",
            len(normalized_cids),
            len(child_to_parent),
            len(cid_to_name),
        )
        return {"child_to_parent": child_to_parent, "cid_to_name": cid_to_name}

    @staticmethod
    def resolve_merge_sources(
        container_names: List[str],
    ) -> Dict[str, List[str]]:
        """Resolve merge source lots from FINISHEDNAME."""
        normalized_names = _normalize_list(container_names)
        if not normalized_names:
            return {}

        result: Dict[str, Set[str]] = defaultdict(set)

        for i in range(0, len(normalized_names), ORACLE_IN_BATCH_SIZE):
            batch = normalized_names[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("ca.FINISHEDNAME", batch)

            sql = SQLLoader.load_with_params(
                "lineage/merge_sources",
                FINISHED_NAME_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params)
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                finished_name = _safe_str(row.get("FINISHEDNAME"))
                source_cid = _safe_str(row.get("SOURCE_CID"))
                if not finished_name or not source_cid:
                    continue
                result[finished_name].add(source_cid)

        mapped = {k: sorted(v) for k, v in result.items()}
        logger.info(
            "Merge source resolution completed: finished_names=%s, mapped=%s",
            len(normalized_names),
            len(mapped),
        )
        return mapped

    @staticmethod
    def resolve_full_genealogy(
        container_ids: List[str],
        initial_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Set[str]]:
        """Resolve combined split + merge genealogy graph.

        Returns:
            {seed_cid: set(ancestor_cids)}
        """
        seed_cids = _normalize_list(container_ids)
        if not seed_cids:
            return {}

        split_result = LineageEngine.resolve_split_ancestors(seed_cids, initial_names)
        child_to_parent = split_result["child_to_parent"]
        cid_to_name = split_result["cid_to_name"]

        ancestors: Dict[str, Set[str]] = {}
        for seed in seed_cids:
            visited: Set[str] = set()
            current = seed
            depth = 0
            while current in child_to_parent and depth < MAX_SPLIT_DEPTH:
                depth += 1
                parent = child_to_parent[current]
                if parent in visited:
                    break
                visited.add(parent)
                current = parent
            ancestors[seed] = visited

        all_names = [name for name in cid_to_name.values() if _safe_str(name)]
        merge_source_map = LineageEngine.resolve_merge_sources(all_names)
        if not merge_source_map:
            return ancestors

        merge_source_cids_all: Set[str] = set()
        for seed in seed_cids:
            self_and_ancestors = ancestors[seed] | {seed}
            for cid in list(self_and_ancestors):
                name = cid_to_name.get(cid)
                if not name:
                    continue
                for source_cid in merge_source_map.get(name, []):
                    if source_cid == cid or source_cid in self_and_ancestors:
                        continue
                    ancestors[seed].add(source_cid)
                    merge_source_cids_all.add(source_cid)

        seen = set(seed_cids) | set(child_to_parent.keys()) | set(child_to_parent.values())
        new_merge_cids = list(merge_source_cids_all - seen)
        if not new_merge_cids:
            return ancestors

        merge_split_result = LineageEngine.resolve_split_ancestors(new_merge_cids)
        merge_child_to_parent = merge_split_result["child_to_parent"]

        for seed in seed_cids:
            for merge_cid in list(ancestors[seed] & merge_source_cids_all):
                current = merge_cid
                depth = 0
                while current in merge_child_to_parent and depth < MAX_SPLIT_DEPTH:
                    depth += 1
                    parent = merge_child_to_parent[current]
                    if parent in ancestors[seed]:
                        break
                    ancestors[seed].add(parent)
                    current = parent

        return ancestors
