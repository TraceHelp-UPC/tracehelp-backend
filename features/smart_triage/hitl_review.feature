Feature: Human-in-the-loop review of AI diagnoses
  As a support analyst
  I want to approve, edit, reject or manually replace AI diagnoses before they reach the collaborator
  So that every response is verified by a human and recorded in the audit log

  Background:
    Given a workspace with users for every role

  Scenario: Approving the AI diagnosis resolves the ticket with the AI answer
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "ANALYST_L1" reviews the diagnosis with decision "APPROVE"
    Then the response status is 200
    And the review resolves the ticket with status "APPROVED"
    And the ticket has a visible comment starting with "Puertos bloqueados [F1]."
    And the audit log records an "AiResolutionReviewed" event with decision "APPROVE"

  Scenario: Editing and approving saves the edited text for the collaborator
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "ANALYST_L1" edits and approves the diagnosis with summary "El router bloquea los puertos." and step "Reinicia el router corporativo."
    Then the response status is 200
    And the review resolves the ticket with status "EDITED_AND_APPROVED"
    And the ticket has a visible comment starting with "El router bloquea los puertos."

  Scenario: Rejecting the AI diagnosis keeps the ticket in ASSIGNED_L1 and allows a manual response
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "ANALYST_L1" rejects the diagnosis with reason "El manual corresponde a otra versión de la VPN"
    Then the response status is 200
    And the review does not resolve the ticket and leaves diagnosis in "REJECTED"
    When the "ANALYST_L1" responds manually to the diagnosis with "Reinstalé tu perfil VPN; intenta conectarte nuevamente."
    Then the response status is 200
    And the review resolves the ticket with status "MANUAL_RESPONSE"
    And the ticket has a visible comment starting with "Reinstalé tu perfil VPN"

  Scenario: Reviewing an already approved diagnosis is rejected with 409
    Given a triaged ticket in status "ASSIGNED_L1" with a pending AI diagnosis
    When the "ANALYST_L1" reviews the diagnosis with decision "APPROVE"
    And the "SPECIALIST_L2" reviews the diagnosis with decision "APPROVE"
    Then the response status is 409
    And the error detail mentions "ya fue revisado"

  Scenario: Analyst must attend the ticket before reviewing its diagnosis
    Given a triaged ticket in status "PENDING_ASSIGNMENT" with a pending AI diagnosis
    When the "ANALYST_L1" reviews the diagnosis with decision "APPROVE"
    Then the response status is 422
    And the error detail mentions "Atender"
