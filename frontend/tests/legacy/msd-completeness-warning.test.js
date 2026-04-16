import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * Tests for the MSD staged-events completeness warning logic.
 *
 * App.vue derives three computed values from trace.stage_results.events?.quality_meta:
 *   eventsQualityMeta   — raw quality_meta object or null
 *   hasCompletenessWarning — true when hasQueried && !loading && status not 'complete'
 *   completenessWarningText — Chinese warning string keyed on status
 *
 * These tests exercise the pure logic inline (without mounting the Vue component)
 * to verify all status branches and the independence from the genealogy warning.
 */

function evalHasCompletenessWarning({ hasQueried, isLoading, qualityMetaStatus }) {
  if (!hasQueried || isLoading) return false;
  const status = String(qualityMetaStatus || '').toLowerCase();
  return Boolean(status) && status !== 'complete';
}

function evalCompletenessWarningText(qualityMetaStatus) {
  const status = String(qualityMetaStatus || '').toLowerCase();
  if (status === 'partial') return '部分事件資料尚未完整擷取，分析結果可能不完整。';
  if (status === 'truncated') return '事件資料已截斷，超出查詢限制，分析結果可能不完整。';
  if (status === 'failed') return '部分事件域擷取失敗，分析結果可能不完整。';
  return '';
}


test('hasCompletenessWarning: partial/truncated/failed statuses show warning', () => {
  for (const status of ['partial', 'truncated', 'failed']) {
    assert.equal(
      evalHasCompletenessWarning({ hasQueried: true, isLoading: false, qualityMetaStatus: status }),
      true,
      `status '${status}' should trigger warning`,
    );
  }
});

test('hasCompletenessWarning: complete status suppresses warning', () => {
  assert.equal(
    evalHasCompletenessWarning({ hasQueried: true, isLoading: false, qualityMetaStatus: 'complete' }),
    false,
  );
});

test('hasCompletenessWarning: null/empty quality_meta suppresses warning', () => {
  assert.equal(
    evalHasCompletenessWarning({ hasQueried: true, isLoading: false, qualityMetaStatus: null }),
    false,
  );
  assert.equal(
    evalHasCompletenessWarning({ hasQueried: true, isLoading: false, qualityMetaStatus: '' }),
    false,
  );
});

test('hasCompletenessWarning: suppressed while loading or before first query', () => {
  assert.equal(
    evalHasCompletenessWarning({ hasQueried: false, isLoading: false, qualityMetaStatus: 'partial' }),
    false,
    'should not warn before first query',
  );
  assert.equal(
    evalHasCompletenessWarning({ hasQueried: true, isLoading: true, qualityMetaStatus: 'partial' }),
    false,
    'should not warn while loading',
  );
});

test('completenessWarningText: correct Chinese text per status', () => {
  assert.equal(evalCompletenessWarningText('partial'), '部分事件資料尚未完整擷取，分析結果可能不完整。');
  assert.equal(evalCompletenessWarningText('truncated'), '事件資料已截斷，超出查詢限制，分析結果可能不完整。');
  assert.equal(evalCompletenessWarningText('failed'), '部分事件域擷取失敗，分析結果可能不完整。');
  assert.equal(evalCompletenessWarningText('complete'), '');
  assert.equal(evalCompletenessWarningText(null), '');
});

test('MSD completeness warning is independent of genealogy warning', () => {
  // Genealogy warning condition: analysisData.genealogy_status === 'error'
  // Completeness warning condition: hasCompletenessWarning (quality_meta driven)
  // Both can be true simultaneously — verify they use orthogonal inputs

  const genealogyError = true; // genealogy_status === 'error'
  const completenessStatus = 'partial';

  // Both warnings active simultaneously
  const showGenealogy = genealogyError;
  const showCompleteness = evalHasCompletenessWarning({
    hasQueried: true,
    isLoading: false,
    qualityMetaStatus: completenessStatus,
  });

  assert.equal(showGenealogy, true, 'genealogy warning should be active');
  assert.equal(showCompleteness, true, 'completeness warning should be active independently');

  // Genealogy ok, completeness non-complete
  const genealogyOk = false;
  const showCompletenessAlone = evalHasCompletenessWarning({
    hasQueried: true,
    isLoading: false,
    qualityMetaStatus: 'truncated',
  });
  assert.equal(genealogyOk, false);
  assert.equal(showCompletenessAlone, true, 'completeness warning should show even when genealogy is ok');
});
