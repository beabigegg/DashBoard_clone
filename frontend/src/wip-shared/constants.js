export const NON_QUALITY_HOLD_REASONS = Object.freeze([
  'IQC檢驗(久存品驗證)(QC)',
  '大中/安波幅50pcs樣品留樣(PD)',
  '工程驗證(PE)',
  '工程驗證(RD)',
  '指定機台生產',
  '特殊需求(X-Ray全檢)',
  '特殊需求管控',
  '第一次量產QC品質確認(QC)',
  '需綁尾數(PD)',
  '樣品需求留存打樣(樣品)',
  '盤點(收線)需求',
]);

export const NON_QUALITY_HOLD_REASON_SET = new Set(NON_QUALITY_HOLD_REASONS);
