## MODIFIED Requirements

### Requirement: Hold Overview API SHALL accept lotid and workorder as exact-match filters
Hold Overview API endpoints (`/api/hold-overview/summary`, `/api/hold-overview/matrix`, `/api/hold-overview/lots`) SHALL document and implement `lotid` and `workorder` parameters as **exact match** (case-insensitive), not fuzzy/substring match.

#### Scenario: Summary with lotid exact filter
- **WHEN** `GET /api/hold-overview/summary?lotid=A100,B200` is called
- **THEN** the response SHALL only include hold lots where `LOTID` exactly equals `A100` or `B200`
- **THEN** lots where `LOTID` merely contains `A100` as a substring SHALL NOT be included

#### Scenario: Summary via POST avoids URL length limit
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "lotid": "<60+ comma-separated lot IDs>", "hold_type": "quality" }`
- **THEN** the response SHALL return HTTP 200 with `{ success: true }`
- **THEN** the service layer SHALL receive the same parameters as the equivalent GET request
- **THEN** filtering SHALL use exact match semantics

#### Scenario: Summary POST reason as JSON array
- **WHEN** `POST /api/hold-overview/summary` is called with JSON body `{ "reason": ["品質確認", "YieldLimit"] }`
- **THEN** the reason filter SHALL be applied as if `reason=品質確認,YieldLimit` was given in GET
