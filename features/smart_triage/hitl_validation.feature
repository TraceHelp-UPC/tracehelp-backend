Feature: Human-in-the-Loop validation of AI responses
  As a Tier 1 Support Analyst
  I want to review, edit or approve the AI-generated response before sending it to the collaborator
  So that I can ensure the accuracy of the resolution message

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator
    And the ticket is in status "ASSIGNED_L1"

  Scenario: Analyst approves the AI recommendation, resolving the ticket and logging audit entry
    Given the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.88 for the ticket
    When the "ANALYST_L1" reviews the diagnosis with action "APPROVE"
    Then the response status is 200
    And the diagnosis validation status is "APPROVED"
    And the ticket status is "RESOLVED"
    And the audit trail records action "AI_RESOLUTION_APPROVED" for the ticket

  Scenario: Analyst edits and approves an inaccurate AI recommendation
    Given the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.82 for the ticket
    When the "ANALYST_L1" submits edited text "Reinicie el servicio OpenVPN y actualice el certificado corporativo." with review action "EDIT"
    Then the response status is 200
    And the diagnosis validation status is "EDITED"
    And the diagnosis final approved text is "Reinicie el servicio OpenVPN y actualice el certificado corporativo."
    And the ticket status is "RESOLVED"
    And the audit trail records action "AI_RESOLUTION_EDITED" for the ticket

  Scenario: Analyst rejects the AI recommendation preventing delivery to the collaborator
    Given the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.75 for the ticket
    When the "ANALYST_L1" reviews the diagnosis with action "REJECT"
    Then the response status is 200
    And the diagnosis validation status is "REJECTED"
    And the ticket status is "ASSIGNED_L1"
    And the audit trail records action "AI_RESOLUTION_REJECTED" for the ticket

  Scenario: User without HITL permission cannot approve a recommendation
    Given the RAG engine retrieves chunk "manual_vpn.pdf" page 4 paragraph 2 with similarity 0.88 for the ticket
    When the "COLLABORATOR" reviews the diagnosis with action "APPROVE"
    Then the response status is 403

  Scenario: Analyst sends a manual response when there is no AI recommendation due to lack of evidence
    Given the RAG engine finds no relevant sources for the ticket
    When the "ANALYST_L1" submits edited text "Se coordinó el reemplazo físico del token MFA con Seguridad TI." with review action "MANUAL"
    Then the response status is 200
    And the diagnosis validation status is "MANUAL_ONLY"
    And the ticket status is "RESOLVED"
    And the audit trail records action "MANUAL_RESOLUTION_PROVIDED" for the ticket
