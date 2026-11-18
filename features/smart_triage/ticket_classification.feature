Feature: Automatic ticket classification and analyst correction
  As a support analyst or IT leader
  I want triage to suggest a technical category and priority and allow analysts to correct them
  So that tickets are accurately categorized and audited

  Background:
    Given a workspace with users for every role
    And the knowledge base of the workspace has the VPN troubleshooting guide
    And the language model is simulated

  Scenario: Automatic triage suggests category and priority and applies them to the ticket
    Given the collaborator registered the ticket "VPN corporativa caída" with the description "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    When the automatic triage processes the ticket
    Then the ticket "VPN corporativa caída" is in status "PENDING_ASSIGNMENT"
    And the ticket has category "Red/VPN" and priority "HIGH"
    And the diagnosis of the ticket suggests category "Red/VPN" and priority "HIGH"

  Scenario: Incidents without sufficient evidence do not get an AI category suggestion
    Given the collaborator registered the ticket "Silla rota" with the description "La silla ergonómica de mi escritorio rechina mucho"
    When the automatic triage processes the ticket
    Then the ticket "Silla rota" is in status "PENDING_ASSIGNMENT"
    And the ticket has no category assigned
    And the diagnosis of the ticket has no suggested category

  Scenario: Analyst corrects the ticket classification and the change is audited
    Given the collaborator registered the ticket "Error de acceso" with the description "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    When the automatic triage processes the ticket
    And the "ANALYST_L1" corrects the classification of the ticket to category "Accesos" and priority "CRITICAL" with reason "Cuenta de directorio activo comprometida"
    Then the response status is 200
    And the ticket has category "Accesos" and priority "CRITICAL"
    And the audit log records a "TicketClassificationCorrected" event for the ticket with previous category "Red/VPN" and new category "Accesos"

  Scenario: Collaborators cannot correct the classification of a ticket
    Given the collaborator registered the ticket "Error VPN" with the description "Me sale el error 809 en la vpn"
    When the "COLLABORATOR" corrects the classification of the ticket to category "Hardware" and priority "LOW" with reason "Intento no autorizado"
    Then the response status is 403
    And the error is reported as problem details

  Scenario: Categories outside the catalog are rejected with 400
    Given the collaborator registered the ticket "Error VPN" with the description "Me sale el error 809 en la vpn"
    When the "ANALYST_L1" corrects the classification of the ticket to category "Mobiliario" and priority "LOW" with reason "Categoría inexistente"
    Then the response status is 400
    And the error is reported as problem details
