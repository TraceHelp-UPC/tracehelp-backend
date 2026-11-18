Feature: Ticket status change history and escalation
  As a collaborator or a support analyst
  I want every status transition of a ticket recorded with its actor and reason
  So that I can audit the full timeline of escalations, returns and resolutions

  Background:
    Given a workspace with users for every role
    And another collaborator in the same workspace
    And a ticket reported by the collaborator

  Scenario: Analyst escalates a ticket with a reason, specialist returns it, and analyst resolves it
    When the automatic triage routes the ticket to "PENDING_ASSIGNMENT" with reason "Requiere validación de un analista"
    And the "ANALYST_L1" changes the ticket status to "ASSIGNED_L1" with reason "Tomo el caso desde la bandeja"
    And the "ANALYST_L1" changes the ticket status to "ESCALATED_L2" with reason "Requiere permisos de firewall L2"
    And the "SPECIALIST_L2" changes the ticket status to "ASSIGNED_L1" with reason "Puertos habilitados, validar con usuario"
    And the "ANALYST_L1" changes the ticket status to "RESOLVED" with reason "Conexión VPN restablecida"
    And the "COLLABORATOR" requests the status history of the ticket
    Then the response status is 200
    And the status history shows these transitions in chronological order:
      | previous_status    | new_status         | changed_by_name      | reason                                   |
      | OPEN               | PENDING_ASSIGNMENT | Sistema              | Requiere validación de un analista       |
      | PENDING_ASSIGNMENT | ASSIGNED_L1        | ANALYST_L1 Demo      | Tomo el caso desde la bandeja            |
      | ASSIGNED_L1        | ESCALATED_L2       | ANALYST_L1 Demo      | Requiere permisos de firewall L2         |
      | ESCALATED_L2       | ASSIGNED_L1        | SPECIALIST_L2 Demo   | Puertos habilitados, validar con usuario |
      | ASSIGNED_L1        | RESOLVED           | ANALYST_L1 Demo      | Conexión VPN restablecida                |

  Scenario: Collaborator cannot view the status history of another collaborator's ticket
    When the other collaborator requests the status history of the ticket
    Then the response status is 403
    And the error is reported as problem details

  Scenario: Requesting status history of a nonexistent ticket returns 404
    When the "ANALYST_L1" requests the status history of a nonexistent ticket
    Then the response status is 404
    And the error is reported as problem details
