# -*- coding: utf-8 -*-
"""Field contract governance tests."""

from __future__ import annotations

import csv
import io
from unittest.mock import patch

import pandas as pd

from mes_dashboard.config.field_contracts import (
    get_page_contract,
    get_export_api_keys,
    get_export_headers,
)
from mes_dashboard.services.job_query_service import export_jobs_with_history
from mes_dashboard.services.resource_history_service import export_csv as export_resource_history_csv


def test_contract_sections_exist_for_primary_pages():
    for page, section in [
        ('job_query', 'jobs_table'),
        ('job_query', 'txn_table'),
        ('job_query', 'export'),
        ('resource_history', 'detail_table'),
        ('resource_history', 'export'),
        ('tables', 'result_table'),
        ('excel_query', 'result_table'),
        ('resource_status', 'matrix_summary'),
    ]:
        contract = get_page_contract(page, section)
        assert contract, f"missing contract for {page}:{section}"


def test_export_contracts_have_no_duplicate_api_keys():
    for page in ['job_query', 'resource_history']:
        keys = [field.get('api_key') for field in get_page_contract(page, 'export')]
        assert len(keys) == len(set(keys))


def test_export_headers_and_keys_have_same_length():
    for page in ['job_query', 'resource_history']:
        headers = get_export_headers(page)
        keys = get_export_api_keys(page)
        assert headers
        assert keys
        assert len(headers) == len(keys)


def test_all_contract_fields_define_semantic_type():
    pages_and_sections = [
        ('job_query', 'jobs_table'),
        ('job_query', 'txn_table'),
        ('job_query', 'export'),
        ('resource_history', 'detail_table'),
        ('resource_history', 'kpi'),
        ('resource_history', 'export'),
        ('tables', 'result_table'),
        ('excel_query', 'result_table'),
        ('resource_status', 'matrix_summary'),
    ]
    for page, section in pages_and_sections:
        for field in get_page_contract(page, section):
            assert field.get('semantic_type'), f"missing semantic_type in {page}:{section}:{field}"


@patch('mes_dashboard.services.job_query_service.SQLLoader.load', return_value='SELECT 1')
def test_job_query_export_uses_contract_headers(_mock_sql):
    export_keys = get_export_api_keys('job_query')
    export_headers = get_export_headers('job_query')

    row = {key: f'v_{idx}' for idx, key in enumerate(export_keys)}
    row['JOB_CREATEDATE'] = pd.Timestamp('2024-01-01 10:00:00')
    row['JOB_COMPLETEDATE'] = pd.Timestamp('2024-01-02 10:00:00')
    row['TXNDATE'] = pd.Timestamp('2024-01-02 11:00:00')
    df = pd.DataFrame([row], columns=export_keys)

    with patch('mes_dashboard.services.job_query_service.read_sql_df', return_value=df):
        chunks = list(export_jobs_with_history(['R1'], '2024-01-01', '2024-01-10'))

    assert chunks
    header_chunk = chunks[0].lstrip('\ufeff')
    header_row = next(csv.reader(io.StringIO(header_chunk)))
    assert header_row == export_headers


@patch('mes_dashboard.services.resource_history_service.SQLLoader.load', return_value='SELECT 1')
@patch('mes_dashboard.services.resource_history_service.read_sql_df')
@patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
def test_resource_history_export_uses_contract_headers(
    mock_wc_mapping,
    mock_read_sql,
    _mock_sql_loader,
):
    export_headers = get_export_headers('resource_history')

    mock_wc_mapping.return_value = {
        'WC-A': {'group': '站點-A', 'sequence': 1}
    }

    mock_read_sql.return_value = pd.DataFrame([
        {
            'HISTORYID': 'RES-A',
            'PRD_HOURS': 10,
            'SBY_HOURS': 2,
            'UDT_HOURS': 1,
            'SDT_HOURS': 1,
            'EGT_HOURS': 1,
            'NST_HOURS': 1,
            'TOTAL_HOURS': 16,
        }
    ])

    with patch('mes_dashboard.services.resource_history_service._get_filtered_resources', return_value=[
        {
            'RESOURCEID': 'RES-A',
            'WORKCENTERNAME': 'WC-A',
            'RESOURCEFAMILYNAME': 'FAM-A',
            'RESOURCENAME': 'EQ-A',
        }
    ]):
        chunks = list(export_resource_history_csv('2024-01-01', '2024-01-10'))

    assert chunks
    header_row = next(csv.reader(io.StringIO(chunks[0])))
    assert header_row == export_headers
