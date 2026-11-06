Feature: Automated RAG diagnosis with citations
  As a Tier 1 Support Analyst
  I want to obtain a solution recommendation generated through RAG
  So that I can reduce the time dedicated to incident diagnosis

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator

  Scenario: Recommendation generated with verified source citations when evidence is sufficient
    Given the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.88 for the ticket
    When the "ANALYST_L1" requests the ticket diagnosis
    Then the response status is 200
    And the diagnosis has sufficient evidence with confidence 0.88
    And the diagnosis includes citation "manual_vpn.pdf" page 4 paragraph 2

  Scenario: System reports insufficient evidence when no relevant sources exist
    Given the RAG engine finds no relevant sources for the ticket
    When the "ANALYST_L1" requests the ticket diagnosis
    Then the response status is 200
    And the diagnosis reports insufficient evidence and low confidence alert

  Scenario: Recommendation marked as low confidence when similarity is below threshold
    Given the RAG engine retrieves chunk "manual_correo.pdf" page 2 paragraph 1 with similarity 0.58 for the ticket
    When the "ANALYST_L1" requests the ticket diagnosis
    Then the response status is 200
    And the diagnosis is marked as low confidence alert with score 0.58
