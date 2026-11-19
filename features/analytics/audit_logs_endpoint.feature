Feature: Audit log REST endpoint
  As a developer or integrator with audit permission
  I want to consume GET /api/v1/audit/logs
  So that I can read the immutable history of operations processed by the AI, with pagination and filters

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator
    And a second ticket reported by the collaborator
    And the workspace audit log is empty

  # ------------------------------------------------------------------------------------- TS06, escenario 1
  Scenario: Paginated query with valid credentials and permission returns 200 with events and pagination metadata
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "page=2&size=10"
    Then the response status is 200
    And the audit page has 10 items, total 25, page 2 of 3 with size 10
    And the audit items are ordered from newest to oldest
    And the audit items are exactly: E10, E11, E12, E13, E14, E15, E16, E17, E18, E19
    And every audit item exposes only the documented fields

  Scenario: Query without parameters uses the defaults of page 1 and size 20
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs without query
    Then the response status is 200
    And the audit page has 20 items, total 25, page 1 of 2 with size 20

  Scenario: The last page holds the remaining entries
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "page=3&size=10"
    Then the response status is 200
    And the audit page has 5 items, total 25, page 3 of 3 with size 10
    And the audit items are exactly: E20, E21, E22, E23, E24

  Scenario: The maximum page size of 100 is accepted
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "size=100"
    Then the response status is 200
    And the audit page has 25 items, total 25, page 1 of 1 with size 100

  Scenario: An empty audit log answers 200 with an empty first page
    When the "IT_LEADER" requests the audit logs with query "page=1&size=10"
    Then the response status is 200
    And the audit items are empty

  Scenario: Only the entries of the workspace of the token are returned
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
    And an audit entry "FOREIGN" of type "TicketStatusChanged" exists in another workspace
    When the "IT_LEADER" requests the audit logs without query
    Then the response status is 200
    And the audit items are exactly: A1
    And every audit item belongs to the workspace of the token

  Scenario: Entries without actor are shown as "Sistema"
    Given these audit entries exist in the workspace:
      | label | event_type      | actor | ticket | occurred_at          |
      | S1    | TriageCompleted | -     | ticket | 2026-11-10T10:00:00Z |
    When the "IT_LEADER" requests the audit logs without query
    Then the response status is 200
    And the audit item "S1" shows the actor name "Sistema"

  # ------------------------------------------------------------------------------------- TS06, escenario 2
  Scenario Outline: A role without the audit:read permission receives 403 Forbidden
    Given the workspace audit log holds 3 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "<role>" requests the audit logs without query
    Then the response status is 403
    And the problem type is "forbidden"
    And the error detail says "Tu rol no tiene el permiso requerido: audit:read."

    Examples:
      | role          |
      | COLLABORATOR  |
      | ANALYST_L1    |
      | SPECIALIST_L2 |

  Scenario: The legacy alias also rejects a role without the audit:read permission
    When the "ANALYST_L1" requests the legacy audit log without query
    Then the response status is 403
    And the problem type is "forbidden"
    And the response has no header "Deprecation"

  Scenario: A request without token receives 401 Unauthorized
    When an unauthenticated client requests the audit logs without query
    Then the response status is 401
    And the problem type is "unauthorized"

  Scenario: A malformed token receives 401 Unauthorized
    When a client requests the audit logs with the token "not-a-valid-token"
    Then the response status is 401
    And the problem type is "unauthorized"

  Scenario: Authentication is checked before the pagination parameters (401 before 400)
    When an unauthenticated client requests the audit logs with query "page=0&size=500"
    Then the response status is 401
    And the problem type is "unauthorized"

  Scenario Outline: Authorization is checked before the parameters (403 before 400 and 422)
    When the "ANALYST_L1" requests the audit logs with query "<query>"
    Then the response status is 403
    And the problem type is "forbidden"

    Examples:
      | query                                                     |
      | page=0                                                    |
      | size=101                                                  |
      | page=abc                                                  |
      | from_date=2026-11-30T00:00:00Z&to_date=2026-11-01T00:00:00Z |
      | ticket_id=not-a-uuid                                      |

  # ------------------------------------------------------------------------------------- TS06, escenario 3
  Scenario Outline: Pagination parameters outside the allowed range receive 400 Bad Request
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "<query>"
    Then the response status is 400
    And the problem type is "invalid-page-request"
    And the error is reported as problem details

    Examples:
      | query           |
      | page=0          |
      | page=-1         |
      | size=0          |
      | size=-5         |
      | size=101        |
      | page=99&size=10 |
      | page=4&size=10  |

  Scenario: Requesting a page beyond the last one reports how many pages exist
    Given the workspace audit log holds 25 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "page=99&size=10"
    Then the response status is 400
    And the error detail says "La página 99 no existe: hay 3 página(s) de 10 resultados."

  Scenario: Requesting page 2 of an empty audit log receives 400 while page 1 is valid
    When the "IT_LEADER" requests the audit logs with query "page=2"
    Then the response status is 400
    And the problem type is "invalid-page-request"

  Scenario Outline: Non numeric pagination values are a validation error, not a range error
    When the "IT_LEADER" requests the audit logs with query "<query>"
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "<field>"

    Examples:
      | query     | field |
      | page=abc  | page  |
      | size=ten  | size  |
      | page=1.5  | page  |
      | size=     | size  |

  Scenario: The legacy alias applies the same pagination range check
    When the "IT_LEADER" requests the legacy audit log with query "size=101"
    Then the response status is 400
    And the problem type is "invalid-page-request"

  # ------------------------------------------------------------------------------------- Filtros
  Scenario: Filter by validator and event type returns only the entries of that validator
    Given these audit entries exist in the workspace:
      | label | event_type           | actor         | ticket       | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1    | ticket       | 2026-11-10T10:00:00Z |
      | A2    | AiResolutionReviewed | SPECIALIST_L2 | ticket       | 2026-11-11T10:00:00Z |
      | A3    | TicketStatusChanged  | ANALYST_L1    | other ticket | 2026-11-12T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "event_type=AiResolutionReviewed&actor_id=<actor:ANALYST_L1>"
    Then the response status is 200
    And the audit items are exactly: A1
    And the audit page has 1 items, total 1, page 1 of 1 with size 20

  Scenario: Filter by actor alone returns every kind of event of that actor
    Given these audit entries exist in the workspace:
      | label | event_type           | actor         | ticket       | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1    | ticket       | 2026-11-10T10:00:00Z |
      | A2    | AiResolutionReviewed | SPECIALIST_L2 | ticket       | 2026-11-11T10:00:00Z |
      | A3    | TicketStatusChanged  | ANALYST_L1    | other ticket | 2026-11-12T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "actor_id=<actor:ANALYST_L1>"
    Then the response status is 200
    And the audit items are exactly: A3, A1

  Scenario: Filter by an actor with no entries returns an empty page
    Given these audit entries exist in the workspace:
      | label | event_type           | actor      | ticket | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "actor_id=<actor:COLLABORATOR>"
    Then the response status is 200
    And the audit items are empty

  Scenario: Filter by ticket returns only the entries of that ticket
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket       | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket       | 2026-11-10T10:00:00Z |
      | A2    | TicketStatusChanged | ANALYST_L1 | other ticket | 2026-11-11T10:00:00Z |
      | A3    | TriageCompleted     | -          | ticket       | 2026-11-12T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "ticket_id=<other_ticket>"
    Then the response status is 200
    And the audit items are exactly: A2
    When the "IT_LEADER" requests the audit logs with query "ticket_id=<ticket>"
    Then the response status is 200
    And the audit items are exactly: A3, A1

  Scenario: Filter by event type is an exact, case sensitive match
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
      | A2    | TriageCompleted     | -          | ticket | 2026-11-11T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "event_type=TriageCompleted"
    Then the response status is 200
    And the audit items are exactly: A2
    When the "IT_LEADER" requests the audit logs with query "event_type=triagecompleted"
    Then the response status is 200
    And the audit items are empty
    When the "IT_LEADER" requests the audit logs with query "event_type=Triage"
    Then the response status is 200
    And the audit items are empty

  Scenario: An unknown event type returns an empty list, not an error
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "event_type=NoSuchEvent"
    Then the response status is 200
    And the audit items are empty

  Scenario: A blank event type is ignored
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "event_type=%20%20"
    Then the response status is 200
    And the audit items are exactly: A1

  Scenario: Filter by date range is inclusive at both ends
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
      | A2    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-11T10:00:00Z |
      | A3    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-12T10:00:00Z |
      | A4    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-13T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-11T10:00:00Z&to_date=2026-11-12T10:00:00Z"
    Then the response status is 200
    And the audit items are exactly: A3, A2
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-12T10:00:01Z"
    Then the audit items are exactly: A4
    When the "IT_LEADER" requests the audit logs with query "to_date=2026-11-10T09:59:59Z"
    Then the audit items are empty

  Scenario: Dates without time zone are interpreted as UTC regardless of the database session zone
    Given the database session time zone is "America/Lima"
    And these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T11:59:59Z |
      | A2    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T12:00:00Z |
      | A3    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T12:00:01Z |
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-10T12:00:00&to_date=2026-11-10T12:00:00"
    Then the response status is 200
    And the audit items are exactly: A2

  Scenario: Dates with a UTC offset are converted to the same instant
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T11:59:59Z |
      | A2    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T12:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-10T07:00:00-05:00"
    Then the response status is 200
    And the audit items are exactly: A2

  Scenario: Date, ticket, event type and actor filters combine
    Given these audit entries exist in the workspace:
      | label | event_type           | actor         | ticket       | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1    | ticket       | 2026-11-10T10:00:00Z |
      | A2    | AiResolutionReviewed | ANALYST_L1    | ticket       | 2026-11-15T10:00:00Z |
      | A3    | AiResolutionReviewed | ANALYST_L1    | other ticket | 2026-11-15T11:00:00Z |
      | A4    | AiResolutionReviewed | SPECIALIST_L2 | ticket       | 2026-11-15T12:00:00Z |
      | A5    | TicketStatusChanged  | ANALYST_L1    | ticket       | 2026-11-15T13:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-12T00:00:00Z&to_date=2026-11-20T00:00:00Z&ticket_id=<ticket>&event_type=AiResolutionReviewed&actor_id=<actor:ANALYST_L1>"
    Then the response status is 200
    And the audit items are exactly: A2
    And the audit page has 1 items, total 1, page 1 of 1 with size 20

  Scenario: Filters and pagination work together and total counts only the filtered entries
    Given these audit entries exist in the workspace:
      | label | event_type           | actor      | ticket | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
      | A2    | AiResolutionReviewed | ANALYST_L1 | ticket | 2026-11-11T10:00:00Z |
      | A3    | AiResolutionReviewed | ANALYST_L1 | ticket | 2026-11-12T10:00:00Z |
      | A4    | TicketStatusChanged  | ANALYST_L1 | ticket | 2026-11-13T10:00:00Z |
    When the "IT_LEADER" requests the audit logs with query "event_type=AiResolutionReviewed&page=2&size=2"
    Then the response status is 200
    And the audit page has 1 items, total 3, page 2 of 2 with size 2
    And the audit items are exactly: A1

  Scenario: An inverted date range receives 400 with its own problem type
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-30T00:00:00Z&to_date=2026-11-01T00:00:00Z"
    Then the response status is 400
    And the problem type is "invalid-date-range"
    And the error is reported as problem details

  Scenario: An inverted range is detected even when one date has no time zone
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-30T00:00:00&to_date=2026-11-01T00:00:00Z"
    Then the response status is 400
    And the problem type is "invalid-date-range"

  Scenario: A range with the same instant at both ends is valid
    When the "IT_LEADER" requests the audit logs with query "from_date=2026-11-10T12:00:00Z&to_date=2026-11-10T12:00:00Z"
    Then the response status is 200

  Scenario Outline: Parameters with an invalid type receive 422 Unprocessable Entity
    When the "IT_LEADER" requests the audit logs with query "<query>"
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "<field>"

    Examples:
      | query                               | field      |
      | ticket_id=not-a-uuid                | ticket_id  |
      | actor_id=12345                      | actor_id   |
      | from_date=yesterday                 | from_date  |
      | to_date=2026-13-45T00:00:00Z        | to_date    |

  Scenario: An event type longer than 80 characters receives 422
    When the "IT_LEADER" requests the audit logs with query "event_type=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    Then the response status is 422
    And the problem type is "validation-error"

  # ------------------------------------------------------------------------------------- Alias obsoleto
  Scenario: The deprecated alias answers the same as the canonical route and announces its successor
    Given these audit entries exist in the workspace:
      | label | event_type           | actor      | ticket | occurred_at          |
      | A1    | AiResolutionReviewed | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
      | A2    | TicketStatusChanged  | ANALYST_L1 | ticket | 2026-11-11T10:00:00Z |
    When the "IT_LEADER" requests both audit endpoints with query "actor_id=<actor:ANALYST_L1>&page=1&size=5"
    Then both audit responses have status 200 and the same body
    And the response header "Deprecation" is "true"
    And the response Link header points to the successor "/api/v1/audit/logs"
    And the canonical audit response has no deprecation headers

  Scenario: The deprecated alias accepts the new actor filter
    Given these audit entries exist in the workspace:
      | label | event_type          | actor         | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1    | ticket | 2026-11-10T10:00:00Z |
      | A2    | TicketStatusChanged | SPECIALIST_L2 | ticket | 2026-11-11T10:00:00Z |
    When the "IT_LEADER" requests the legacy audit log with query "actor_id=<actor:SPECIALIST_L2>"
    Then the response status is 200
    And the audit items are exactly: A2

  Scenario: The deprecated alias reports an inverted date range with the same problem type
    When the "IT_LEADER" requests the legacy audit log with query "from_date=2026-11-30T00:00:00Z&to_date=2026-11-01T00:00:00Z"
    Then the response status is 400
    And the problem type is "invalid-date-range"

  Scenario: The OpenAPI document declares the canonical route and marks the alias as deprecated
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI operation GET "/api/v1/audit/logs" is not marked deprecated
    And the OpenAPI operation GET "/api/v1/audit/logs" has the summary "Consultar la bitácora de auditoría"
    And the OpenAPI operation GET "/api/v1/audit/logs" declares the query parameters "page, size, from_date, to_date, ticket_id, event_type, actor_id"
    And the OpenAPI operation GET "/api/v1/audit/logs" documents the responses "200, 400, 401, 403, 422"
    And the OpenAPI operation GET "/api/v1/audit-log" is marked deprecated
    And the OpenAPI operation GET "/api/v1/audit-log" declares the query parameters "page, size, from_date, to_date, ticket_id, event_type, actor_id"

  # ------------------------------------------------------------------------------------- Orden e inmutabilidad
  Scenario: Entries are always listed from newest to oldest, independently of insertion order
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A2    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-11T10:00:00Z |
      | A4    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-13T10:00:00Z |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
      | A3    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-12T10:00:00Z |
    When the "IT_LEADER" requests the audit logs without query
    Then the audit items are exactly: A4, A3, A2, A1
    And the audit items are ordered from newest to oldest

  Scenario: A new entry recorded between two reads appears first and the total grows by one
    Given the workspace audit log holds 3 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    When the "IT_LEADER" requests the audit logs with query "size=10"
    Then the audit page has 3 items, total 3, page 1 of 1 with size 10
    When a new "TriageCompleted" entry "NEW" is recorded at "2026-11-10T12:05:00Z"
    And the "IT_LEADER" requests the audit logs with query "size=10"
    Then the audit page has 4 items, total 4, page 1 of 1 with size 10
    And the audit items are exactly: NEW, E00, E01, E02

  Scenario: Consulting the audit log does not write to it
    Given the workspace audit log holds 3 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    And the audit entries are counted
    When the "IT_LEADER" requests the audit logs without query
    And the "IT_LEADER" requests the legacy audit log without query
    And the "ANALYST_L1" requests the audit logs without query
    Then the audit entry count is unchanged

  Scenario Outline: The audit log cannot be modified or deleted through the API
    Given the workspace audit log holds 2 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    And the audit entries are counted
    When the "IT_LEADER" sends "<method>" to the audit logs
    Then the response status is 405
    And the audit entry count is unchanged

    Examples:
      | method |
      | PUT    |
      | PATCH  |
      | DELETE |
      | POST   |

  Scenario Outline: An individual audit entry cannot be modified or deleted through the API
    Given the workspace audit log holds 2 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    And the audit entries are counted
    When the "IT_LEADER" sends "<method>" to the audit entry "E00"
    Then the response status is 404
    And the audit entry count is unchanged

    Examples:
      | method |
      | PUT    |
      | PATCH  |
      | DELETE |

  Scenario Outline: The deprecated alias is read only as well
    Given the workspace audit log holds 2 "TicketStatusChanged" entries, one per minute, the newest at "2026-11-10T12:00:00Z"
    And the audit entries are counted
    When the "IT_LEADER" sends "<method>" to the legacy audit log
    Then the response status is 405
    And the audit entry count is unchanged

    Examples:
      | method |
      | PUT    |
      | PATCH  |
      | DELETE |

  Scenario: The OpenAPI document only exposes reading operations for the audit log
    When the client requests the OpenAPI document
    Then the OpenAPI path "/api/v1/audit/logs" only allows the methods "get"
    And the OpenAPI path "/api/v1/audit-log" only allows the methods "get"

  # ------------------------------------------------------------------------------------- Seguridad
  Scenario: The response does not leak credentials or personal data
    Given these audit entries exist in the workspace:
      | label | event_type          | actor      | ticket | occurred_at          |
      | A1    | TicketStatusChanged | ANALYST_L1 | ticket | 2026-11-10T10:00:00Z |
    When the "IT_LEADER" requests the audit logs without query
    Then the response status is 200
    And every audit item exposes only the documented fields
    And the audit response does not expose credentials or personal data
