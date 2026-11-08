Feature: Collaborator ticket self-service and follow-up (US13)
  As a collaborator who reported an IT incident
  I want to search my tickets, inspect their details and screenshots, and confirm or reject solutions
  So that I can track my incidents end-to-end without seeing internal analyst notes or other users' tickets

  Background:
    Given a workspace with users for every role
    And another collaborator in the same workspace

  Scenario: Collaborator searches their own tickets by public code
    Given the collaborator has reported 3 tickets
    And the other collaborator has reported a ticket titled "Ticket de otro usuario"
    When the collaborator searches their ticket history by the code of "Incidente 2"
    Then the response status is 200
    And the page shows these tickets:
      | title       |
      | Incidente 2 |
    And the page does not show the ticket "Ticket de otro usuario"

  Scenario: Collaborator opens ticket detail with screenshots and downloads evidence as data URL
    Given a ticket reported by the collaborator with a screenshot "pantalla-error.png"
    When the collaborator opens the detail of their reported ticket
    Then the response status is 200
    And the ticket detail includes the screenshot "pantalla-error.png"
    When the collaborator requests the screenshot content of their reported ticket
    Then the response status is 200
    And the evidence response contains a PNG data URL for "pantalla-error.png"

  Scenario: Collaborator does not see internal analyst notes in ticket detail
    Given a ticket reported by the collaborator with a public comment and an internal note
    When the collaborator opens the detail of their reported ticket
    Then the response status is 200
    And the ticket detail shows only the public comment "Estamos revisando tu caso"
    And the ticket detail does not include any internal notes

  Scenario: Collaborator accepts the self-service solution and resolves the ticket
    Given a ticket reported by the collaborator
    And the ticket is in status "SELF_SERVICE_PROPOSED"
    When the "COLLABORATOR" changes the ticket status to "RESOLVED"
    Then the response status is 200
    And the response shows the ticket in status "RESOLVED"
    And the response shows the resolution date

  Scenario: Collaborator rejects the self-service solution and sends the ticket to the L1 queue
    Given a ticket reported by the collaborator
    And the ticket is in status "SELF_SERVICE_PROPOSED"
    When the "COLLABORATOR" changes the ticket status to "PENDING_ASSIGNMENT"
    Then the response status is 200
    And the response shows the ticket in status "PENDING_ASSIGNMENT"

  Scenario: Collaborator confirms closure of a resolved ticket
    Given a ticket reported by the collaborator
    And the ticket is in status "RESOLVED"
    When the "COLLABORATOR" changes the ticket status to "CLOSED"
    Then the response status is 200
    And the response shows the ticket in status "CLOSED"

  Scenario: Collaborator reopens a resolved ticket when the issue persists
    Given a ticket reported by the collaborator
    And the ticket is in status "RESOLVED"
    When the "COLLABORATOR" changes the ticket status to "REOPENED"
    Then the response status is 200
    And the response shows the ticket in status "REOPENED"
