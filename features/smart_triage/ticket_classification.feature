Feature: Automatic incident classification and prioritization
  As a Tier 1 Support Analyst
  I want each registered incident to be automatically classified by category and priority
  So that I can reduce the time spent on manual triage

  Background:
    Given a workspace with users for every role

  Scenario: Incident with clear description is classified by category and priority
    When the collaborator reports an incident titled "Fallo de conexión VPN corporativa" with description "El cliente VPN muestra error de gateway TLS y sin acceso a la red" and impact "HIGH"
    Then the response status is 201
    And the ticket category is "Conectividad y Red"
    And the ticket priority is "HIGH"
    And the suggested classification is "Conectividad y Red" with priority "HIGH"

  Scenario: Analyst overrides an incorrect classification preserving the suggested one
    Given a classified ticket in category "Conectividad y Red" with priority "MEDIUM"
    When the "ANALYST_L1" updates the ticket classification to category "Accesos y Credenciales" and priority "HIGH"
    Then the response status is 200
    And the ticket category is "Accesos y Credenciales"
    And the ticket priority is "HIGH"
    And the suggested classification is "Conectividad y Red" with priority "MEDIUM"

  Scenario: Ambiguous description falls back to General category and declared impact priority
    When the collaborator reports an incident titled "Consulta" with description "Necesito apoyo con un trámite interno pendiente desde ayer" and impact "LOW"
    Then the response status is 201
    And the ticket category is "General"
    And the ticket priority is "LOW"
    And the suggested classification is "General" with priority "LOW"

  Scenario: Collaborator cannot override ticket classification
    Given a classified ticket in category "Conectividad y Red" with priority "MEDIUM"
    When the "COLLABORATOR" updates the ticket classification to category "General" and priority "LOW"
    Then the response status is 403
