Feature: Knowledge base management
  As the IT leader
  I want to upload the company's technical manuals and follow their ingestion
  So that the AI answers incidents only with approved information

  Background:
    Given a workspace with users for every role

  Scenario: The IT leader uploads a compatible PDF manual
    Given a PDF manual "Manual_VPN.pdf" with 2 pages of text
    When the "IT_LEADER" uploads the manual with the title "Manual de VPN"
    Then the response status is 202
    And the knowledge base shows "Manual de VPN" in status "PENDING"
    When the ingestion of the manual finishes
    Then the knowledge base shows "Manual de VPN" in status "VECTORIZED"
    And the manual "Manual de VPN" has 2 fragments
    And the fragments of "Manual de VPN" cite the pages of "Manual_VPN.pdf"

  Scenario: A Markdown manual without a title uses the file name
    Given a Markdown manual "guia-correo.md" with 3 sections
    When the "IT_LEADER" uploads the manual
    Then the response status is 202
    And the knowledge base shows "guia-correo" in status "PENDING"
    When the ingestion of the manual finishes
    Then the knowledge base shows "guia-correo" in status "VECTORIZED"
    And the manual "guia-correo" has 3 fragments

  Scenario Outline: Files that are not PDF or Markdown are rejected
    Given a file "<file>" with <content>
    When the "IT_LEADER" uploads the manual
    Then the response status is 400
    And the error detail mentions "<message>"
    And the knowledge base is empty

    Examples:
      | file         | content                 | message                     |
      | manual.docx  | a Word document         | Solo se aceptan manuales PDF |
      | captura.png  | a PNG image             | Solo se aceptan manuales PDF |
      | notas.txt    | plain text              | Solo se aceptan manuales PDF |
      | manual.pdf   | text that is not a PDF  | no es un PDF válido         |

  Scenario: Manuals larger than 25 MB are rejected
    Given a PDF manual "Manual_gigante.pdf" larger than 25 MB
    When the "IT_LEADER" uploads the manual
    Then the response status is 400
    And the error detail mentions "25 MB"
    And the knowledge base is empty

  Scenario: Empty files are rejected
    Given a file "vacio.md" with no content
    When the "IT_LEADER" uploads the manual
    Then the response status is 400
    And the error detail mentions "vacío"
    And the knowledge base is empty

  Scenario: A scanned PDF without text ends as failed with the reason
    Given a scanned PDF manual "Manual_escaneado.pdf" without selectable text
    When the "IT_LEADER" uploads the manual with the title "Manual escaneado"
    And the ingestion of the manual finishes
    Then the knowledge base shows "Manual escaneado" in status "FAILED"
    And the manual "Manual escaneado" explains that "no tiene texto seleccionable"

  Scenario: Support analysts can see the inventory but cannot upload manuals
    Given a PDF manual "Manual_VPN.pdf" with 1 pages of text
    When the "ANALYST_L1" uploads the manual
    Then the response status is 403
    When the "IT_LEADER" uploads the manual with the title "Manual de VPN"
    And the "ANALYST_L1" opens the knowledge base
    Then the response status is 200
    And the inventory lists "Manual de VPN"
