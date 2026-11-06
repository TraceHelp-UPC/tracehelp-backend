Feature: Multimodal incident registration
  As a non-technical collaborator
  I want to report an incident with a description and screenshots of the error
  So that the automated triage has enough context to diagnose it

  Background:
    Given a workspace with users for every role

  Scenario: Collaborator registers an incident with a text description
    When the collaborator registers an incident with title "No puedo ingresar al ERP" and description "Error 0x80070005 al iniciar sesión"
    Then the response status is 201
    And the ticket is created in status "OPEN" with a public code
    And the ticket has 0 screenshots stored
    And the triage is notified about the new ticket

  Scenario: Collaborator registers an incident with text and a valid screenshot
    Given the collaborator has a PNG screenshot of the error
    When the collaborator registers the incident with the screenshots
    Then the response status is 201
    And the ticket has 1 screenshots stored
    And the stored screenshot is an "image/png" file

  Scenario: Large screenshots are reduced before being stored
    Given the collaborator has a JPEG screenshot of 4000 by 3000 pixels
    When the collaborator registers the incident with the screenshots
    Then the response status is 201
    And the stored screenshot is smaller than the original file

  Scenario Outline: Screenshots outside the allowed restrictions are rejected
    Given the collaborator has <file>
    When the collaborator registers the incident with the screenshots
    Then the response status is 400
    And the error detail mentions "<reason>"
    And no ticket was created

    Examples:
      | file                             | reason              |
      | a GIF image                      | PNG o JPG           |
      | a text file renamed as PNG       | no es una imagen    |
      | a PNG image larger than 10 MB    | 10 MB               |
      | 6 PNG screenshots                | como máximo 5       |

  Scenario Outline: Registration without the required information is rejected
    When the collaborator registers an incident without the "<field>" field
    Then the response status is 422
    And the error detail mentions "<field>"
    And no ticket was created

    Examples:
      | field        |
      | title        |
      | description  |
      | impact_level |

  Scenario Outline: Blank required values are rejected
    When the collaborator registers an incident with title "<title>" and description "<description>"
    Then the response status is 400
    And no ticket was created

    Examples:
      | title                    | description          |
      | No puedo ingresar al ERP | (blank)              |
      | (blank)                  | El sistema se cierra |

  Scenario: Registration requires an authenticated user
    When an anonymous user registers an incident
    Then the response status is 401
    And no ticket was created
