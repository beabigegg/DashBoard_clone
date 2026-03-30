# -*- coding: utf-8 -*-
"""DuckDB runtime for MSD (mid-section defect) staged trace aggregation.

Reads stage spool parquet files produced by the RQ lineage/events pipeline
and computes KPIs, charts, daily-trend, and detail rows using DuckDB so that
no large pandas frames need to be assembled in the gunicorn worker.

Spool layout expected:
  {SPOOL_NAMESPACE}/{trace_query_id}_events.parquet
  {SPOOL_NAMESPACE}/{trace_query_id}_lineage.parquet   (optional, for attribution)

Usage::

    from mes_dashboard.services.msd_duckdb_runtime import MsdDuckdbRuntime

    rt = MsdDuckdbRuntime(trace_query_id="msd-abc12345")
    if rt.is_available():
        summary = rt.get_summary()
        detail = rt.get_detail(page=1, per_page=20, sort_by="defect_rate", order="desc")
        # streaming CSV:
        for chunk in rt.export_csv():
            yield chunk
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger("mes_dashboard.msd_duckdb_runtime")

SPOOL_NAMESPACE = "msd-events"
_STAGE_EVENTS = "events"
_STAGE_LINEAGE = "lineage"
_STAGE_DETECTION = "detection"


class MsdDuckdbRuntime:
    """DuckDB-backed runtime for MSD aggregation over spool parquet files."""

    def __init__(self, trace_query_id: str) -> None:
        self.trace_query_id = trace_query_id
        self._events_path: Optional[str] = None
        self._lineage_path: Optional[str] = None
        self._detection_path: Optional[str] = None
        self._resolved = False

    def _resolve_paths(self) -> None:
        if self._resolved:
            return
        from mes_dashboard.core.query_spool_store import (
            get_stage_spool_path,
            get_spool_file_path,
        )
        self._events_path = (
            get_stage_spool_path(SPOOL_NAMESPACE, self.trace_query_id, _STAGE_EVENTS)
            or get_spool_file_path(SPOOL_NAMESPACE, self.trace_query_id)
        )
        self._lineage_path = get_stage_spool_path(
            SPOOL_NAMESPACE, self.trace_query_id, _STAGE_LINEAGE
        )
        # Try to resolve detection spool (registered as stage under msd-events namespace)
        _det_stage_path = get_stage_spool_path(
            SPOOL_NAMESPACE, self.trace_query_id, _STAGE_DETECTION
        )
        self._detection_path = _det_stage_path if _det_stage_path and Path(_det_stage_path).exists() else None
        self._resolved = True

    def is_available(self) -> bool:
        """Return True if at least the events spool file is present."""
        self._resolve_paths()
        available = bool(self._events_path and Path(self._events_path).exists())
        from mes_dashboard.core.heavy_query_telemetry import record_spool_hit, record_spool_miss
        if available:
            record_spool_hit("msd", self.trace_query_id)
        else:
            record_spool_miss("msd", self.trace_query_id)
        return available

    @staticmethod
    def _sql_quote(value: str) -> str:
        return value.replace("'", "''")

    def _register_runtime_views(
        self,
        conn,
        detection_spool_path: Optional[str] = None,
        loss_reasons: Optional[List[str]] = None,
    ) -> bool:
        self._resolve_paths()
        if not self._events_path or not detection_spool_path:
            return False

        conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")
        conn.execute(f"CREATE VIEW detection_raw AS SELECT * FROM read_parquet('{detection_spool_path}')")

        if loss_reasons:
            quoted = ", ".join(f"'{self._sql_quote(str(reason).strip())}'" for reason in loss_reasons if str(reason).strip())
            if quoted:
                conn.execute(
                    f"""
                    CREATE VIEW detection AS
                    SELECT *
                    FROM detection_raw
                    WHERE LOSSREASONNAME IN ({quoted})
                       OR REJECTQTY = 0
                       OR LOSSREASONNAME IS NULL
                    """
                )
            else:
                conn.execute("CREATE VIEW detection AS SELECT * FROM detection_raw")
        else:
            conn.execute("CREATE VIEW detection AS SELECT * FROM detection_raw")

        if self._lineage_path and Path(self._lineage_path).exists():
            conn.execute(f"CREATE VIEW lineage AS SELECT * FROM read_parquet('{self._lineage_path}')")
        return True

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            import pandas as pd

            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value).strip()

    def _load_spool_frames(self):
        import pandas as pd

        self._resolve_paths()
        events_df = pd.read_parquet(self._events_path) if self._events_path and Path(self._events_path).exists() else pd.DataFrame()
        lineage_df = pd.read_parquet(self._lineage_path) if self._lineage_path and Path(self._lineage_path).exists() else pd.DataFrame()
        detection_df = pd.read_parquet(self._detection_path) if self._detection_path and Path(self._detection_path).exists() else pd.DataFrame()
        return events_df, lineage_df, detection_df

    def _build_lineage_maps(self, lineage_df) -> tuple[Dict[str, set[str]], Dict[str, str]]:
        ancestors: Dict[str, set[str]] = {}
        roots: Dict[str, str] = {}
        if lineage_df is None or lineage_df.empty:
            return ancestors, roots

        descendant_ids = set()
        ancestor_name_map: Dict[str, str] = {}
        for row in lineage_df.to_dict(orient="records"):
            descendant_id = self._safe_text(row.get("DESCENDANT_ID"))
            ancestor_id = self._safe_text(row.get("ANCESTOR_ID"))
            ancestor_name = self._safe_text(row.get("ANCESTOR_NAME")) or ancestor_id
            if not descendant_id or not ancestor_id:
                continue
            descendant_ids.add(descendant_id)
            ancestors.setdefault(descendant_id, set()).add(ancestor_id)
            if ancestor_name:
                ancestor_name_map[ancestor_id] = ancestor_name

        for descendant_id, ancestor_ids in ancestors.items():
            root_names = sorted(
                {
                    ancestor_name_map.get(ancestor_id) or ancestor_id
                    for ancestor_id in ancestor_ids
                    if ancestor_id not in descendant_ids
                }
            )
            if root_names:
                roots[descendant_id] = ", ".join(root_names)
        return ancestors, roots

    def _split_events_by_cid(self, events_df) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        upstream_by_cid: Dict[str, List[Dict[str, Any]]] = {}
        materials_by_cid: Dict[str, List[Dict[str, Any]]] = {}
        downstream_by_cid: Dict[str, List[Dict[str, Any]]] = {}
        if events_df is None or events_df.empty:
            return upstream_by_cid, materials_by_cid, downstream_by_cid

        container_col = "CONTAINERID" if "CONTAINERID" in events_df.columns else "CONTAINER_ID" if "CONTAINER_ID" in events_df.columns else None
        if not container_col:
            return upstream_by_cid, materials_by_cid, downstream_by_cid

        for row in events_df.to_dict(orient="records"):
            cid = self._safe_text(row.get(container_col))
            if not cid:
                continue

            material_part = self._safe_text(row.get("MATERIALPARTNAME"))
            has_upstream_fields = any(
                self._safe_text(row.get(col))
                for col in ("WORKCENTER_GROUP", "EQUIPMENTID", "EQUIPMENTNAME", "SPECNAME", "TRACKINTIMESTAMP")
            )
            has_downstream_fields = any(
                row.get(col) is not None
                for col in ("REJECT_TOTAL_QTY", "reject_total_qty", "LOTS_REACHED", "lots_reached")
            )

            if material_part:
                materials_by_cid.setdefault(cid, []).append(row)
            if has_upstream_fields and not material_part:
                upstream_by_cid.setdefault(cid, []).append(row)
            if has_downstream_fields:
                downstream_by_cid.setdefault(cid, []).append(row)

        return upstream_by_cid, materials_by_cid, downstream_by_cid

    def _build_backward_payload_from_spool(
        self,
        loss_reasons: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        self._resolve_paths()
        if not self._detection_path or not Path(self._detection_path).exists():
            return None

        from mes_dashboard.services.mid_section_defect_service import (
            _attribute_defects,
            _attribute_materials,
            _attribute_wafer_roots,
            _build_all_charts,
            _build_daily_trend,
            _build_detail_table,
            _build_detection_lookup,
            _build_kpi,
            _empty_result,
            _normalize_materials_event_records,
            _normalize_upstream_event_records,
            parse_loss_reasons_param,
        )

        try:
            events_df, lineage_df, detection_df = self._load_spool_frames()
            if detection_df.empty:
                empty_result = _empty_result("backward")
                return {
                    "summary": {
                        "kpi": empty_result["kpi"],
                        "charts": empty_result["charts"],
                        "daily_trend": empty_result["daily_trend"],
                        "available_loss_reasons": empty_result["available_loss_reasons"],
                        "genealogy_status": empty_result["genealogy_status"],
                        "detail_total_count": 0,
                        "attribution": [],
                        "trace_query_id": self.trace_query_id,
                    },
                    "detail": [],
                }

            normalized_loss_reasons = parse_loss_reasons_param(loss_reasons)
            available_loss_reasons = sorted(
                detection_df.loc[detection_df["REJECTQTY"] > 0, "LOSSREASONNAME"]
                .dropna()
                .astype(str)
                .tolist()
            )
            available_loss_reasons = sorted(set(v.strip() for v in available_loss_reasons if v and v.strip()))

            if normalized_loss_reasons:
                filtered_df = detection_df[
                    (detection_df["LOSSREASONNAME"].isin(normalized_loss_reasons))
                    | (detection_df["REJECTQTY"] == 0)
                    | (detection_df["LOSSREASONNAME"].isna())
                ].copy()
            else:
                filtered_df = detection_df.copy()

            detection_data = _build_detection_lookup(filtered_df)
            lineage_ancestors, lineage_roots = self._build_lineage_maps(lineage_df)
            upstream_events_by_cid, materials_events_by_cid, _ = self._split_events_by_cid(events_df)
            normalized_upstream = _normalize_upstream_event_records(upstream_events_by_cid)
            normalized_materials = _normalize_materials_event_records(materials_events_by_cid)

            attribution = _attribute_defects(
                detection_data,
                lineage_ancestors,
                normalized_upstream,
                normalized_loss_reasons,
            )
            material_attribution = _attribute_materials(
                detection_data,
                lineage_ancestors,
                normalized_materials,
                normalized_loss_reasons,
            )
            wafer_root_attribution = _attribute_wafer_roots(
                detection_data,
                lineage_roots,
                normalized_loss_reasons,
            )
            detail = _build_detail_table(
                filtered_df,
                lineage_ancestors,
                normalized_upstream,
                materials_by_cid=normalized_materials,
                roots=lineage_roots,
            )

            summary = {
                "kpi": _build_kpi(filtered_df, attribution, normalized_loss_reasons),
                "charts": _build_all_charts(
                    attribution,
                    detection_data,
                    materials_attribution=material_attribution,
                    wafer_root_attribution=wafer_root_attribution,
                ),
                "daily_trend": _build_daily_trend(filtered_df, normalized_loss_reasons),
                "available_loss_reasons": available_loss_reasons,
                "genealogy_status": "ready",
                "detail_total_count": len(detail),
                "attribution": attribution,
                "trace_query_id": self.trace_query_id,
            }
            return {"summary": summary, "detail": detail}
        except Exception as exc:
            logger.warning(
                "MsdDuckdbRuntime._build_backward_payload_from_spool failed (trace_query_id=%s): %s",
                self.trace_query_id,
                exc,
            )
            return None

    @staticmethod
    def _sort_detail_rows(
        rows: List[Dict[str, Any]],
        sort_by: str,
        order: str,
    ) -> List[Dict[str, Any]]:
        reverse = order.lower() == "desc"
        sort_map = {
            "defect_rate": "DEFECT_RATE",
            "defect_qty": "DEFECT_QTY",
            "input_qty": "INPUT_QTY",
            "ancestor_count": "ANCESTOR_COUNT",
            "upstream_machine_count": "UPSTREAM_MACHINE_COUNT",
        }
        sort_key = sort_map.get(sort_by.lower(), "DEFECT_RATE")

        def _value(row: Dict[str, Any]):
            value = row.get(sort_key)
            if value is None:
                return float("-inf") if reverse else float("inf")
            return value

        return sorted(rows, key=_value, reverse=reverse)

    # ------------------------------------------------------------------
    # Summary / KPI
    # ------------------------------------------------------------------

    def get_summary(
        self,
        direction: str = "backward",
        loss_reasons: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compute summary KPIs and charts from spool via DuckDB."""
        self._resolve_paths()
        if direction == "backward":
            if not self._detection_path or not Path(self._detection_path).exists():
                return None
            summary = self.get_summary_with_detection(self._detection_path, loss_reasons=loss_reasons)
            if summary is not None:
                return summary
            return None

        if not self._events_path:
            return None

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")

            kpi = self._compute_kpi(conn)
            charts = self._compute_charts(conn)
            daily_trend = self._compute_daily_trend(conn)

            if self._lineage_path and Path(self._lineage_path).exists():
                conn.execute(
                    f"CREATE VIEW lineage AS SELECT * FROM read_parquet('{self._lineage_path}')"
                )
                attribution = self._compute_attribution(conn)
            else:
                attribution = []

            conn.close()
            return {
                "kpi": kpi,
                "charts": charts,
                "daily_trend": daily_trend,
                "attribution": attribution,
                "trace_query_id": self.trace_query_id,
            }
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_summary failed (trace_query_id=%s): %s", self.trace_query_id, exc)
            from mes_dashboard.core.heavy_query_telemetry import record_lifecycle_failure
            record_lifecycle_failure("msd", reason="runtime_error")
            return None

    def _compute_kpi(self, conn) -> Dict[str, Any]:
        """Compute total defect count, lot count, and defect rate from events view."""
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT CONTAINER_ID) AS lot_count,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                """
            ).fetchone()
            if row:
                lot_count, defect_qty, input_qty = row
                defect_rate = (
                    round(float(defect_qty) / float(input_qty) * 100, 2)
                    if input_qty and input_qty > 0
                    else 0.0
                )
                return {
                    "lot_count": int(lot_count or 0),
                    "defect_qty": int(defect_qty or 0),
                    "input_qty": int(input_qty or 0),
                    "defect_rate": defect_rate,
                }
        except Exception as exc:
            logger.debug("_compute_kpi failed: %s", exc)
        return {"lot_count": 0, "defect_qty": 0, "input_qty": 0, "defect_rate": 0.0}

    def _compute_charts(self, conn) -> List[Dict[str, Any]]:
        """Compute top-N station defect rate chart from events view."""
        try:
            rows = conn.execute(
                """
                SELECT
                    STATION_NAME,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                GROUP BY STATION_NAME
                ORDER BY defect_qty DESC
                LIMIT 20
                """
            ).fetchall()
            return [
                {
                    "station": r[0],
                    "defect_qty": int(r[1] or 0),
                    "input_qty": int(r[2] or 0),
                    "defect_rate": round(float(r[1] or 0) / float(r[2]) * 100, 2) if r[2] else 0.0,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_charts failed: %s", exc)
            return []

    def _compute_daily_trend(self, conn) -> List[Dict[str, Any]]:
        """Compute daily defect trend from events view."""
        try:
            rows = conn.execute(
                """
                SELECT
                    CAST(TXNDATE AS DATE) AS txn_day,
                    SUM(DEFECT_QTY) AS defect_qty,
                    SUM(INPUT_QTY) AS input_qty
                FROM events
                GROUP BY CAST(TXNDATE AS DATE)
                ORDER BY txn_day
                """
            ).fetchall()
            return [
                {
                    "date": str(r[0]),
                    "defect_qty": int(r[1] or 0),
                    "input_qty": int(r[2] or 0),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_daily_trend failed: %s", exc)
            return []

    def _compute_attribution(self, conn) -> List[Dict[str, Any]]:
        """Compute upstream attribution by joining events + lineage views."""
        try:
            rows = conn.execute(
                """
                SELECT
                    l.ANCESTOR_NAME,
                    COUNT(DISTINCT e.CONTAINER_ID) AS lot_count,
                    SUM(e.DEFECT_QTY) AS defect_qty
                FROM events e
                JOIN lineage l ON e.CONTAINER_ID = l.DESCENDANT_ID
                GROUP BY l.ANCESTOR_NAME
                ORDER BY defect_qty DESC
                LIMIT 20
                """
            ).fetchall()
            return [
                {
                    "ancestor": r[0],
                    "lot_count": int(r[1] or 0),
                    "defect_qty": int(r[2] or 0),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_attribution failed (may be schema difference): %s", exc)
            return []

    # ------------------------------------------------------------------
    # Summary with Detection Spool (canonical path for trace job)
    # ------------------------------------------------------------------

    def get_summary_with_detection(
        self,
        detection_spool_path: str,
        loss_reasons: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compute summary KPIs and charts using detection spool + events/lineage spools.

        This is the canonical aggregation path for the trace-job flow.  The
        detection spool (namespace ``msd_detect``) contains one row per
        CONTAINERID × LOSSREASONNAME and is the authoritative source for KPI
        numbers.  The events and lineage spools (namespace ``msd-events``) are
        used for upstream attribution charts only.

        Args:
            detection_spool_path: Absolute path to the ``msd_detect`` parquet
                spool file that corresponds to this query's station / date range.

        Returns:
            Aggregated dict compatible with ``build_trace_aggregation_from_events``
            output, or None if the computation fails.
        """
        self._resolve_paths()
        if not self._events_path:
            return None

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            if not self._register_runtime_views(
                conn,
                detection_spool_path=detection_spool_path,
                loss_reasons=loss_reasons,
            ):
                conn.close()
                return None

            lineage_available = bool(self._lineage_path and Path(self._lineage_path).exists())

            kpi = self._compute_kpi_from_detection(conn)
            daily_trend = self._compute_daily_trend_from_detection(conn)
            available_loss_reasons = self._compute_available_loss_reasons(conn, source_view="detection_raw")
            detail_total_count = self._compute_detail_total_count(conn)

            if lineage_available:
                by_machine = self._compute_machine_chart(conn)
                by_material = self._compute_material_chart(conn)
                affected_machine_count = self._compute_affected_machine_count(conn)
            else:
                by_machine = []
                by_material = []
                affected_machine_count = 0

            by_loss_reason = self._compute_loss_reason_chart(conn)
            by_detection_machine = self._compute_detection_machine_chart(conn)
            by_wafer_root = self._compute_wafer_root_chart(conn) if lineage_available else []

            conn.close()

            # Merge affected_machine_count into kpi dict
            kpi["affected_machine_count"] = affected_machine_count

            charts = {
                "by_machine": by_machine,
                "by_detection_machine": by_detection_machine,
                "by_material": by_material,
                "by_wafer_root": by_wafer_root,
                "by_loss_reason": by_loss_reason,
            }

            return {
                "kpi": kpi,
                "charts": charts,
                "daily_trend": daily_trend,
                "attribution": by_machine,
                "available_loss_reasons": available_loss_reasons,
                "genealogy_status": "ready",
                "detail_total_count": detail_total_count,
                "trace_query_id": self.trace_query_id,
            }
        except Exception as exc:
            logger.warning(
                "MsdDuckdbRuntime.get_summary_with_detection failed (trace_query_id=%s): %s",
                self.trace_query_id, exc,
            )
            return None

    def _compute_kpi_from_detection(self, conn) -> Dict[str, Any]:
        """Compute KPI from detection spool (Oracle column names)."""
        try:
            row = conn.execute(
                """
                WITH lot_summary AS (
                    SELECT
                        CONTAINERID,
                        MAX(TRACKINQTY) AS lot_trackinqty,
                        SUM(REJECTQTY)  AS lot_rejectqty
                    FROM detection
                    GROUP BY CONTAINERID
                )
                SELECT
                    COUNT(DISTINCT CONTAINERID)                                  AS lot_count,
                    SUM(lot_trackinqty)                                          AS total_input,
                    SUM(CASE WHEN lot_rejectqty > 0 THEN 1 ELSE 0 END)          AS defective_lot_count,
                    SUM(lot_rejectqty)                                           AS total_defect_qty
                FROM lot_summary
                """
            ).fetchone()
            if row:
                lot_count, total_input, defective_lot_count, total_defect_qty = row
                lot_count = int(lot_count or 0)
                total_input = int(total_input or 0)
                defective_lot_count = int(defective_lot_count or 0)
                total_defect_qty = int(total_defect_qty or 0)
                total_defect_rate = (
                    round(total_defect_qty / total_input * 100, 4)
                    if total_input > 0
                    else 0.0
                )

                # Top loss reason
                top_row = conn.execute(
                    """
                    SELECT LOSSREASONNAME, SUM(REJECTQTY) AS total
                    FROM detection
                    WHERE LOSSREASONNAME IS NOT NULL AND LOSSREASONNAME != ''
                    GROUP BY LOSSREASONNAME
                    ORDER BY total DESC
                    LIMIT 1
                    """
                ).fetchone()
                top_loss_reason = str(top_row[0]) if top_row else ""

                return {
                    "total_input": total_input,
                    "lot_count": lot_count,
                    "defective_lot_count": defective_lot_count,
                    "total_defect_qty": total_defect_qty,
                    "total_defect_rate": total_defect_rate,
                    "top_loss_reason": top_loss_reason,
                }
        except Exception as exc:
            logger.debug("_compute_kpi_from_detection failed: %s", exc)
        return {
            "total_input": 0,
            "lot_count": 0,
            "defective_lot_count": 0,
            "total_defect_qty": 0,
            "total_defect_rate": 0.0,
            "top_loss_reason": "",
        }

    def _compute_daily_trend_from_detection(self, conn) -> List[Dict[str, Any]]:
        """Compute daily defect trend from detection spool."""
        try:
            rows = conn.execute(
                """
                WITH lot_daily AS (
                    SELECT
                        CAST(TRACKINTIMESTAMP AS DATE) AS txn_day,
                        CONTAINERID,
                        MAX(TRACKINQTY) AS input_qty,
                        SUM(REJECTQTY)  AS defect_qty
                    FROM detection
                    GROUP BY CAST(TRACKINTIMESTAMP AS DATE), CONTAINERID
                )
                SELECT
                    txn_day,
                    SUM(defect_qty) AS defect_qty,
                    SUM(input_qty)  AS input_qty
                FROM lot_daily
                GROUP BY txn_day
                ORDER BY txn_day
                """
            ).fetchall()
            return [
                {
                    "date": str(r[0]),
                    "defect_qty": int(r[1] or 0),
                    "input_qty": int(r[2] or 0),
                    "defect_rate": round((int(r[1] or 0) / int(r[2] or 0) * 100), 4) if int(r[2] or 0) else 0.0,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_daily_trend_from_detection failed: %s", exc)
            return []

    def _compute_attribution_from_detection(self, conn) -> List[Dict[str, Any]]:
        """Attribute defective lots to upstream WORKCENTER_GROUP via lineage + events."""
        try:
            rows = conn.execute(
                """
                WITH defective AS (
                    SELECT DISTINCT CONTAINERID FROM detection WHERE REJECTQTY > 0
                )
                SELECT
                    e.WORKCENTER_GROUP                  AS station_group,
                    COUNT(DISTINCT l.DESCENDANT_ID)     AS defective_lot_count,
                    SUM(e.TRACKINQTY)                   AS total_input
                FROM defective d
                JOIN lineage l ON l.DESCENDANT_ID = d.CONTAINERID
                JOIN events  e ON e.CONTAINERID   = l.ANCESTOR_ID
                WHERE e.WORKCENTER_GROUP IS NOT NULL
                GROUP BY e.WORKCENTER_GROUP
                ORDER BY defective_lot_count DESC
                LIMIT 20
                """
            ).fetchall()
            return [
                {
                    "station_group": r[0],
                    "defective_lot_count": int(r[1] or 0),
                    "total_input": int(r[2] or 0),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("_compute_attribution_from_detection failed: %s", exc)
            return []

    def _compute_affected_machine_count(self, conn) -> int:
        """Count distinct upstream machines for defective lots via lineage."""
        try:
            row = conn.execute(
                """
                WITH defective AS (
                    SELECT DISTINCT CONTAINERID FROM detection WHERE REJECTQTY > 0
                )
                SELECT COUNT(DISTINCT e.EQUIPMENTID) AS machine_count
                FROM defective d
                JOIN lineage l ON l.DESCENDANT_ID = d.CONTAINERID
                JOIN events  e ON e.CONTAINERID   = l.ANCESTOR_ID
                WHERE e.EQUIPMENTID IS NOT NULL
                """
            ).fetchone()
            return int(row[0] or 0) if row else 0
        except Exception as exc:
            logger.debug("_compute_affected_machine_count failed: %s", exc)
            return 0

    def _compute_detection_machine_chart(self, conn) -> List[Dict[str, Any]]:
        """Build by_detection_machine chart from detection spool."""
        try:
            rows = conn.execute(
                """
                WITH lot_machine AS (
                    SELECT
                        CONTAINERID,
                        COALESCE(NULLIF(TRIM(MAX(DETECTION_EQUIPMENTNAME)), ''), '(未知)') AS name,
                        MAX(TRACKINQTY) AS trackin_qty,
                        SUM(REJECTQTY)  AS defect_qty
                    FROM detection
                    WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID
                ),
                machine_agg AS (
                    SELECT
                        name,
                        COUNT(DISTINCT CONTAINERID) AS lot_count,
                        SUM(defect_qty)             AS defect_qty,
                        SUM(trackin_qty)            AS input_qty
                    FROM lot_machine
                    WHERE name != '(未知)'
                    GROUP BY name
                )
                SELECT name, lot_count, defect_qty, input_qty
                FROM machine_agg
                ORDER BY defect_qty DESC
                LIMIT 10
                """
            ).fetchall()
            return self._to_pareto_items(rows)
        except Exception as exc:
            logger.debug("_compute_detection_machine_chart failed: %s", exc)
            return []

    def _compute_wafer_root_chart(self, conn) -> List[Dict[str, Any]]:
        """Build by_wafer_root chart: roots = ancestors that are not descendants."""
        try:
            rows = conn.execute(
                """
                WITH defective_kpis AS (
                    SELECT CONTAINERID,
                           MAX(TRACKINQTY) AS trackin_qty,
                           SUM(REJECTQTY)  AS defect_qty
                    FROM detection WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID
                ),
                all_descendants AS (
                    SELECT DISTINCT DESCENDANT_ID FROM lineage
                ),
                roots AS (
                    SELECT DISTINCT l.ANCESTOR_ID AS root_id, l.ANCESTOR_NAME AS root_name
                    FROM lineage l
                    WHERE l.ANCESTOR_ID NOT IN (SELECT DESCENDANT_ID FROM all_descendants)
                ),
                root_agg AS (
                    SELECT
                        COALESCE(NULLIF(TRIM(r.root_name), ''), r.root_id, '(未知)') AS name,
                        COUNT(DISTINCT l.DESCENDANT_ID)                               AS lot_count,
                        SUM(dk.defect_qty)                                            AS defect_qty,
                        SUM(dk.trackin_qty)                                           AS input_qty
                    FROM roots r
                    JOIN lineage l  ON l.ANCESTOR_ID = r.root_id
                    JOIN defective_kpis dk ON dk.CONTAINERID = l.DESCENDANT_ID
                    GROUP BY name
                )
                SELECT name, lot_count, defect_qty, input_qty
                FROM root_agg
                ORDER BY defect_qty DESC
                LIMIT 10
                """
            ).fetchall()
            return self._to_pareto_items(rows)
        except Exception as exc:
            logger.debug("_compute_wafer_root_chart failed: %s", exc)
            return []

    def _compute_machine_chart(self, conn) -> List[Dict[str, Any]]:
        """Build by_machine Pareto chart from events + lineage + detection (TOP 10)."""
        try:
            rows = conn.execute(
                """
                WITH defective_kpis AS (
                    SELECT CONTAINERID,
                           MAX(TRACKINQTY)  AS trackin_qty,
                           SUM(REJECTQTY)   AS defect_qty
                    FROM detection WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID
                ),
                machine_agg AS (
                    SELECT
                        COALESCE(NULLIF(TRIM(e.EQUIPMENTNAME), ''), '(未知)') AS name,
                        COUNT(DISTINCT dk.CONTAINERID)                         AS lot_count,
                        SUM(dk.defect_qty)                                     AS defect_qty,
                        SUM(dk.trackin_qty)                                    AS input_qty
                    FROM defective_kpis dk
                    JOIN lineage l ON l.DESCENDANT_ID = dk.CONTAINERID
                    JOIN events  e ON e.CONTAINERID   = l.ANCESTOR_ID
                    WHERE e.EQUIPMENTNAME IS NOT NULL AND TRIM(e.EQUIPMENTNAME) != ''
                    GROUP BY name
                )
                SELECT name, lot_count, defect_qty, input_qty
                FROM machine_agg
                ORDER BY defect_qty DESC
                LIMIT 10
                """
            ).fetchall()
            return self._to_pareto_items(rows)
        except Exception as exc:
            logger.debug("_compute_machine_chart failed: %s", exc)
            return []

    def _compute_material_chart(self, conn) -> List[Dict[str, Any]]:
        """Build by_material Pareto chart using MATERIALPARTNAME from events spool."""
        try:
            rows = conn.execute(
                """
                WITH defective_kpis AS (
                    SELECT CONTAINERID,
                           MAX(TRACKINQTY)  AS trackin_qty,
                           SUM(REJECTQTY)   AS defect_qty
                    FROM detection WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID
                ),
                mat_agg AS (
                    SELECT
                        COALESCE(NULLIF(TRIM(e.MATERIALPARTNAME), ''), '(未知)') AS name,
                        COUNT(DISTINCT dk.CONTAINERID)                            AS lot_count,
                        SUM(dk.defect_qty)                                        AS defect_qty,
                        SUM(dk.trackin_qty)                                       AS input_qty
                    FROM defective_kpis dk
                    JOIN lineage l ON l.DESCENDANT_ID = dk.CONTAINERID
                    JOIN events  e ON e.CONTAINERID   = l.ANCESTOR_ID
                    WHERE e.MATERIALPARTNAME IS NOT NULL AND TRIM(e.MATERIALPARTNAME) != ''
                    GROUP BY name
                )
                SELECT name, lot_count, defect_qty, input_qty
                FROM mat_agg
                ORDER BY defect_qty DESC
                LIMIT 10
                """
            ).fetchall()
            return self._to_pareto_items(rows)
        except Exception as exc:
            logger.debug("_compute_material_chart failed: %s", exc)
            return []

    def _compute_loss_reason_chart(self, conn) -> List[Dict[str, Any]]:
        """Build by_loss_reason chart from detection spool."""
        try:
            total_row = conn.execute(
                """
                SELECT SUM(lot_trackin)
                FROM (
                    SELECT CONTAINERID, MAX(TRACKINQTY) AS lot_trackin
                    FROM detection GROUP BY CONTAINERID
                )
                """
            ).fetchone()
            total_input = int(total_row[0] or 0) if total_row else 0

            rows = conn.execute(
                """
                SELECT LOSSREASONNAME AS name,
                       SUM(REJECTQTY)           AS defect_qty,
                       COUNT(DISTINCT CONTAINERID) AS lot_count
                FROM detection
                WHERE REJECTQTY > 0
                  AND LOSSREASONNAME IS NOT NULL
                  AND TRIM(LOSSREASONNAME) != ''
                GROUP BY LOSSREASONNAME
                ORDER BY defect_qty DESC
                LIMIT 10
                """
            ).fetchall()

            total_defects = sum(int(r[1] or 0) for r in rows)
            items = []
            cumsum = 0
            for r in rows:
                name, defect_qty, lot_count = str(r[0]), int(r[1] or 0), int(r[2] or 0)
                cumsum += defect_qty
                rate = round(defect_qty / total_input * 100, 4) if total_input else 0.0
                items.append({
                    "name": name,
                    "defect_qty": defect_qty,
                    "lot_count": lot_count,
                    "defect_rate": rate,
                    "cumulative_pct": round(cumsum / total_defects * 100, 2) if total_defects else 0.0,
                })
            return items
        except Exception as exc:
            logger.debug("_compute_loss_reason_chart failed: %s", exc)
            return []

    def _compute_available_loss_reasons(self, conn, source_view: str = "detection") -> List[str]:
        """Return sorted list of distinct LOSSREASONNAME where REJECTQTY > 0."""
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT LOSSREASONNAME FROM """
                + source_view
                + """
                WHERE REJECTQTY > 0 AND LOSSREASONNAME IS NOT NULL AND TRIM(LOSSREASONNAME) != ''
                ORDER BY LOSSREASONNAME
                """
            ).fetchall()
            return [str(r[0]) for r in rows]
        except Exception as exc:
            logger.debug("_compute_available_loss_reasons failed: %s", exc)
            return []

    def _compute_detail_total_count(self, conn) -> int:
        """Return total detail row count under the current detection filter."""
        try:
            row = conn.execute(
                """
                WITH lot_base AS (
                    SELECT DISTINCT CONTAINERID FROM detection
                ),
                lot_defects AS (
                    SELECT CONTAINERID, LOSSREASONNAME
                    FROM detection
                    WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID, LOSSREASONNAME
                )
                SELECT COUNT(*)
                FROM lot_base lb
                LEFT JOIN lot_defects ld ON ld.CONTAINERID = lb.CONTAINERID
                """
            ).fetchone()
            return int(row[0] or 0) if row else 0
        except Exception as exc:
            logger.debug("_compute_detail_total_count failed: %s", exc)
            return 0

    @staticmethod
    def _to_pareto_items(rows) -> List[Dict[str, Any]]:
        """Convert (name, lot_count, defect_qty, input_qty) rows to Pareto chart items."""
        total_defects = sum(int(r[2] or 0) for r in rows)
        items = []
        cumsum = 0
        for r in rows:
            name, lot_count, defect_qty, input_qty = str(r[0]), int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)
            cumsum += defect_qty
            rate = round(defect_qty / input_qty * 100, 4) if input_qty else 0.0
            items.append({
                "name": name,
                "lot_count": lot_count,
                "defect_qty": defect_qty,
                "input_qty": input_qty,
                "defect_rate": rate,
                "cumulative_pct": round(cumsum / total_defects * 100, 2) if total_defects else 0.0,
            })
        return items

    # ------------------------------------------------------------------
    # Detail (paginated)
    # ------------------------------------------------------------------

    def get_detail(
        self,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "defect_rate",
        order: str = "desc",
        direction: str = "backward",
        loss_reasons: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return paginated detail rows from detection+lineage+events spool via DuckDB."""
        self._resolve_paths()
        if direction != "backward":
            return None
        if not self._events_path:
            return None
        # Detection spool is required for proper detail (CONTAINERNAME, DEFECT_QTY, etc.)
        if not self._detection_path:
            return None

        safe_order = "DESC" if order.lower() == "desc" else "ASC"
        sort_lower = sort_by.lower()
        _sortable = {"defect_rate", "defect_qty", "input_qty", "ancestor_count", "upstream_machine_count"}
        if sort_lower not in _sortable:
            sort_lower = "defect_rate"
        offset = max(0, (page - 1) * per_page)

        lineage_available = bool(self._lineage_path and Path(self._lineage_path).exists())

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            if not self._register_runtime_views(
                conn,
                detection_spool_path=self._detection_path,
                loss_reasons=loss_reasons,
            ):
                conn.close()
                return None

            # Build ancestor/machine counts from lineage if available
            ancestor_join = ""
            machine_join = ""
            ancestor_col = "0 AS ANCESTOR_COUNT"
            machine_col = "0 AS UPSTREAM_MACHINE_COUNT"
            if lineage_available:
                conn.execute(
                    """
                    CREATE TEMP TABLE lot_ancestor_counts AS
                    SELECT DESCENDANT_ID, COUNT(DISTINCT ANCESTOR_ID) AS ancestor_count
                    FROM lineage GROUP BY DESCENDANT_ID
                    """
                )
                conn.execute(
                    """
                    CREATE TEMP TABLE lot_machine_counts AS
                    SELECT l.DESCENDANT_ID, COUNT(DISTINCT e.EQUIPMENTID) AS machine_count
                    FROM lineage l
                    JOIN events e ON e.CONTAINERID = l.ANCESTOR_ID
                    WHERE e.EQUIPMENTID IS NOT NULL AND TRIM(CAST(e.EQUIPMENTID AS VARCHAR)) != ''
                    GROUP BY l.DESCENDANT_ID
                    """
                )
                ancestor_join = "LEFT JOIN lot_ancestor_counts lac ON lac.DESCENDANT_ID = lb.CONTAINERID"
                machine_join = "LEFT JOIN lot_machine_counts lmc ON lmc.DESCENDANT_ID = lb.CONTAINERID"
                ancestor_col = "COALESCE(lac.ancestor_count, 0) AS ANCESTOR_COUNT"
                machine_col = "COALESCE(lmc.machine_count, 0) AS UPSTREAM_MACHINE_COUNT"

            count_sql = """
                SELECT COUNT(*)
                FROM (
                    WITH lot_base AS (
                        SELECT DISTINCT CONTAINERID FROM detection
                    ),
                    lot_defects AS (
                        SELECT CONTAINERID, LOSSREASONNAME
                        FROM detection
                        WHERE REJECTQTY > 0
                        GROUP BY CONTAINERID, LOSSREASONNAME
                    )
                    SELECT lb.CONTAINERID, ld.LOSSREASONNAME
                    FROM lot_base lb
                    LEFT JOIN lot_defects ld ON ld.CONTAINERID = lb.CONTAINERID
                )
            """
            total_row = conn.execute(count_sql).fetchone()
            total = int(total_row[0]) if total_row else 0

            detail_sql = f"""
                WITH lot_base AS (
                    SELECT
                        CONTAINERID,
                        MAX(CONTAINERNAME)            AS CONTAINERNAME,
                        MAX(PJ_TYPE)                  AS PJ_TYPE,
                        MAX(PRODUCTLINENAME)          AS PRODUCTLINENAME,
                        MAX(WORKFLOW)                 AS WORKFLOW,
                        MAX(FINISHEDRUNCARD)          AS FINISHEDRUNCARD,
                        MAX(DETECTION_EQUIPMENTNAME)  AS DETECTION_EQUIPMENTNAME,
                        MAX(TRACKINQTY)               AS INPUT_QTY
                    FROM detection
                    GROUP BY CONTAINERID
                ),
                lot_defects AS (
                    SELECT CONTAINERID,
                           LOSSREASONNAME,
                           SUM(REJECTQTY) AS DEFECT_QTY
                    FROM detection WHERE REJECTQTY > 0
                    GROUP BY CONTAINERID, LOSSREASONNAME
                ),
                detail_rows AS (
                    SELECT
                        lb.CONTAINERID,
                        lb.CONTAINERNAME,
                        lb.PJ_TYPE,
                        lb.PRODUCTLINENAME,
                        lb.WORKFLOW,
                        lb.FINISHEDRUNCARD,
                        lb.DETECTION_EQUIPMENTNAME,
                        lb.INPUT_QTY,
                        COALESCE(ld.LOSSREASONNAME, '')                             AS LOSS_REASON,
                        COALESCE(ld.DEFECT_QTY, 0)                                  AS DEFECT_QTY,
                        CASE WHEN lb.INPUT_QTY > 0
                             THEN ROUND(COALESCE(ld.DEFECT_QTY, 0) * 100.0 / lb.INPUT_QTY, 4)
                             ELSE 0.0 END                                           AS defect_rate,
                        {ancestor_col},
                        {machine_col}
                    FROM lot_base lb
                    LEFT JOIN lot_defects ld ON ld.CONTAINERID = lb.CONTAINERID
                    {ancestor_join}
                    {machine_join}
                )
                SELECT * FROM detail_rows
                ORDER BY {sort_lower} {safe_order}
                LIMIT {per_page} OFFSET {offset}
            """
            rows = conn.execute(detail_sql).df()

            page_cids = [
                str(cid).strip()
                for cid in rows["CONTAINERID"].tolist()
                if cid is not None and str(cid).strip()
            ] if not rows.empty and "CONTAINERID" in rows.columns else []

            machine_map: Dict[str, List[Dict[str, str]]] = {}
            material_map: Dict[str, List[Dict[str, str]]] = {}
            root_map: Dict[str, str] = {}
            if lineage_available and page_cids:
                cid_list = ", ".join(f"'{self._sql_quote(cid)}'" for cid in page_cids)

                machine_rows = conn.execute(
                    f"""
                    SELECT
                        l.DESCENDANT_ID,
                        COALESCE(NULLIF(TRIM(CAST(e.WORKCENTER_GROUP AS VARCHAR)), ''), '(未知)') AS station,
                        TRIM(CAST(e.EQUIPMENTNAME AS VARCHAR)) AS machine
                    FROM lineage l
                    JOIN events e ON e.CONTAINERID = l.ANCESTOR_ID
                    WHERE l.DESCENDANT_ID IN ({cid_list})
                      AND e.EQUIPMENTNAME IS NOT NULL
                      AND TRIM(CAST(e.EQUIPMENTNAME AS VARCHAR)) != ''
                    GROUP BY l.DESCENDANT_ID, station, machine
                    ORDER BY l.DESCENDANT_ID, station, machine
                    """
                ).fetchall()
                for descendant_id, station, machine in machine_rows:
                    cid = str(descendant_id or "").strip()
                    if not cid:
                        continue
                    machine_map.setdefault(cid, []).append({
                        "station": str(station or "").strip() or "(未知)",
                        "machine": str(machine or "").strip(),
                    })

                material_rows = conn.execute(
                    f"""
                    SELECT
                        l.DESCENDANT_ID,
                        TRIM(CAST(e.MATERIALPARTNAME AS VARCHAR)) AS part,
                        COALESCE(TRIM(CAST(e.MATERIALLOTNAME AS VARCHAR)), '') AS lot
                    FROM lineage l
                    JOIN events e ON e.CONTAINERID = l.ANCESTOR_ID
                    WHERE l.DESCENDANT_ID IN ({cid_list})
                      AND e.MATERIALPARTNAME IS NOT NULL
                      AND TRIM(CAST(e.MATERIALPARTNAME AS VARCHAR)) != ''
                    GROUP BY l.DESCENDANT_ID, part, lot
                    ORDER BY l.DESCENDANT_ID, part, lot
                    """
                ).fetchall()
                for descendant_id, part, lot in material_rows:
                    cid = str(descendant_id or "").strip()
                    if not cid:
                        continue
                    material_map.setdefault(cid, []).append({
                        "part": str(part or "").strip(),
                        "lot": str(lot or "").strip(),
                    })

                root_rows = conn.execute(
                    f"""
                    WITH all_descendants AS (
                        SELECT DISTINCT DESCENDANT_ID FROM lineage
                    )
                    SELECT
                        l.DESCENDANT_ID,
                        string_agg(
                            DISTINCT COALESCE(NULLIF(TRIM(CAST(l.ANCESTOR_NAME AS VARCHAR)), ''), CAST(l.ANCESTOR_ID AS VARCHAR)),
                            ', '
                            ORDER BY COALESCE(NULLIF(TRIM(CAST(l.ANCESTOR_NAME AS VARCHAR)), ''), CAST(l.ANCESTOR_ID AS VARCHAR))
                        ) AS wafer_root
                    FROM lineage l
                    WHERE l.DESCENDANT_ID IN ({cid_list})
                      AND l.ANCESTOR_ID NOT IN (SELECT DESCENDANT_ID FROM all_descendants)
                    GROUP BY l.DESCENDANT_ID
                    """
                ).fetchall()
                root_map = {
                    str(descendant_id or "").strip(): str(wafer_root or "").strip()
                    for descendant_id, wafer_root in root_rows
                    if str(descendant_id or "").strip()
                }

            conn.close()

            items = []
            for row in rows.to_dict(orient="records"):
                cid = str(row.get("CONTAINERID") or "").strip()
                row["DEFECT_RATE"] = row.pop("defect_rate", 0.0)
                row["UPSTREAM_MACHINES"] = machine_map.get(cid, [])
                row["UPSTREAM_MATERIALS"] = material_map.get(cid, [])
                row["WAFER_ROOT"] = root_map.get(cid, "")
                items.append(row)

            return {
                "items": items,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                },
                "trace_query_id": self.trace_query_id,
            }
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_detail failed: %s", exc)
            return None

    def get_all_detail(
        self,
        sort_by: str = "defect_rate",
        order: str = "desc",
        direction: str = "backward",
        loss_reasons: Optional[List[str]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return all detail rows from events spool via DuckDB."""
        self._resolve_paths()
        if not self._events_path:
            return None

        safe_order = "DESC" if order.lower() == "desc" else "ASC"
        derived = {"defect_rate"}
        raw_allowed = {"defect_qty", "input_qty", "station_name", "txndate"}
        sort_lower = sort_by.lower()
        if sort_lower not in derived and sort_lower not in raw_allowed:
            sort_lower = "defect_qty"

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

            conn = create_heavy_query_connection()
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")
            rows = conn.execute(
                f"""
                WITH with_rate AS (
                    SELECT *,
                        CASE WHEN INPUT_QTY > 0
                             THEN DEFECT_QTY * 1.0 / INPUT_QTY * 100
                             ELSE 0.0 END AS defect_rate
                    FROM events
                )
                SELECT * FROM with_rate
                ORDER BY {sort_lower} {safe_order}
                """
            ).df()
            conn.close()
            return rows.to_dict(orient="records")
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.get_all_detail failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Export (streaming CSV)
    # ------------------------------------------------------------------

    def export_csv(
        self,
        chunk_size: int = 5000,
        direction: str = "backward",
        loss_reasons: Optional[List[str]] = None,
    ) -> Generator[bytes, None, None]:
        """Stream CSV rows from events spool via DuckDB in chunks."""
        self._resolve_paths()
        if direction == "backward" and self._detection_path and Path(self._detection_path).exists():
            import csv
            import io

            from mes_dashboard.services.mid_section_defect_service import CSV_COLUMNS_BACKWARD

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([label for _, label in CSV_COLUMNS_BACKWARD])
            yield buf.getvalue().encode("utf-8-sig")

            page = 1
            per_page = max(1, min(chunk_size, 2000))
            while True:
                detail = self.get_detail(
                    page=page,
                    per_page=per_page,
                    sort_by="defect_rate",
                    order="desc",
                    direction=direction,
                    loss_reasons=loss_reasons,
                )
                if not detail:
                    break
                items = detail.get("items") or []
                if not items:
                    break

                buf = io.StringIO()
                writer = csv.writer(buf)
                for row in items:
                    csv_row = []
                    for col, _ in CSV_COLUMNS_BACKWARD:
                        value = row.get(col, "")
                        if col == "UPSTREAM_MACHINES" and isinstance(value, list):
                            value = ", ".join(
                                f"{item.get('station', '')}/{item.get('machine', '')}"
                                for item in value
                            )
                        elif col == "UPSTREAM_MATERIALS" and isinstance(value, list):
                            value = ", ".join(
                                f"{item.get('part', '')}/{item.get('lot', '')}"
                                for item in value
                            )
                        csv_row.append(value)
                    writer.writerow(csv_row)
                yield buf.getvalue().encode("utf-8")

                pagination = detail.get("pagination") or {}
                if page >= int(pagination.get("total_pages") or page):
                    break
                page += 1
            return

        if not self._events_path:
            return

        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
            import io
            import csv

            conn = create_heavy_query_connection()
            conn.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{self._events_path}')")

            # Get column names
            cols_result = conn.execute("DESCRIBE events").fetchall()
            columns = [r[0] for r in cols_result]

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            yield buf.getvalue().encode("utf-8-sig")

            offset = 0
            while True:
                rows = conn.execute(
                    f"SELECT * FROM events LIMIT {chunk_size} OFFSET {offset}"
                ).fetchall()
                if not rows:
                    break
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerows(rows)
                yield buf.getvalue().encode("utf-8")
                offset += chunk_size

            conn.close()
        except Exception as exc:
            logger.warning("MsdDuckdbRuntime.export_csv failed: %s", exc)
