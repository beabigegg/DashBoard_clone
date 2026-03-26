## ADDED Requirements

### Requirement: Tool prompt block generation
The system SHALL provide a `build_tool_prompt_block()` function that converts the YAML function registry into a prompt-friendly text block describing available tools, their purposes, and parameters. The output SHALL be embeddable in the agent system prompt.

#### Scenario: Prompt block includes Tier 1 tools
- **WHEN** `build_tool_prompt_block()` is called
- **THEN** the output SHALL contain descriptions for ~8-10 high-frequency tools (including `reject_summary`, `reject_reason_pareto`, `reject_trend`, `wip_summary`, `wip_matrix`, `dashboard_kpi`, `ou_trend`, `yield_summary`)
- **AND** each tool description SHALL include: tool name, Chinese description, parameter names with types and required/optional status

#### Scenario: Prompt block includes special tools
- **WHEN** `build_tool_prompt_block()` is called
- **THEN** the output SHALL include `query_database` (ad-hoc SQL queries) and `search_tools` (discover Tier 2 tools by keyword)
- **AND** these special tools are hardcoded, not from YAML

### Requirement: Two-tier tool strategy
The system SHALL implement a two-tier tool strategy: Tier 1 tools are always included in the prompt block; Tier 2 tools (remaining 30+ YAML tools) are discoverable via the `search_tools` meta-tool. The prompt block SHALL stay within ~1,500 tokens.

#### Scenario: Tier 2 tool discovery
- **WHEN** LLM calls `search_tools({"keyword": "追溯"})` during the agentic loop
- **THEN** the system SHALL search all YAML registry entries (including Tier 2) for matching tools
- **AND** return their names, descriptions, and parameter schemas

### Requirement: Agent system prompt construction
The system SHALL provide a `build_agent_system_prompt()` function that assembles the complete system prompt for agent mode, combining: role description, business context (from `ai_business_context.py`), tool prompt block, `<tool_call>` syntax instructions, clarification guidelines, response format rules, and current date.

#### Scenario: System prompt contains all required sections
- **WHEN** `build_agent_system_prompt()` is called
- **THEN** the output SHALL contain the role (MES AI 助手), business terminology (`BUSINESS_TERMINOLOGY`), system overview (`SYSTEM_OVERVIEW`), tool list, `<tool_call>` format instructions, clarification guidance, and the current date
- **AND** total length SHALL be within ~4,000 tokens

### Requirement: Single tool description formatting
The system SHALL provide a `build_single_tool_description(name, entry)` function that converts a single YAML registry entry into a prompt-friendly text description including the tool name, Chinese description, and parameter schema.

#### Scenario: Tool with required and optional parameters
- **WHEN** `build_single_tool_description("reject_trend", entry)` is called with an entry that has required params `start_date`, `end_date` and optional param `workcenter`
- **THEN** the output SHALL clearly indicate which parameters are required and which are optional
- **AND** include parameter types and enum values where applicable
