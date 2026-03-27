# -*- coding: utf-8 -*-
"""Unified LOT lineage resolution helpers."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.lineage_engine")

ORACLE_IN_BATCH_SIZE = 1000
MAX_SPLIT_DEPTH = 20

NODE_TYPE_WAFER = "WAFER"
NODE_TYPE_GC = "GC"
NODE_TYPE_GA = "GA"
NODE_TYPE_GD = "GD"
NODE_TYPE_LOT = "LOT"
NODE_TYPE_UNKNOWN = "UNKNOWN"

EDGE_TYPE_SPLIT = "split_from"
EDGE_TYPE_MERGE = "merge_source"
EDGE_TYPE_WAFER = "wafer_origin"
EDGE_TYPE_GD_REWORK = "gd_rework_source"


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


def _upper_prefix_match(value: Optional[str], prefix: str) -> bool:
    text = _safe_str(value)
    if not text:
        return False
    return text.upper().startswith(prefix.upper())


def _append_unique(values: List[str], item: str) -> None:
    if item and item not in values:
        values.append(item)


def _to_edge_payload(edges: List[Tuple[str, str, str]]) -> List[Dict[str, str]]:
    dedup: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for from_cid, to_cid, edge_type in edges:
        from_id = _safe_str(from_cid)
        to_id = _safe_str(to_cid)
        et = _safe_str(edge_type)
        if not from_id or not to_id or not et:
            continue
        key = (from_id, to_id, et)
        if key in seen:
            continue
        seen.add(key)
        dedup.append({
            "from_cid": from_id,
            "to_cid": to_id,
            "edge_type": et,
        })
    return dedup


def _build_parent_map(
    child_to_parent: Dict[str, str],
    merge_child_to_parent: Dict[str, str],
    merge_source_map: Dict[str, List[str]],
) -> tuple:
    """Build per-node direct parent lists and merge edge lists.

    Returns:
        (parent_map, merge_edges) where:
        - parent_map: {child_cid: [direct_parent_cids]}
        - merge_edges: {child_cid: [merge_source_cids]}

    Notes:
        merge_source_map is keyed by target/child CID.
    """
    parent_map: Dict[str, List[str]] = defaultdict(list)
    merge_edges: Dict[str, List[str]] = defaultdict(list)

    for child, parent in child_to_parent.items():
        parent_map[child].append(parent)

    for child, parent in merge_child_to_parent.items():
        if parent not in parent_map[child]:
            parent_map[child].append(parent)

    if merge_source_map:
        for owner_cid, source_cids in merge_source_map.items():
            child = _safe_str(owner_cid)
            if not child:
                continue
            for source_cid in source_cids:
                source = _safe_str(source_cid)
                if not source or source == child:
                    continue
                if source not in parent_map[child]:
                    parent_map[child].append(source)
                    merge_edges[child].append(source)

    return dict(parent_map), dict(merge_edges)


class LineageEngine:
    """Unified split/merge genealogy resolver."""

    @staticmethod
    def _resolve_container_snapshot(
        container_ids: List[str],
    ) -> Dict[str, Dict[str, Optional[str]]]:
        normalized_cids = _normalize_list(container_ids)
        if not normalized_cids:
            return {}

        snapshots: Dict[str, Dict[str, Optional[str]]] = {}
        for i in range(0, len(normalized_cids), ORACLE_IN_BATCH_SIZE):
            batch = normalized_cids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("c.CONTAINERID", batch)
            sql = SQLLoader.load_with_params(
                "lineage/container_snapshot",
                CID_FILTER=builder.get_conditions_sql(),
            )
            df = read_sql_df(sql, builder.params, caller="lineage_engine:container_snapshot")
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                cid = _safe_str(row.get("CONTAINERID"))
                if not cid:
                    continue
                snapshots[cid] = {
                    "CONTAINERID": cid,
                    "CONTAINERNAME": _safe_str(row.get("CONTAINERNAME")),
                    "MFGORDERNAME": _safe_str(row.get("MFGORDERNAME")),
                    "OBJECTTYPE": _safe_str(row.get("OBJECTTYPE")),
                    "FIRSTNAME": _safe_str(row.get("FIRSTNAME")),
                    "ORIGINALCONTAINERID": _safe_str(row.get("ORIGINALCONTAINERID")),
                    "SPLITFROMID": _safe_str(row.get("SPLITFROMID")),
                }
        return snapshots

    @staticmethod
    def _resolve_lot_ids_by_name(names: List[str]) -> Dict[str, str]:
        normalized_names = _normalize_list(names)
        if not normalized_names:
            return {}

        mapping: Dict[str, str] = {}
        for i in range(0, len(normalized_names), ORACLE_IN_BATCH_SIZE):
            batch = normalized_names[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("c.CONTAINERNAME", batch)
            sql = SQLLoader.load_with_params(
                "lineage/lot_ids_by_name",
                NAME_FILTER=builder.get_conditions_sql(),
            )
            df = read_sql_df(sql, builder.params, caller="lineage_engine:lot_ids_by_name")
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                cid = _safe_str(row.get("CONTAINERID"))
                name = _safe_str(row.get("CONTAINERNAME"))
                if cid and name and name not in mapping:
                    mapping[name] = cid
        return mapping

    @staticmethod
    def _is_gd_snapshot(snapshot: Optional[Dict[str, Optional[str]]]) -> bool:
        if not snapshot:
            return False
        return (
            _upper_prefix_match(snapshot.get("MFGORDERNAME"), "GD")
            or _upper_prefix_match(snapshot.get("CONTAINERNAME"), "GD")
        )

    @staticmethod
    def _classify_node_type(
        cid: str,
        snapshot: Optional[Dict[str, Optional[str]]],
        wafer_ids: Set[str],
    ) -> str:
        if cid in wafer_ids:
            return NODE_TYPE_WAFER
        if LineageEngine._is_gd_snapshot(snapshot):
            return NODE_TYPE_GD
        if snapshot and (
            _upper_prefix_match(snapshot.get("MFGORDERNAME"), "GC")
            or _upper_prefix_match(snapshot.get("CONTAINERNAME"), "GC")
        ):
            return NODE_TYPE_GC
        if snapshot and (
            _upper_prefix_match(snapshot.get("MFGORDERNAME"), "GA")
            or _upper_prefix_match(snapshot.get("CONTAINERNAME"), "GA")
        ):
            return NODE_TYPE_GA
        if snapshot and _safe_str(snapshot.get("OBJECTTYPE")) == "LOT":
            return NODE_TYPE_LOT
        return NODE_TYPE_UNKNOWN

    @staticmethod
    def _build_semantic_links(
        base_node_ids: Set[str],
        snapshots: Dict[str, Dict[str, Optional[str]]],
    ) -> Tuple[Dict[str, Dict[str, Optional[str]]], List[Tuple[str, str, str]], Set[str]]:
        """Build wafer-origin and GD rework edges from container snapshots.

        Returns:
            (snapshots, semantic_edges, wafer_ids)
        """
        if not base_node_ids:
            return snapshots, [], set()

        all_snapshots = dict(snapshots)

        first_names = sorted({
            first_name
            for row in all_snapshots.values()
            for first_name in [_safe_str(row.get("FIRSTNAME"))]
            if first_name
        })
        wafer_by_name = LineageEngine._resolve_lot_ids_by_name(first_names)

        extra_ids: Set[str] = set()
        for cid in wafer_by_name.values():
            if cid not in all_snapshots:
                extra_ids.add(cid)

        for row in all_snapshots.values():
            if not LineageEngine._is_gd_snapshot(row):
                continue
            source = _safe_str(row.get("ORIGINALCONTAINERID")) or _safe_str(row.get("SPLITFROMID"))
            if source and source not in all_snapshots:
                extra_ids.add(source)

        if extra_ids:
            all_snapshots.update(LineageEngine._resolve_container_snapshot(sorted(extra_ids)))

        semantic_edges: List[Tuple[str, str, str]] = []
        wafer_ids: Set[str] = set()

        for cid, row in all_snapshots.items():
            first_name = _safe_str(row.get("FIRSTNAME"))
            wafer_cid = wafer_by_name.get(first_name or "")
            if wafer_cid and wafer_cid != cid:
                semantic_edges.append((wafer_cid, cid, EDGE_TYPE_WAFER))
                wafer_ids.add(wafer_cid)

            if LineageEngine._is_gd_snapshot(row):
                source = _safe_str(row.get("ORIGINALCONTAINERID")) or _safe_str(row.get("SPLITFROMID"))
                if source and source != cid:
                    semantic_edges.append((source, cid, EDGE_TYPE_GD_REWORK))

        return all_snapshots, semantic_edges, wafer_ids

    @staticmethod
    def _build_nodes_payload(
        node_ids: Set[str],
        snapshots: Dict[str, Dict[str, Optional[str]]],
        cid_to_name: Dict[str, str],
        wafer_ids: Set[str],
    ) -> Dict[str, Dict[str, Optional[str]]]:
        payload: Dict[str, Dict[str, Optional[str]]] = {}
        for cid in sorted({cid for cid in node_ids if _safe_str(cid)}):
            snapshot = snapshots.get(cid, {})
            name = _safe_str(snapshot.get("CONTAINERNAME")) or _safe_str(cid_to_name.get(cid)) or cid
            payload[cid] = {
                "container_id": cid,
                "container_name": name,
                "mfgorder_name": _safe_str(snapshot.get("MFGORDERNAME")),
                "wafer_lot": _safe_str(snapshot.get("FIRSTNAME")),
                "node_type": LineageEngine._classify_node_type(cid, snapshot, wafer_ids),
            }
        return payload

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

        total_batches = (len(normalized_cids) + ORACLE_IN_BATCH_SIZE - 1) // ORACLE_IN_BATCH_SIZE
        for batch_idx, i in enumerate(range(0, len(normalized_cids), ORACLE_IN_BATCH_SIZE)):
            batch = normalized_cids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("c.CONTAINERID", batch)

            sql = SQLLoader.load_with_params(
                "lineage/split_ancestors",
                CID_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params, caller="lineage_engine:split_ancestors")
            if df is None or df.empty:
                if total_batches > 5 and (batch_idx + 1) % 5 == 0:
                    logger.info(
                        "Split ancestors progress: %s/%s batches, edges=%s, names=%s",
                        batch_idx + 1, total_batches, len(child_to_parent), len(cid_to_name),
                    )
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

            if total_batches > 5 and (batch_idx + 1) % 5 == 0:
                logger.info(
                    "Split ancestors progress: %s/%s batches, edges=%s, names=%s",
                    batch_idx + 1, total_batches, len(child_to_parent), len(cid_to_name),
                )

        logger.info(
            "Split ancestor resolution completed: seed=%s, edges=%s, names=%s",
            len(normalized_cids),
            len(child_to_parent),
            len(cid_to_name),
        )
        return {"child_to_parent": child_to_parent, "cid_to_name": cid_to_name}

    @staticmethod
    def resolve_merge_sources(
        target_cids: List[str],
    ) -> Dict[str, List[str]]:
        """Resolve merge source lots by target LOT CID (COMBINE.LOTID)."""
        normalized_target_cids = _normalize_list(target_cids)
        if not normalized_target_cids:
            return {}

        result: Dict[str, Set[str]] = defaultdict(set)

        for i in range(0, len(normalized_target_cids), ORACLE_IN_BATCH_SIZE):
            batch = normalized_target_cids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("ca.LOTID", batch)

            sql = SQLLoader.load_with_params(
                "lineage/merge_sources",
                TARGET_CID_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params, caller="lineage_engine:merge_sources")
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                target_cid = _safe_str(row.get("FINISHED_CID"))
                source_cid = _safe_str(row.get("SOURCE_CID"))
                if not target_cid or not source_cid or source_cid == target_cid:
                    continue
                result[target_cid].add(source_cid)

        mapped = {k: sorted(v) for k, v in result.items()}
        logger.info(
            "Merge source resolution completed: target_cids=%s, mapped=%s",
            len(normalized_target_cids),
            len(mapped),
        )
        return mapped

    @staticmethod
    def resolve_split_descendants(
        root_cids: List[str],
    ) -> Dict[str, Any]:
        """Resolve split lineage downward from root(s) via CONNECT BY.

        Returns:
            {
                "children_map": {parent_cid: [child_cids]},
                "cid_to_name": {cid: container_name},
            }
        """
        normalized_roots = _normalize_list(root_cids)
        children_map: Dict[str, List[str]] = defaultdict(list)
        cid_to_name: Dict[str, str] = {}

        if not normalized_roots:
            return {"children_map": dict(children_map), "cid_to_name": cid_to_name}

        for i in range(0, len(normalized_roots), ORACLE_IN_BATCH_SIZE):
            batch = normalized_roots[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("c.CONTAINERID", batch)

            sql = SQLLoader.load_with_params(
                "lineage/split_descendants",
                ROOT_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params, caller="lineage_engine:split_descendants")
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
                    if cid not in children_map[parent]:
                        children_map[parent].append(cid)

        logger.info(
            "Split descendant resolution completed: roots=%s, edges=%s, names=%s",
            len(normalized_roots),
            sum(len(v) for v in children_map.values()),
            len(cid_to_name),
        )
        return {"children_map": dict(children_map), "cid_to_name": cid_to_name}

    @staticmethod
    def resolve_leaf_serials(
        container_ids: List[str],
    ) -> Dict[str, List[str]]:
        """Find finished product serial numbers for leaf lot CIDs.

        Returns:
            {cid: [finished_names]}
        """
        normalized_cids = _normalize_list(container_ids)
        if not normalized_cids:
            return {}

        result: Dict[str, List[str]] = defaultdict(list)

        for i in range(0, len(normalized_cids), ORACLE_IN_BATCH_SIZE):
            batch = normalized_cids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            builder.add_in_condition("ca.CONTAINERID", batch)

            sql = SQLLoader.load_with_params(
                "lineage/leaf_serial_numbers",
                CID_FILTER=builder.get_conditions_sql(),
            )

            df = read_sql_df(sql, builder.params, caller="lineage_engine:leaf_serial_numbers")
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                cid = _safe_str(row.get("CONTAINERID"))
                finished = _safe_str(row.get("FINISHEDNAME"))
                if cid and finished and finished not in result[cid]:
                    result[cid].append(finished)

        logger.info(
            "Leaf serial resolution completed: leaf_cids=%s, with_serials=%s",
            len(normalized_cids),
            len(result),
        )
        return dict(result)

    @staticmethod
    def resolve_forward_tree(
        container_ids: List[str],
        initial_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve a forward production tree: root(wafer) → splits → leaf → serial numbers.

        1. Trace UP from seed CIDs to find root(s) via split_ancestors
        2. Trace DOWN from root(s) to get all descendants via split_descendants
        3. For leaf nodes, query COMBINEDASSYLOTS for finished serial numbers

        Returns:
            {
                "roots": [root_cids],
                "children_map": {parent_cid: [child_cids]},
                "leaf_serials": {leaf_cid: [finished_names]},
                "cid_to_name": {cid: container_name},
                "total_nodes": int,
            }
        """
        seed_cids = _normalize_list(container_ids)
        empty = {
            "roots": [],
            "children_map": {},
            "leaf_serials": {},
            "cid_to_name": {},
            "total_nodes": 0,
        }
        if not seed_cids:
            return empty

        # Step 1: Trace UP to find roots
        split_result = LineageEngine.resolve_split_ancestors(seed_cids, initial_names)
        child_to_parent = split_result["child_to_parent"]
        cid_to_name = dict(split_result["cid_to_name"])

        # Find root CIDs: trace each seed's chain to the top
        roots_set: Set[str] = set()
        for seed in seed_cids:
            current = seed
            depth = 0
            while current in child_to_parent and depth < MAX_SPLIT_DEPTH:
                depth += 1
                parent = child_to_parent[current]
                if parent == current:
                    break
                current = parent
            roots_set.add(current)

        roots = sorted(roots_set)

        # Step 2: Trace DOWN from roots to get full tree
        desc_result = LineageEngine.resolve_split_descendants(roots)
        split_children_map = desc_result["children_map"]
        children_map: Dict[str, List[str]] = {
            parent: list(children)
            for parent, children in split_children_map.items()
        }
        cid_to_name.update(desc_result["cid_to_name"])

        split_edges: List[Tuple[str, str, str]] = []
        for parent, children in split_children_map.items():
            for child in children:
                split_edges.append((parent, child, EDGE_TYPE_SPLIT))
        split_pairs = {(parent, child) for parent, child, _ in split_edges}

        # Collect all nodes in the tree
        all_nodes: Set[str] = set(roots)
        for parent, children in children_map.items():
            all_nodes.add(parent)
            all_nodes.update(children)

        # Step 3: Find leaf nodes (nodes with no children in children_map)
        leaf_cids = [cid for cid in all_nodes if cid not in children_map]

        # Step 4: Query serial numbers for leaf nodes
        leaf_serials = LineageEngine.resolve_leaf_serials(leaf_cids) if leaf_cids else {}

        # Step 4b: Resolve merge relations for known nodes by target CID.
        merge_edges: List[Tuple[str, str, str]] = []
        try:
            merge_source_map = LineageEngine.resolve_merge_sources(list(all_nodes))
            for target_cid, source_cids in merge_source_map.items():
                target = _safe_str(target_cid)
                if not target:
                    continue
                for source_cid in source_cids:
                    source = _safe_str(source_cid)
                    if not source or source == target:
                        continue
                    if (source, target) in split_pairs:
                        continue
                    merge_edges.append((source, target, EDGE_TYPE_MERGE))
                    all_nodes.add(source)
                    all_nodes.add(target)
        except Exception as exc:
            logger.warning("Forward merge enrichment skipped due to merge lookup error: %s", exc)

        # Step 5: Build semantic links (wafer origin / GD rework) and augment tree.
        snapshots: Dict[str, Dict[str, Optional[str]]] = {}
        semantic_edges: List[Tuple[str, str, str]] = []
        wafer_ids: Set[str] = set()
        try:
            snapshots = LineageEngine._resolve_container_snapshot(list(all_nodes))
            for cid, row in snapshots.items():
                name = _safe_str(row.get("CONTAINERNAME"))
                if name:
                    cid_to_name[cid] = name

            snapshots, semantic_edges, wafer_ids = LineageEngine._build_semantic_links(all_nodes, snapshots)
            for cid, row in snapshots.items():
                name = _safe_str(row.get("CONTAINERNAME"))
                if name:
                    cid_to_name[cid] = name
        except Exception as exc:
            logger.warning("Forward semantic enrichment skipped due to snapshot error: %s", exc)

        for from_cid, to_cid, _edge_type in semantic_edges:
            if from_cid not in children_map:
                children_map[from_cid] = []
            _append_unique(children_map[from_cid], to_cid)
            all_nodes.add(from_cid)
            all_nodes.add(to_cid)

        # Recompute roots after semantic edge augmentation.
        incoming: Set[str] = set()
        for parent, children in children_map.items():
            all_nodes.add(parent)
            for child in children:
                incoming.add(child)
                all_nodes.add(child)
        roots = sorted([cid for cid in all_nodes if cid not in incoming])

        typed_nodes = LineageEngine._build_nodes_payload(all_nodes, snapshots, cid_to_name, wafer_ids)
        typed_edges = _to_edge_payload(split_edges + merge_edges + semantic_edges)

        logger.info(
            "Forward tree resolution completed: seeds=%s, roots=%s, nodes=%s, leaves=%s, serials=%s, merge_edges=%s, semantic_edges=%s",
            len(seed_cids),
            len(roots),
            len(all_nodes),
            len(leaf_cids),
            len(leaf_serials),
            len(merge_edges),
            len(semantic_edges),
        )

        return {
            "roots": roots,
            "children_map": children_map,
            "leaf_serials": leaf_serials,
            "cid_to_name": cid_to_name,
            "total_nodes": len(all_nodes),
            "nodes": typed_nodes,
            "edges": typed_edges,
        }

    @staticmethod
    def resolve_full_genealogy(
        container_ids: List[str],
        initial_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Resolve combined split + merge genealogy graph.

        Returns:
            {
                "ancestors": {seed_cid: set(ancestor_cids)},
                "cid_to_name": {cid: container_name},
                "parent_map": {child_cid: [direct_parent_cids]},
                "merge_edges": {child_cid: [merge_source_cids]},
            }
        """
        seed_cids = _normalize_list(container_ids)
        if not seed_cids:
            return {
                "ancestors": {},
                "cid_to_name": {},
                "parent_map": {},
                "merge_edges": {},
                "nodes": {},
                "edges": [],
            }

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

        split_edges: List[Tuple[str, str, str]] = [
            (parent, child, EDGE_TYPE_SPLIT)
            for child, parent in child_to_parent.items()
            if _safe_str(parent) and _safe_str(child)
        ]

        merge_lookup_targets = sorted(
            {
                cid
                for cid in (
                    list(seed_cids)
                    + list(child_to_parent.keys())
                    + list(child_to_parent.values())
                )
                if _safe_str(cid)
            }
        )
        merge_source_map = LineageEngine.resolve_merge_sources(merge_lookup_targets)
        merge_child_to_parent: Dict[str, str] = {}
        merge_source_cids_all: Set[str] = set()
        if merge_source_map:
            for seed in seed_cids:
                self_and_ancestors = ancestors[seed] | {seed}
                for cid in list(self_and_ancestors):
                    for source_cid in merge_source_map.get(cid, []):
                        if source_cid == cid or source_cid in self_and_ancestors:
                            continue
                        ancestors[seed].add(source_cid)
                        merge_source_cids_all.add(source_cid)

            seen = set(seed_cids) | set(child_to_parent.keys()) | set(child_to_parent.values())
            new_merge_cids = list(merge_source_cids_all - seen)
            if new_merge_cids:
                merge_split_result = LineageEngine.resolve_split_ancestors(new_merge_cids)
                merge_child_to_parent = merge_split_result["child_to_parent"]
                cid_to_name.update(merge_split_result["cid_to_name"])

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

        pm, me = _build_parent_map(child_to_parent, merge_child_to_parent, merge_source_map)

        for child, parent in merge_child_to_parent.items():
            if _safe_str(parent) and _safe_str(child):
                split_edges.append((parent, child, EDGE_TYPE_SPLIT))

        merge_payload_edges: List[Tuple[str, str, str]] = []
        for child, sources in me.items():
            for source in sources:
                merge_payload_edges.append((source, child, EDGE_TYPE_MERGE))

        all_nodes: Set[str] = set(seed_cids)
        for values in ancestors.values():
            all_nodes.update(values)
        for child, parents in pm.items():
            all_nodes.add(child)
            all_nodes.update(parents)

        snapshots: Dict[str, Dict[str, Optional[str]]] = {}
        semantic_edges: List[Tuple[str, str, str]] = []
        wafer_ids: Set[str] = set()
        try:
            snapshots = LineageEngine._resolve_container_snapshot(list(all_nodes))
            for cid, row in snapshots.items():
                name = _safe_str(row.get("CONTAINERNAME"))
                if name:
                    cid_to_name[cid] = name

            snapshots, semantic_edges, wafer_ids = LineageEngine._build_semantic_links(all_nodes, snapshots)
            for cid, row in snapshots.items():
                name = _safe_str(row.get("CONTAINERNAME"))
                if name:
                    cid_to_name[cid] = name
        except Exception as exc:
            logger.warning("Reverse semantic enrichment skipped due to snapshot error: %s", exc)

        for parent, child, _edge_type in semantic_edges:
            parent = _safe_str(parent)
            child = _safe_str(child)
            if not parent or not child:
                continue
            parents = pm.setdefault(child, [])
            _append_unique(parents, parent)
            all_nodes.add(parent)
            all_nodes.add(child)

        recomputed_ancestors: Dict[str, Set[str]] = {}
        recomputed_roots: Dict[str, str] = {}
        for seed in seed_cids:
            visited: Set[str] = set()
            stack = list(pm.get(seed, []))
            depth = 0
            while stack and depth < MAX_SPLIT_DEPTH * 10:
                depth += 1
                parent = _safe_str(stack.pop())
                if not parent or parent in visited:
                    continue
                visited.add(parent)
                for grand_parent in pm.get(parent, []):
                    gp = _safe_str(grand_parent)
                    if gp and gp not in visited:
                        stack.append(gp)
            recomputed_ancestors[seed] = visited
            # Root = ancestor with no further parents; if no ancestors, seed is its own root
            if visited:
                root_cid = next(
                    (cid for cid in visited if not pm.get(cid)),
                    next(iter(visited)),
                )
            else:
                root_cid = seed
            recomputed_roots[seed] = cid_to_name.get(root_cid, root_cid)

        typed_nodes = LineageEngine._build_nodes_payload(all_nodes, snapshots, cid_to_name, wafer_ids)
        typed_edges = _to_edge_payload(split_edges + merge_payload_edges + semantic_edges)

        return {
            "ancestors": recomputed_ancestors,
            "cid_to_name": cid_to_name,
            "parent_map": pm,
            "merge_edges": me,
            "seed_roots": recomputed_roots,
            "nodes": typed_nodes,
            "edges": typed_edges,
        }
