Feature: Audit log hash-chain integrity verification and ticket traceability (US21, T96/T99)
  As an IT Leader with audit:read permission
  I want to verify the cryptographic hash chain of audit entries and inspect full ticket traceability
  So that I can prove log immutability and audit every AI diagnosis, consulted source, and human decision

  # Nota (T99 / T96): Los escenarios de exportación CSV/PDF (`GET /api/v1/audit/logs/export` y 404 `no-data`)
  # corresponden a T97, que aún no forma parte de esta rama y se agregarán al integrar T97.

  Background:
    Given a workspace with users for every role
    And the workspace audit log is empty

  # ------------------------------------------------------------------------------------- Cadena de hashes y /verify
  Scenario: The genesis audit entry in a workspace has no previous_hash and verifies as VALID
    Given a chained audit sequence of 1 entries in the workspace
    When the "IT_LEADER" verifies the chained entry "C1"
    Then the response status is 200
    And the integrity verification result is "VALID" with valid true, hash_valid true and chain_valid true
    And the verification response reports a genesis entry with no predecessor
    And the verification stored_hash matches computed_hash

  Scenario: A 3-entry chained sequence verifies the third entry as VALID linked to the second
    Given a chained audit sequence of 3 entries in the workspace
    When the "IT_LEADER" verifies the chained entry "C3"
    Then the response status is 200
    And the integrity verification result is "VALID" with valid true, hash_valid true and chain_valid true
    And the verification links entry "C3" to predecessor "C2"
    And the audit log listing shows "C1", "C2", "C3" with monotonic seq and valid previous_hash links

  Scenario: Direct database tampering of an entry detail is detected as TAMPERED
    Given a chained audit sequence of 3 entries in the workspace
    When entry "C2" has its detail tampered directly in PostgreSQL
    And the "IT_LEADER" verifies the chained entry "C2"
    Then the response status is 200
    And the integrity verification result is "TAMPERED" with valid false, hash_valid false and chain_valid true
    And the verification stored_hash differs from computed_hash

  Scenario: Tampering a predecessor entry in PostgreSQL breaks the chain of the successor
    Given a chained audit sequence of 3 entries in the workspace
    When entry "C2" has its detail tampered directly in PostgreSQL
    And the "IT_LEADER" verifies the chained entry "C3"
    Then the response status is 200
    And the integrity verification result is "CHAIN_BROKEN" with valid false, hash_valid true and chain_valid false
    And the verification links entry "C3" to predecessor "C2"

  Scenario: Breaking previous_hash in PostgreSQL while keeping entry hash consistent reports CHAIN_BROKEN
    Given a chained audit sequence of 3 entries in the workspace
    When entry "C3" has its previous_hash replaced and its own hash recomputed in PostgreSQL
    And the "IT_LEADER" verifies the chained entry "C3"
    Then the response status is 200
    And the integrity verification result is "CHAIN_BROKEN" with valid false, hash_valid true and chain_valid false
    And the verification stored_previous_hash differs from expected_previous_hash

  # ------------------------------------------------------------------------------------- Trazabilidad por ticket (/trace)
  Scenario: Full traceability of a triaged and HITL-approved ticket returns sources, analyst and chronological events
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis and cited sources
    And the ticket has chained audit events for registration, triage, HITL approval by "ANALYST_L1", and resolution
    When the "IT_LEADER" requests the traceability of the traced ticket
    Then the response status is 200
    And the trace ticket summary shows status "RESOLVED" and reporter "COLLABORATOR"
    And the trace diagnosis shows outcome "ANSWERED", confidence "GROUNDED" and review_status "APPROVED"
    And the trace sources include 1 consulted source from "Manual VPN Corporativa v2"
    And the trace authorizing analyst is "ANALYST_L1" with decision "APPROVE"
    And the trace events are ordered chronologically with 4 events and all_hashes_valid true

  Scenario: Ticket traceability reports all_hashes_valid false when one of its events is tampered in PostgreSQL
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis and cited sources
    And the ticket has chained audit events for registration, triage, HITL approval by "ANALYST_L1", and resolution
    When the second traced ticket audit event is tampered directly in PostgreSQL
    And the "IT_LEADER" requests the traceability of the traced ticket
    Then the response status is 200
    And the trace reports all_hashes_valid false

  Scenario: Ticket without diagnosis or HITL review returns null diagnosis, empty sources and null authorizing analyst
    Given a newly registered ticket without AI diagnosis with a chained registration audit event
    When the "IT_LEADER" requests the traceability of the traced ticket
    Then the response status is 200
    And the trace diagnosis is null, sources are empty and authorizing_analyst is null
    And the trace events are ordered chronologically with 1 events and all_hashes_valid true

  Scenario: Rejected AI diagnosis followed by manual response resolves authorizing analyst to MANUAL_RESPONSE
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis and cited sources
    And the ticket has a rejected AI review followed by a manual response from "ANALYST_L1"
    When the "IT_LEADER" requests the traceability of the traced ticket
    Then the response status is 200
    And the trace authorizing analyst is "ANALYST_L1" with decision "MANUAL_RESPONSE"

  # ------------------------------------------------------------------------------------- Seguridad, errores y aislamiento
  Scenario Outline: Roles without audit:read receive 403 Forbidden on verify and trace endpoints
    Given a chained audit sequence of 1 entries in the workspace
    And a newly registered ticket without AI diagnosis with a chained registration audit event
    When the "<role>" requests "<endpoint>" for the audit integrity resources
    Then the response status is 403
    And the problem type is "forbidden"

    Examples:
      | role          | endpoint |
      | COLLABORATOR  | verify   |
      | ANALYST_L1    | verify   |
      | SPECIALIST_L2 | verify   |
      | COLLABORATOR  | trace    |
      | ANALYST_L1    | trace    |
      | SPECIALIST_L2 | trace    |

  Scenario Outline: Unauthenticated or malformed token requests receive 401 Unauthorized on verify and trace
    Given a chained audit sequence of 1 entries in the workspace
    And a newly registered ticket without AI diagnosis with a chained registration audit event
    When an unauthenticated client with auth "<auth>" requests "<endpoint>"
    Then the response status is 401
    And the problem type is "unauthorized"

    Examples:
      | auth          | endpoint |
      | none          | verify   |
      | invalid-token | verify   |
      | none          | trace    |
      | invalid-token | trace    |

  Scenario: Verifying a nonexistent entry or an entry from another workspace returns 404 audit-entry-not-found
    Given a chained audit sequence of 1 entries in the workspace
    And a second workspace exists with its own chained entry "FOREIGN_1" and ticket "FOREIGN_TICKET"
    When the "IT_LEADER" verifies a nonexistent audit entry UUID
    Then the response status is 404
    And the problem type is "audit-entry-not-found"
    When the "IT_LEADER" verifies the foreign workspace entry "FOREIGN_1"
    Then the response status is 404
    And the problem type is "audit-entry-not-found"

  Scenario: Requesting trace for a nonexistent ticket or a ticket from another workspace returns 404 ticket-not-found
    Given a second workspace exists with its own chained entry "FOREIGN_1" and ticket "FOREIGN_TICKET"
    When the "IT_LEADER" requests the traceability of a nonexistent ticket UUID
    Then the response status is 404
    And the problem type is "ticket-not-found"
    When the "IT_LEADER" requests the traceability of the foreign workspace ticket "FOREIGN_TICKET"
    Then the response status is 404
    And the problem type is "ticket-not-found"

  Scenario Outline: Invalid UUID path parameters return 422 validation-error
    When the "IT_LEADER" requests "<endpoint>" with invalid UUID "not-a-uuid"
    Then the response status is 422
    And the problem type is "validation-error"

    Examples:
      | endpoint |
      | verify   |
      | trace    |

  Scenario: Hash chains are isolated per workspace with independent genesis entries
    Given a chained audit sequence of 2 entries in the workspace
    And a second workspace exists with its own chained entry "FOREIGN_1" and ticket "FOREIGN_TICKET"
    Then the foreign entry "FOREIGN_1" is a genesis entry with previous_hash null
    And the local entry "C1" is a genesis entry and "C2" links to "C1"

  Scenario: OpenAPI documents the verify and trace endpoints with expected responses
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI path "/api/v1/audit/logs/{entry_id}/verify" only allows the methods "get"
    And the OpenAPI operation GET "/api/v1/audit/logs/{entry_id}/verify" documents the responses "200, 401, 403, 404, 422"
    And the OpenAPI path "/api/v1/audit/tickets/{ticket_id}/trace" only allows the methods "get"
    And the OpenAPI operation GET "/api/v1/audit/tickets/{ticket_id}/trace" documents the responses "200, 401, 403, 404, 422"
