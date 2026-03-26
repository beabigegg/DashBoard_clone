## ADDED Requirements

### Requirement: Hold Detail Dynamic Rendering MUST Sanitize Untrusted Values
Dynamic table and distribution rendering in hold-detail SHALL sanitize untrusted text before injecting into HTML attributes or content.

#### Scenario: Hold reason distribution contains HTML-like payload
- **WHEN** workcenter/package/lot fields include HTML-like text from upstream data
- **THEN** the hold-detail page MUST render escaped text and MUST NOT execute embedded markup or scripts
