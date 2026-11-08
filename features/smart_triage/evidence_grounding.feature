Feature: Evidence grounding and low confidence alerts
  As a support analyst or IT leader
  I want RAG responses grounded exclusively in retrieved manual fragments with citations
  So that the AI never hallucinates answers when the knowledge base lacks evidence

  Background:
    Given a workspace with users for every role
    And the knowledge base of the workspace has the VPN troubleshooting guide
    And the evidence search and diagnosis preview services use simulated embeddings and LLM

  Scenario: Evidence search returns supporting fragments with exact citation
    When the "ANALYST_L1" searches the manuals for "error 809 vpn puertos udp 500 y 4500"
    Then the response status is 200
    And the evidence search confidence level is "GROUNDED"
    And the top evidence fragment cites "guia-vpn.md, sección «Error 809», párr. 1" and supports the answer
    And no low confidence alert was published

  Scenario: Query without sufficient evidence raises a low confidence alert
    When the "ANALYST_L1" searches the manuals for "la silla ergonómica rechina mucho"
    Then the response status is 200
    And the evidence search confidence level is "LOW_CONFIDENCE"
    And a low confidence alert was published for the workspace

  Scenario: Diagnosis preview cites retrieved fragments in every step
    When the "ANALYST_L1" requests a diagnosis preview for "me sale el error 809 en la vpn, puertos udp 500 y 4500"
    Then the response status is 200
    And the preview status is "ANSWERED"
    And every step of the diagnosis cites a source
    And the diagnosis cites "guia-vpn.md, sección «Error 809», párr. 1"

  Scenario: Diagnosis preview does not call the language model on low confidence
    When the "IT_LEADER" requests a diagnosis preview for "la silla ergonómica rechina mucho"
    Then the response status is 200
    And the preview status is "INSUFFICIENT_EVIDENCE"
    And the language model was not called
