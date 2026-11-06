Feature: RESTful endpoints for diagnosis retrieval and HITL review
  As a TraceHelp API consumer
  I want to retrieve ticket diagnoses and submit human reviews with strict access and state control
  So that unauthorized users or duplicate reviews are rejected

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator
    And the ticket is in status "ASSIGNED_L1"
    And the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.88 for the ticket

  Scenario: Valid diagnosis review returns 200 OK
    When the "ANALYST_L1" reviews the diagnosis with action "APPROVE"
    Then the response status is 200
    And the diagnosis validation status is "APPROVED"

  Scenario: Review by user without validation permission returns 403 Forbidden
    When the "COLLABORATOR" reviews the diagnosis with action "APPROVE"
    Then the response status is 403

  Scenario: Reviewing an already reviewed diagnosis returns 409 Conflict
    Given the "ANALYST_L1" has already reviewed the diagnosis with action "APPROVE"
    When the "ANALYST_L1" reviews the diagnosis with action "REJECT"
    Then the response status is 409
