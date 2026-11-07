Feature: Document ingestion API contract
  As a client of the TraceHelp API (the Appsmith dashboard)
  I want the document upload endpoint to answer immediately and report the job status
  So that large manuals are processed in the background without blocking the user

  Background:
    Given a workspace with users for every role
    And a PDF manual "Manual_VPN.pdf" with 1 pages of text

  Scenario: A valid file is accepted with 202 and an ingestion job
    When the "IT_LEADER" uploads the manual
    Then the response status is 202
    And the response contains a job id with status "PENDING"
    And the "Location" header points to the status of that job
    When the client requests the status of that job as the "IT_LEADER"
    Then the response status is 200
    And the job reports the file "Manual_VPN.pdf" in status "PENDING"

  Scenario: Support analysts can follow the job status
    When the "IT_LEADER" uploads the manual
    And the client requests the status of that job as the "ANALYST_L1"
    Then the response status is 200

  Scenario Outline: Unsupported formats are rejected with 400 in RFC 7807 format
    Given a file "<file>" with <content>
    When the "IT_LEADER" uploads the manual
    Then the response status is 400
    And the error is reported as problem details
    And the error detail mentions "<message>"

    Examples:
      | file        | content                | message                     |
      | manual.docx | a Word document        | Solo se aceptan manuales PDF |
      | manual.pdf  | text that is not a PDF | no es un PDF válido         |

  Scenario Outline: Requests without a valid access token are rejected with 401
    When the client uploads the manual with <token>
    Then the response status is 401
    And the response asks for a Bearer token
    And the error detail says "<message>"

    Examples:
      | token                                | message                                              |
      | no token                             | Se requiere un token de acceso.                      |
      | a malformed token                    | El token no es válido.                               |
      | a token signed with another key      | El token no es válido.                               |
      | an expired token                     | El token ha expirado.                                |
      | a refresh token instead of an access | El tipo de token no corresponde a esta operación.    |

  Scenario: The job status also requires a valid token
    When the "IT_LEADER" uploads the manual
    And the client requests the status of that job without a token
    Then the response status is 401

  Scenario: Collaborators cannot upload manuals
    When the "COLLABORATOR" uploads the manual
    Then the response status is 403

  Scenario: Uploading to another workspace is treated as not found
    When the "IT_LEADER" uploads the manual to another workspace
    Then the response status is 404
    And the knowledge base is empty

  Scenario: Jobs of another workspace are not visible
    When the "IT_LEADER" uploads the manual
    And a leader of another workspace requests the status of that job
    Then the response status is 404

  Scenario: Unknown jobs return 404
    When the client requests the status of an unknown job as the "IT_LEADER"
    Then the response status is 404
