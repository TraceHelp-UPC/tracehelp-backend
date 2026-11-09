Feature: Diagnosis retrieval and HITL review API contract
  As an API consumer
  I want strict RBAC, state validations and RFC 7807 problem details on diagnosis endpoints
  So that unauthorized users or incomplete review payloads are reliably rejected

  Background:
    Given a workspace with users for every role

  Scenario: Unauthenticated request to get a diagnosis returns 401
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When an anonymous user requests the diagnosis of the ticket
    Then the response status is 401
    And the error is reported as problem details

  Scenario: Collaborator cannot view a diagnosis that is pending analyst review
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "COLLABORATOR" requests the diagnosis of the ticket
    Then the response status is 403
    And the error is reported as problem details

  Scenario: Collaborator can view a self-service proposal without internal scores
    Given a triaged ticket with a self-service proposal
    When the "COLLABORATOR" requests the diagnosis of the ticket
    Then the response status is 200
    And the diagnosis response has review status "SELF_SERVICE_PROPOSED"
    And the diagnosis response hides internal similarity scores and OCR details

  Scenario: Collaborator without HITL permission cannot review a diagnosis
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "COLLABORATOR" reviews the diagnosis with decision "APPROVE"
    Then the response status is 403
    And the error is reported as problem details

  Scenario: Requesting diagnosis of an untriaged ticket returns 404
    Given a ticket that is still waiting for automatic triage
    When the "ANALYST_L1" requests the diagnosis of the ticket
    Then the response status is 404
    And the error is reported as problem details

  Scenario: Reviewing a nonexistent diagnosis returns 404
    When the "ANALYST_L1" reviews a nonexistent diagnosis
    Then the response status is 404
    And the error is reported as problem details

  Scenario: Rejecting a diagnosis without a valid reason returns 400
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "ANALYST_L1" rejects the diagnosis with reason "no"
    Then the response status is 400
    And the error is reported as problem details
