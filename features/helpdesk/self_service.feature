Feature: Self-service triage recommendation and collaborator resolution (US12)
  As a non-technical collaborator
  I want to receive a high-confidence self-service solution and either accept it or request an analyst
  So that simple incidents are resolved immediately while complex cases reach L1 support with full context

  Background:
    Given a workspace with users for every role

  Scenario: High-confidence triage exposes a safe recommendation and acceptance resolves the ticket
    Given a newly registered ticket "VPN error 809" waiting for automatic triage
    When automatic triage runs with similarity score 0.89 and self-service threshold 0.80
    Then the self-service ticket is in status "SELF_SERVICE_PROPOSED" and tier "SELF_SERVICE"
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the response status is 200
    And the ticket detail exposes a self-service recommendation with match percentage 89 and label "Alta coincidencia"
    And the self-service recommendation hides internal triage fields
    When the "COLLABORATOR" accepts the self-service recommendation
    Then the response status is 200
    And the response ticket has status "RESOLVED", tier "SELF_SERVICE" and a resolution timestamp
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the ticket detail has no self-service recommendation
    And the self-service ticket history records the transition from "SELF_SERVICE_PROPOSED" to "RESOLVED"
    And the audit log records "SelfServiceAccepted" for the self-service ticket with outcome "RESOLVED_BY_SELF_SERVICE"
    When the "ANALYST_L1" tries to approve the self-service diagnosis in HITL
    Then the response status is 409

  Scenario: Rejecting self-service with a reason returns the ticket to L1 and reopens diagnosis for HITL review
    Given a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    When the "COLLABORATOR" rejects the self-service recommendation with reason "Sigue fallando para carlos@empresa.pe desde 10.0.0.15"
    Then the response status is 200
    And the response ticket has status "PENDING_ASSIGNMENT", tier "TIER_L1" and no assigned analyst
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the ticket detail has no self-service recommendation
    And the self-service diagnosis is in review status "PENDING_REVIEW"
    When the "ANALYST_L1" takes the self-service ticket and approves its diagnosis in HITL
    Then the response status is 200
    And the HITL approval resolves the ticket with diagnosis status "APPROVED"
    And the audit log records "SelfServiceRejected" for the self-service ticket with masked reason

  Scenario Outline: Rejecting self-service without a reason also derives the ticket and reopens diagnosis
    Given a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    When the "COLLABORATOR" rejects the self-service recommendation <variant>
    Then the response status is 200
    And the response ticket has status "PENDING_ASSIGNMENT", tier "TIER_L1" and no assigned analyst
    And the self-service diagnosis is in review status "PENDING_REVIEW"

    Examples:
      | variant                |
      | without a request body |
      | with an empty payload  |
      | with a blank reason    |

  Scenario: Insufficient evidence routes the ticket to L1 without a self-service recommendation
    Given a newly registered ticket "Silla ergonómica" waiting for automatic triage
    When automatic triage runs with similarity score 0.45 and self-service threshold 0.80
    Then the self-service ticket is in status "PENDING_ASSIGNMENT" and tier "TIER_L1"
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the response status is 200
    And the ticket detail has no self-service recommendation

  Scenario: Grounded diagnosis below the self-service threshold hides the recommendation and keeps internal diagnosis restricted
    Given a newly registered ticket "VPN lenta" waiting for automatic triage
    When automatic triage runs with similarity score 0.75 and self-service threshold 0.80
    Then the self-service ticket is in status "PENDING_ASSIGNMENT" and tier "TIER_L1"
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the response status is 200
    And the ticket detail has no self-service recommendation
    When the "COLLABORATOR" requests the internal diagnosis of the self-service ticket
    Then the response status is 403

  Scenario Outline: Ticket detail hides recommendation outside SELF_SERVICE_PROPOSED or when diagnosis is pending review
    Given a self-service setup with ticket status "<ticket_status>" and diagnosis review status "<review_status>"
    When the "COLLABORATOR" requests the detail of the self-service ticket
    Then the response status is 200
    And the ticket detail has no self-service recommendation

    Examples:
      | ticket_status         | review_status         |
      | OPEN                  | SELF_SERVICE_PROPOSED |
      | PENDING_ASSIGNMENT    | SELF_SERVICE_PROPOSED |
      | ASSIGNED_L1           | SELF_SERVICE_PROPOSED |
      | RESOLVED              | SELF_SERVICE_PROPOSED |
      | SELF_SERVICE_PROPOSED | PENDING_REVIEW        |

  Scenario Outline: Only the reporting collaborator can accept or reject a self-service recommendation
    Given another collaborator in the same workspace
    And a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    When the actor "<actor>" calls self-service "<action>" on the ticket
    Then the response status is 403
    And the error is reported as problem details
    And the problem type is "ticket-status-change-forbidden"

    Examples:
      | actor              | action |
      | ANALYST_L1         | accept |
      | SPECIALIST_L2      | accept |
      | IT_LEADER          | accept |
      | OTHER_COLLABORATOR | accept |
      | ANALYST_L1         | reject |
      | SPECIALIST_L2      | reject |
      | IT_LEADER          | reject |
      | OTHER_COLLABORATOR | reject |

  Scenario Outline: Self-service accept or reject is rejected when the ticket is not in SELF_SERVICE_PROPOSED
    Given a self-service setup with ticket status "<status>" and diagnosis review status "SELF_SERVICE_PROPOSED"
    When the "COLLABORATOR" calls self-service "<action>" on the ticket
    Then the response status is 422
    And the error is reported as problem details
    And the problem type is "invalid-ticket-state-transition"

    Examples:
      | status             | action |
      | OPEN               | accept |
      | PENDING_ASSIGNMENT | accept |
      | ASSIGNED_L1        | accept |
      | RESOLVED           | accept |
      | CLOSED             | accept |
      | OPEN               | reject |
      | PENDING_ASSIGNMENT | reject |
      | ASSIGNED_L1        | reject |
      | RESOLVED           | reject |
      | CLOSED             | reject |

  Scenario: Rejecting self-service validates reason max length and forbids extra fields
    Given a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    When the "COLLABORATOR" rejects the self-service recommendation with a reason of 501 characters
    Then the response status is 422
    And the error is reported as problem details
    And the problem type is "validation-error"
    And the first error field is "reason"
    When the "COLLABORATOR" rejects the self-service recommendation with an unknown field
    Then the response status is 422
    And the problem type is "validation-error"

  Scenario Outline: Self-service endpoints return 404 for nonexistent or foreign-workspace tickets
    Given a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    And a collaborator from another workspace
    When the "<target>" ticket receives a self-service "<action>" call
    Then the response status is 404
    And the error is reported as problem details
    And the problem type is "ticket-not-found"

    Examples:
      | target      | action |
      | nonexistent | accept |
      | nonexistent | reject |
      | foreign     | accept |
      | foreign     | reject |

  Scenario Outline: Self-service endpoints require authentication
    Given a ticket in status "SELF_SERVICE_PROPOSED" with an eligible self-service diagnosis
    When an anonymous user calls self-service "<action>" on the ticket
    Then the response status is 401
    And the error is reported as problem details

    Examples:
      | action |
      | accept |
      | reject |

  Scenario: OpenAPI documents the self-service endpoints and recommendation field
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI document documents self-service endpoints and TicketDetailResponse recommendation
