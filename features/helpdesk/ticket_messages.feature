Feature: Ticket conversation
  As a collaborator or a support team member
  I want to exchange messages inside a ticket
  So that the incident is resolved without leaving the platform and internal notes stay private

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator
    And the ticket is in status "ASSIGNED_L1"

  # ------------------------------------------------------------------ US26, criterio 1: mensaje válido
  Scenario: The collaborator posts a valid message on their ticket
    Given a subscriber is listening to MessagePosted events
    When the "COLLABORATOR" posts the message "Adjunto: el error aparece solo cuando estoy en la VPN."
    Then the response status is 201
    And the response field "content" is "Adjunto: el error aparece solo cuando estoy en la VPN."
    And the response field "from_reporter" is "true"
    And the response field "is_internal_note" is "false"
    And the response field "is_ai_generated" is "false"
    And the response field "ticket_id" is the ticket id
    And MessagePosted was published once with author_is_reporter true and is_internal_note false

  Scenario: The analyst posts a valid message and the collaborator sees it
    When the "ANALYST_L1" posts the message "¿El error aparece también fuera de la VPN?"
    Then the response status is 201
    And the response field "from_reporter" is "false"
    And the response field "author_name" is "ANALYST_L1 Demo"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread shows these messages in order:
      | content                                   | from_reporter | is_internal_note |
      | ¿El error aparece también fuera de la VPN? | false         | false            |

  Scenario: Messages appear in the thread in chronological order for everyone
    Given the "ANALYST_L1" posts the message "Primero"
    And the "COLLABORATOR" posts the message "Segundo"
    And the "ANALYST_L1" posts the message "Tercero"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the thread shows these messages in order:
      | content | from_reporter | is_internal_note |
      | Primero | false         | false            |
      | Segundo | true          | false            |
      | Tercero | false         | false            |
    And the thread reports 3 messages in 1 pages
    When the "ANALYST_L1" requests the messages of the ticket
    Then the thread shows these messages in order:
      | content | from_reporter | is_internal_note |
      | Primero | false         | false            |
      | Segundo | true          | false            |
      | Tercero | false         | false            |

  Scenario: A ticket without messages returns an empty thread
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread reports 0 messages in 0 pages
    And the thread page holds 0 messages

  Scenario: The message text is trimmed and stored as written
    When the "COLLABORATOR" posts the message "   Hola equipo   "
    Then the response status is 201
    And the response content is exactly "Hola equipo"

  Scenario: Accents and emoji are preserved
    When the "COLLABORATOR" posts a message with accents and emoji
    Then the response status is 201
    And the response content equals the text that was sent
    When the "ANALYST_L1" requests the messages of the ticket
    Then the thread page holds 1 messages

  Scenario: Line breaks are preserved
    When the "COLLABORATOR" posts a message with this text:
      """
      Paso 1: reinicié el equipo
      Paso 2: probé con otra red

      Sigue fallando
      """
    Then the response status is 201
    And the response content equals the text that was sent

  Scenario Outline: Messages are accepted in every status except RESOLVED and CLOSED
    Given the ticket is in status "<status>"
    When the "COLLABORATOR" posts the message "Consulta en estado <status>"
    Then the response status is 201
    And the ticket status is "<status>"

    Examples:
      | status                |
      | OPEN                  |
      | SELF_SERVICE_PROPOSED |
      | PENDING_ASSIGNMENT    |
      | ASSIGNED_L1           |
      | ESCALATED_L2          |
      | REOPENED              |

  Scenario: A support member who is not the assignee can write
    Given the ticket is in status "ESCALATED_L2"
    When the "SPECIALIST_L2" posts the message "Tomo el caso, reviso el servidor"
    Then the response status is 201
    And the response field "from_reporter" is "false"

  # ------------------------------------------------------------------ US26, criterio 2: notas internas
  Scenario: An internal note is hidden from the collaborator
    Given the "ANALYST_L1" posts the message "Estamos revisando tu caso"
    And the "ANALYST_L1" posts the internal note "Interna: revisar el servidor Exchange"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread reports 1 messages in 1 pages
    And the thread does not contain "Exchange"
    When the "ANALYST_L1" requests the messages of the ticket
    Then the thread reports 2 messages in 1 pages
    And the thread shows these messages in order:
      | content                              | from_reporter | is_internal_note |
      | Estamos revisando tu caso            | false         | false            |
      | Interna: revisar el servidor Exchange | false         | true             |

  Scenario: An analyst can post an internal note
    When the "ANALYST_L1" posts the internal note "Nota para el equipo"
    Then the response status is 201
    And the response field "is_internal_note" is "true"

  Scenario: Internal notes do not count in the total or the pages of the collaborator
    Given the ticket already has 3 messages from the collaborator
    And the "ANALYST_L1" posts the internal note "Nota secreta uno"
    And the "ANALYST_L1" posts the internal note "Nota secreta dos"
    When the "COLLABORATOR" requests the messages of the ticket page 1 with 2 messages per page
    Then the thread reports 3 messages in 2 pages
    And the thread page holds 2 messages
    And the thread does not contain "secreta"
    When the "COLLABORATOR" requests the messages of the ticket page 3 with 2 messages per page
    Then the response status is 400
    When the "ANALYST_L1" requests the messages of the ticket page 1 with 2 messages per page
    Then the thread reports 5 messages in 3 pages

  Scenario: Internal notes do not leak through the ticket detail or the history
    Given the "ANALYST_L1" posts the internal note "Nota secreta del detalle"
    When the "COLLABORATOR" opens the full detail of the ticket
    Then the response status is 200
    And the detail shows 0 comments
    And the response body does not contain "secreta"
    When the collaborator lists their ticket history
    Then the response status is 200
    And the response body does not contain "secreta"
    When the "COLLABORATOR" requests the status history of the ticket
    Then the response body does not contain "secreta"
    When the "ANALYST_L1" opens the full detail of the ticket
    Then the detail shows 1 comments

  Scenario: A specialist internal note stays hidden from the collaborator
    Given the ticket is in status "ESCALATED_L2"
    And the "SPECIALIST_L2" posts the internal note "L2: el certificado está vencido"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the thread reports 0 messages in 0 pages
    And the thread does not contain "certificado"
    When the "ANALYST_L1" requests the messages of the ticket
    Then the thread reports 1 messages in 1 pages

  Scenario: The collaborator cannot mark a message as an internal note
    When the "COLLABORATOR" posts the internal note "Esto es privado"
    Then the response status is 403
    And the problem type is "internal-note-not-allowed"
    And the stored message count of the ticket is 0

  Scenario: The AI reply validated by the analyst is part of the thread and is not truncated
    Given the ticket has a validated AI reply of 2500 characters
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread contains the AI reply marked as "true" with 2500 characters

  # ------------------------------------------------------------------ US26, criterio 3: ticket resuelto o cerrado (D30)
  Scenario: Nobody can write on a closed ticket
    Given the ticket is in status "CLOSED"
    When the "COLLABORATOR" posts the message "¿Puedo agregar algo?"
    Then the response status is 409
    And the problem type is "ticket-closed"
    And the error detail mentions that the ticket is closed
    When the "ANALYST_L1" posts the message "Cerrado"
    Then the response status is 409
    And the problem type is "ticket-closed"
    When the "ANALYST_L1" posts the internal note "Nota tardía"
    Then the response status is 409
    And the stored message count of the ticket is 0

  Scenario: Nobody can write on a resolved ticket (D30)
    Given the ticket is in status "RESOLVED"
    When the "COLLABORATOR" posts the message "¿Puedo agregar algo?"
    Then the response status is 409
    And the problem type is "ticket-closed"
    And the error detail mentions that the ticket is resolved
    And the ticket status is "RESOLVED"
    When the "ANALYST_L1" posts the message "Resuelto"
    Then the response status is 409
    And the problem type is "ticket-closed"
    When the "ANALYST_L1" posts the internal note "Nota tardía"
    Then the response status is 409
    And the stored message count of the ticket is 0

  Scenario: Reopening a resolved ticket allows posting messages again
    Given the ticket is in status "RESOLVED"
    When the "COLLABORATOR" posts the message "Sigue fallando"
    Then the response status is 409
    And the problem type is "ticket-closed"
    When the "COLLABORATOR" changes the ticket status to "REOPENED"
    Then the response status is 200
    When the "COLLABORATOR" posts the message "Adjunto nuevos detalles del error"
    Then the response status is 201
    And the ticket status is "REOPENED"

  Scenario Outline: A resolved or closed ticket can still be read
    Given the ticket already has 2 messages from the collaborator
    And the ticket is in status "<status>"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread reports 2 messages in 1 pages

    Examples:
      | status   |
      | RESOLVED |
      | CLOSED   |

  Scenario Outline: The collaborator marking an internal note on a resolved or closed ticket gets 403 first
    Given the ticket is in status "<status>"
    When the "COLLABORATOR" posts the internal note "Privado"
    Then the response status is 403
    And the problem type is "internal-note-not-allowed"

    Examples:
      | status   |
      | RESOLVED |
      | CLOSED   |

  # ------------------------------------------------------------------ Validación (422)
  Scenario Outline: An empty or blank message is rejected
    When the "<role>" posts a message of <count> spaces
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "content"
    And the stored message count of the ticket is 0

    Examples:
      | role         | count |
      | COLLABORATOR | 0     |
      | COLLABORATOR | 3     |
      | ANALYST_L1   | 0     |
      | ANALYST_L1   | 5     |

  Scenario: A message of 2001 characters is rejected
    Given a subscriber is listening to MessagePosted events
    When the "COLLABORATOR" posts a message of 2001 characters
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "content"
    And the stored message count of the ticket is 0
    And MessagePosted was not published

  Scenario: A message of exactly 2000 characters is accepted
    When the "COLLABORATOR" posts a message of 2000 characters
    Then the response status is 201
    And the response content has 2000 characters

  Scenario: The limit is measured after trimming the spaces
    When the "COLLABORATOR" posts a message of 2000 characters padded with spaces
    Then the response status is 201
    And the response content has 2000 characters

  Scenario: The limit counts characters and not bytes
    When the "COLLABORATOR" posts a message of 2000 emoji characters
    Then the response status is 201
    And the response content has 2000 characters
    When the "COLLABORATOR" posts a message of 2001 emoji characters
    Then the response status is 422

  Scenario: The analyst has the same limit as the collaborator
    When the "ANALYST_L1" posts a message of 2001 characters
    Then the response status is 422
    When the "ANALYST_L1" posts a message of 2000 characters
    Then the response status is 201

  Scenario Outline: A malformed payload is rejected
    When the "COLLABORATOR" posts this raw payload:
      """
      <payload>
      """
    Then the response status is 422
    And the problem type is "validation-error"

    Examples:
      | payload                                        |
      | {}                                             |
      | {"content": null}                              |
      | {"content": 123}                               |
      | {"content": "Hola", "extra": 1}                |
      | {"content": "Hola", "is_internal_note": "tal"} |

  # ------------------------------------------------------------------ Permisos y recursos
  Scenario: Another collaborator cannot read or write on a ticket that is not theirs
    Given another collaborator in the same workspace
    When the other collaborator requests the messages of the ticket
    Then the response status is 403
    And the problem type is "ticket-access-denied"
    When the other collaborator posts the message "Me cuelgo del ticket ajeno"
    Then the response status is 403
    And the problem type is "ticket-access-denied"
    And the stored message count of the ticket is 0

  Scenario: Another collaborator gets ticket-access-denied before internal-note-not-allowed
    Given another collaborator in the same workspace
    When the other collaborator posts the internal note "Nota en ticket ajeno"
    Then the response status is 403
    And the problem type is "ticket-access-denied"

  Scenario: The IT leader does not see the messages of other people's tickets
    Given the "ANALYST_L1" posts the message "Datos del caso"
    When the "IT_LEADER" requests the messages of the ticket
    Then the response status is 403
    And the problem type is "ticket-access-denied"
    And the response body does not contain "Datos del caso"
    When the "IT_LEADER" posts the message "Intento de mensaje"
    Then the response status is 403
    And the problem type is "ticket-access-denied"
    And the stored message count of the ticket is 1

  Scenario: A ticket of another workspace is treated as nonexistent
    Given an analyst of another workspace
    When the analyst of another workspace requests the messages of the ticket
    Then the response status is 404
    And the problem type is "ticket-not-found"
    When the analyst of another workspace posts the message "Desde otra empresa"
    Then the response status is 404

  Scenario: A nonexistent ticket returns 404
    When the "COLLABORATOR" requests the messages of a nonexistent ticket
    Then the response status is 404
    And the problem type is "ticket-not-found"
    When the "ANALYST_L1" posts the message "Hola" on a nonexistent ticket
    Then the response status is 404
    And the problem type is "ticket-not-found"

  Scenario: Requests without a token are rejected
    Given the "ANALYST_L1" posts the message "Mensaje previo"
    When an anonymous user requests the messages of the ticket
    Then the response status is 401
    And the response body does not contain "Mensaje previo"
    When an anonymous user posts the message "Sin sesión"
    Then the response status is 401
    And the stored message count of the ticket is 1

  Scenario: Requests with an invalid token are rejected
    When a user with an invalid token requests the messages of the ticket
    Then the response status is 401
    When a user with an invalid token posts the message "Token falso"
    Then the response status is 401

  # ------------------------------------------------------------------ Paginación
  Scenario: A long thread is paginated from the oldest message
    Given the ticket already has 120 messages from the collaborator
    When the "ANALYST_L1" requests the messages of the ticket
    Then the thread reports 120 messages in 3 pages
    And the thread page holds 50 messages
    And the thread page starts with "Mensaje 001" and ends with "Mensaje 050"
    When the "ANALYST_L1" requests the messages of the ticket page 2 with 100 messages per page
    Then the thread reports 120 messages in 2 pages
    And the thread page starts with "Mensaje 101" and ends with "Mensaje 120"

  Scenario Outline: The page size accepts the whole 1 to 100 range
    Given the ticket already has 3 messages from the collaborator
    When the "COLLABORATOR" requests the messages of the ticket page 1 with <size> messages per page
    Then the response status is 200
    And the response field "size" is "<size>"

    Examples:
      | size |
      | 1    |
      | 100  |

  Scenario Outline: A page or size out of range is rejected
    Given the ticket already has 3 messages from the collaborator
    When the "COLLABORATOR" requests the messages of the ticket page <page> with <size> messages per page
    Then the response status is 400
    And the problem type is "invalid-page-request"

    Examples:
      | page | size |
      | 0    | 10   |
      | -1   | 10   |
      | 1    | 0    |
      | 1    | 101  |
      | 2    | 10   |

  # ------------------------------------------------------------------ Evento, auditoría y privacidad
  Scenario: The event MessagePosted does not carry the message text
    Given a subscriber is listening to MessagePosted events
    When the "ANALYST_L1" posts the message "El usuario de red es jperez, clave Temporal123"
    Then the response status is 201
    And MessagePosted was published once with author_is_reporter false and is_internal_note false
    And the published event carries no message text

  Scenario: The event of an internal note is marked as internal
    Given a subscriber is listening to MessagePosted events
    When the "ANALYST_L1" posts the internal note "Nota para L2"
    Then MessagePosted was published once with author_is_reporter false and is_internal_note true
    And the published event carries no message text

  Scenario: The audit log records the metadata of the message but not its text
    Given the audit log of the workspace is empty
    When the "COLLABORATOR" posts the message "Mi correo es carlos.mendoza@empresa.pe y mi DNI 12345678"
    And the "IT_LEADER" requests the audit log of the ticket for "MessagePosted"
    Then the audit log holds a "MessagePosted" entry acted by the "COLLABORATOR" without the message text
    And the audit entry says author_is_reporter true and is_internal_note false in status "ASSIGNED_L1"
    And the raw audit rows do not contain the message text

  Scenario: The audit entry of an internal note from a specialist
    Given the ticket is in status "ESCALATED_L2"
    And the audit log of the workspace is empty
    When the "SPECIALIST_L2" posts the internal note "Revisar el balanceador"
    And the "IT_LEADER" requests the audit log of the ticket for "MessagePosted"
    Then the audit log holds a "MessagePosted" entry acted by the "SPECIALIST_L2" without the message text
    And the audit entry says author_is_reporter false and is_internal_note true in status "ESCALATED_L2"

  Scenario: Rejected messages leave no event and no audit entry
    Given a subscriber is listening to MessagePosted events
    And the audit log of the workspace is empty
    When the "COLLABORATOR" posts the internal note "Privado"
    And the "COLLABORATOR" posts a message of 2001 characters
    And an anonymous user posts the message "Sin sesión"
    Then MessagePosted was not published
    And the audit log holds no MessagePosted entry

  Scenario: The message text is not written to the application logs
    Given the application logs are being captured
    When the "COLLABORATOR" posts the message "Texto-confidencial-xyz-98765"
    And the "ANALYST_L1" requests the messages of the ticket
    Then the response status is 200
    And the captured logs do not contain "Texto-confidencial-xyz-98765"

  # ------------------------------------------------------------------ Contrato OpenAPI
  Scenario: The OpenAPI document describes the messages endpoints
    When the client requests the OpenAPI document
    Then the OpenAPI document declares "POST" "/api/v1/tickets/{ticket_id}/messages" with the responses "201,403,404,409,422"
    And the OpenAPI document declares "GET" "/api/v1/tickets/{ticket_id}/messages" with the responses "200,400,403,404"
