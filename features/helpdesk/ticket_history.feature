Feature: Incident History and Detail Consultation (US13, T50, T51)
  As a collaborator
  I want to view my reported incident history and details
  So that I can monitor progress, view validated responses, and ensure my tickets remain private

  Scenario: Collaborator views their existing incident history
    Given an authenticated collaborator "carlos.mendoza@empresa.pe" with 2 reported tickets
    When the collaborator requests their ticket history
    Then the response status is 200
    And the history response contains 2 tickets

  Scenario: Collaborator with no tickets views empty history
    Given an authenticated collaborator "nuevo.empleado@empresa.pe" with no reported tickets
    When the collaborator requests their ticket history
    Then the response status is 200
    And the ticket history is empty

  Scenario: Collaborator cannot view another collaborator's ticket
    Given an authenticated collaborator "carlos.mendoza@empresa.pe"
    And a ticket reported by collaborator "maria.lopez@empresa.pe"
    When collaborator "carlos.mendoza@empresa.pe" attempts to view the ticket details
    Then the response status is 403
    And the response contains an access forbidden message

  Scenario: Collaborator views ticket details with validated response visible
    Given an authenticated collaborator "carlos.mendoza@empresa.pe"
    And a ticket reported by the collaborator with a validated public comment "Por favor reinicie el servicio VPN"
    When the collaborator requests the ticket details
    Then the response status is 200
    And the response contains the comment "Por favor reinicie el servicio VPN"
