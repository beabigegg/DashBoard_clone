## MODIFIED Requirements

### Requirement: EventFetcher SHALL separate records payload from quality metadata
`EventFetcher` SHALL return domain records and completeness metadata as separate structures, and SHALL NOT inject metadata entries into the `CONTAINERID -> records` map.

#### Scenario: Truncation metadata is separated from records
- **WHEN** total fetched rows for a domain reaches `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL stop adding more records for that domain
- **THEN** EventFetcher SHALL return `quality_meta.status = "truncated"` with row-limit details
- **THEN** returned records map SHALL contain only container-id keys mapped to record arrays

#### Scenario: Normal domain query has complete metadata
- **WHEN** a domain query completes without truncation/failure
- **THEN** EventFetcher SHALL return `quality_meta.status = "complete"`
- **THEN** EventFetcher SHALL still return records map in the same structural shape used by callers

### Requirement: EventFetcher truncation SHALL remain configurable and observable
Truncation behavior SHALL remain controlled by environment configuration and visible in logs/metadata.

#### Scenario: Configurable total-row guard
- **WHEN** operator sets `EVENT_FETCHER_MAX_TOTAL_ROWS`
- **THEN** EventFetcher SHALL enforce the configured limit at runtime
- **THEN** returned `quality_meta` SHALL include the effective limit value

#### Scenario: Truncation observability
- **WHEN** truncation is triggered
- **THEN** a warning log SHALL include domain, observed rows, and row limit
- **THEN** caller-facing metadata SHALL expose the same truncation context
