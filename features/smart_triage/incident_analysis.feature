Feature: Multimodal incident analysis with RAG
  As a support analyst
  I want the incident text and screenshot analyzed against the company manuals
  So that I get a diagnosis with citations and a confidence score instead of starting from scratch

  The language model (Gemini) is simulated in every scenario: no real API is called.

  Background:
    Given a workspace with users for every role
    And the knowledge base of the workspace has the VPN troubleshooting guide
    And the language model is simulated

  Scenario: Successful diagnosis from the incident description
    When the "ANALYST_L1" analyzes the incident "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    Then the response status is 200
    And the analysis status is "ANSWERED" with confidence level "GROUNDED"
    And the confidence score is above the similarity threshold
    And the diagnosis cites "guia-vpn.md, sección «Error 809», párr. 1"
    And every step of the diagnosis cites a source

  Scenario: Successful diagnosis from a screenshot of the error
    When the "ANALYST_L1" analyzes the incident "No puedo entrar a la red de la empresa" with a screenshot of the error
    Then the response status is 200
    And the analysis status is "ANSWERED" with confidence level "GROUNDED"
    And the screenshot was read with the error codes "Error 809, 0x80070005"

  Scenario: Personal data never reaches the language model
    When the "ANALYST_L1" analyzes the incident "Soy ana.diaz@empresa.pe desde 10.0.0.15, la vpn me da el error 809 en los puertos udp"
    Then the response status is 200
    And the language model did not receive "ana.diaz@empresa.pe"
    And the language model did not receive "10.0.0.15"

  Scenario: Incidents not covered by the manuals are not answered by the AI
    When the "ANALYST_L1" analyzes the incident "La silla ergonómica de mi escritorio rechina mucho"
    Then the response status is 200
    And the analysis status is "INSUFFICIENT_EVIDENCE" with confidence level "LOW_CONFIDENCE"
    And the language model was not called

  Scenario Outline: Missing incident data is rejected with 400
    When the "ANALYST_L1" analyzes the incident "<description>"
    Then the response status is 400
    And the error is reported as problem details
    And the error detail mentions "<message>"

    Examples:
      | description | message                             |
      |             | Describe el problema o adjunta      |
      | error       | Describe el problema con más detalle |

  Scenario: The workspace id is required
    When the "ANALYST_L1" analyzes an incident without the workspace id
    Then the response status is 422

  Scenario: Analyzing against a workspace that does not exist
    When the "ANALYST_L1" analyzes the incident "La vpn me da el error 809" in a workspace that does not exist
    Then the response status is 404
    And the error detail mentions "El workspace no existe"

  Scenario: The language model is unavailable
    Given the language model is unavailable
    When the "ANALYST_L1" analyzes the incident "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    Then the response status is 502
    And the error detail mentions "La IA no respondió"

  Scenario: Collaborators cannot call the analysis directly
    When the "COLLABORATOR" analyzes the incident "Me sale el error 809 en la vpn"
    Then the response status is 403

  Scenario: A registered ticket is triaged automatically
    Given the collaborator registered the ticket "VPN no conecta" with the description "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    When the automatic triage processes the ticket
    Then the ticket "VPN no conecta" is in status "PENDING_ASSIGNMENT"
    And the diagnosis of the ticket is waiting for an analyst review

  Scenario: A ticket is never left untriaged when the AI fails
    Given the language model is unavailable
    And the collaborator registered the ticket "VPN no conecta" with the description "Me sale el error 809 en la vpn, los puertos udp 500 y 4500"
    When the automatic triage processes the ticket
    Then the ticket "VPN no conecta" is in status "PENDING_ASSIGNMENT"
    And the diagnosis of the ticket records that the AI was unavailable
