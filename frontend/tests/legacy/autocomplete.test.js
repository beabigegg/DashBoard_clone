import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildWipAutocompleteParams,
  fetchWipAutocompleteItems,
} from '../../src/core/autocomplete.js';

test('buildWipAutocompleteParams keeps cross-filters except active field', () => {
  const params = buildWipAutocompleteParams('lotid', 'L123', {
    workorder: 'WO1',
    lotid: 'L999',
    package: 'PKG-A',
    type: 'QFN'
  });

  assert.equal(params.field, 'lotid');
  assert.equal(params.q, 'L123');
  assert.equal(params.workorder, 'WO1');
  assert.equal(params.package, 'PKG-A');
  assert.equal(params.type, 'QFN');
  assert.equal(Object.prototype.hasOwnProperty.call(params, 'lotid'), false);
});

test('buildWipAutocompleteParams returns null for short query', () => {
  const params = buildWipAutocompleteParams('workorder', 'a', {});
  assert.equal(params, null);
});

test('fetchWipAutocompleteItems maps successful API response', async () => {
  const items = await fetchWipAutocompleteItems({
    searchType: 'workorder',
    query: 'WO',
    filters: {},
    request: async () => ({
      success: true,
      data: {
        items: ['WO1', 'WO2']
      }
    })
  });

  assert.deepEqual(items, ['WO1', 'WO2']);
});

test('fetchWipAutocompleteItems swallows API errors and returns empty list', async () => {
  const items = await fetchWipAutocompleteItems({
    searchType: 'workorder',
    query: 'WO',
    filters: {},
    request: async () => {
      throw new Error('network down');
    }
  });

  assert.deepEqual(items, []);
});
