Feature: Reading error screenshots with OCR
  As a non-technical collaborator
  I want the system to read the error message in my screenshot
  So that the triage can diagnose the incident without me typing the error

  Scenario: A readable screenshot gives its text and error codes
    Given a screenshot of an error window with the lines:
      | line                                            |
      | Error de autenticacion de dominio               |
      | Codigo: 0x80070005 - Acceso denegado.           |
      | VPN Error 809: no se pudo conectar al servidor. |
    When the screenshot is analyzed
    Then the extracted text contains "Acceso denegado"
    And the error codes "0x80070005, Error 809" are detected

  Scenario: A dark mode screenshot is read as well
    Given a dark mode screenshot of an error window with the lines:
      | line                                  |
      | Codigo: 0x80070005 - Acceso denegado. |
      | Contacte al administrador de TI.      |
    When the screenshot is analyzed
    Then the extracted text contains "Contacte al administrador"

  Scenario Outline: An illegible screenshot asks for a better capture or more details
    Given <screenshot>
    When the screenshot is analyzed
    Then the screenshot is marked as illegible
    And the collaborator is asked for a clearer screenshot or a more detailed description

    Examples:
      | screenshot                         |
      | a blurry screenshot of an error    |
      | a screenshot without any text      |
