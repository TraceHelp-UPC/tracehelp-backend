Feature: L2 escalation and return to L1
  As an L1 support analyst or L2 specialist
  I want to escalate complex incidents to a specialist group with context and return them to L1 when more info is needed
  So that level 2 gets full triage evidence without exposing internal notes to the collaborator

  Background:
    Given a workspace with users for every role
    And specialist L2 users for groups "REDES" and "SEGURIDAD"
    And a ticket reported by the collaborator

  # ------------------------------------------------------------------ US17, esc. 1 & 2: escalamiento con contexto completo
  Scenario: Analyst L1 escalates an assigned ticket with full triage context, OCR and citations
    Given the ticket is classified with category "Red/VPN", priority "HIGH" and module "VPN corporativa"
    And the ticket is in status "ASSIGNED_L1"
    And the ticket has a triage diagnosis with OCR and cited sources
    And the audit log of the workspace is empty
    And a subscriber is listening to TicketEscalated and MessagePosted events
    When the "ANALYST_L1" escalates the ticket to group "REDES" with reason "El error 809 persiste tras reiniciar el perfil VPN; requiere firewall."
    Then the response status is 200
    And the response field "status" is "ESCALATED_L2"
    And the response field "current_tier" is "TIER_L2"
    And the response field "escalated_group" is "REDES"
    And the response field "escalated_at" is not null
    And the response field "assigned_specialist_id" is "null"
    And the response field "specialist_claimed_at" is "null"
    And the response field "assigned_analyst_id" matches the user "ANALYST_L1"
    And TicketEscalated was published once with has_triage_snapshot true
    And MessagePosted was not emitted during escalation
    When the "SPECIALIST_REDES" opens the full detail of the ticket
    Then the response status is 200
    And the detail shows 1 comments
    And the first comment is an internal note containing:
      | fragment                                                      |
      | [ESCALAMIENTO A L2 · REDES]                                   |
      | Motivo del escalamiento: El error 809 persiste tras reiniciar |
      | Categoría=Red/VPN \| Prioridad=HIGH \| Impacto=MEDIUM         |
      | bloqueo de puertos UDP 500/4500                               |
      | ERR_809                                                       |
      | Error 809 al conectar [EMAIL]                                 |
      | [F1] Sección 3.1 · Error 809 (Manual VPN Corporativa)         |
    When the "COLLABORATOR" opens the full detail of the ticket
    Then the response status is 200
    And the detail shows 0 comments
    And the response body does not contain "[ESCALAMIENTO A L2"
    And the response body does not contain "ERR_809"
    When the "COLLABORATOR" requests the messages of the ticket
    Then the response status is 200
    And the thread reports 0 messages in 0 pages
    And the thread does not contain "[ESCALAMIENTO A L2"
    And the workspace audit log holds a "TicketEscalated" entry acted by "ANALYST_L1" for group "REDES" with snapshot true

  # ------------------------------------------------------------------ US17: escalamiento sin diagnóstico previo
  Scenario: Analyst L1 escalates a ticket without prior triage diagnosis
    Given the ticket is in status "ASSIGNED_L1"
    And the audit log of the workspace is empty
    And a subscriber is listening to TicketEscalated and MessagePosted events
    When the "ANALYST_L1" escalates the ticket to group "INFRAESTRUCTURA" with reason "Servidor ERP sin respuesta desde esta mañana."
    Then the response status is 200
    And the response field "status" is "ESCALATED_L2"
    And the response field "escalated_group" is "INFRAESTRUCTURA"
    And TicketEscalated was published once with has_triage_snapshot false
    When the "SPECIALIST_L2" opens the full detail of the ticket
    Then the response status is 200
    And the detail shows 1 comments
    And the first comment is an internal note containing:
      | fragment                                                                   |
      | [ESCALAMIENTO A L2 · INFRAESTRUCTURA]                                      |
      | Triaje IA: Sin diagnóstico automático registrado al momento del escalamiento. |
      | OCR (anonimizado): Sin evidencia OCR                                       |
      | - Sin fuentes consultadas                                                  |
    When the "COLLABORATOR" opens the full detail of the ticket
    Then the detail shows 0 comments
    And the workspace audit log holds a "TicketEscalated" entry acted by "ANALYST_L1" for group "INFRAESTRUCTURA" with snapshot false

  # ------------------------------------------------------------------ US17: re-escalamiento limpia reclamo previo
  Scenario: Re-escalating a ticket clears any previous L2 claim and updates the target group
    Given the ticket is in status "ASSIGNED_L1"
    And the ticket still holds a prior L2 claim by "SPECIALIST_REDES"
    When the "ANALYST_L1" escalates the ticket to group "APLICACIONES" with reason "Tras devolverlo, el error ahora ocurre dentro del módulo contable."
    Then the response status is 200
    And the response field "status" is "ESCALATED_L2"
    And the response field "escalated_group" is "APLICACIONES"
    And the response field "assigned_specialist_id" is "null"
    And the response field "specialist_claimed_at" is "null"
    And the response field "assigned_analyst_id" matches the user "ANALYST_L1"

  # ------------------------------------------------------------------ US17: validaciones de entrada en escalate
  Scenario Outline: Invalid escalation payloads are rejected with 422
    Given the ticket is in status "ASSIGNED_L1"
    When the "ANALYST_L1" sends raw escalation payload '<payload>'
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "<field>"
    And the ticket status is "ASSIGNED_L1"

    Examples:
      | payload                                                                                       | field            |
      | {"specialist_group": "VENTAS", "reason": "Motivo válido de prueba"}                           | specialist_group |
      | {"specialist_group": "REDES", "reason": "   "}                                                | reason           |
      | {"specialist_group": "REDES", "reason": "abc"}                                                | reason           |
      | {"specialist_group": "REDES", "reason": "Motivo válido", "extra_field": true}                 | extra_field      |

  Scenario: An escalation reason longer than 500 characters is rejected with 422
    Given the ticket is in status "ASSIGNED_L1"
    When the "ANALYST_L1" escalates the ticket to group "REDES" with a reason of 501 characters
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "reason"
    And the ticket status is "ASSIGNED_L1"

  # ------------------------------------------------------------------ US17: máquina de estados en escalate
  Scenario Outline: Escalating a ticket outside ASSIGNED_L1 is rejected with 422
    Given the ticket is in status "<status>"
    When the "ANALYST_L1" escalates the ticket to group "REDES" with reason "Intento de escalar fuera de estado"
    Then the response status is 422
    And the problem type is "invalid-ticket-state-transition"
    And the ticket status is "<status>"

    Examples:
      | status             |
      | PENDING_ASSIGNMENT |
      | ESCALATED_L2       |
      | RESOLVED           |
      | CLOSED             |

  # ------------------------------------------------------------------ US17, esc. 3: devolución a L1 por especialista del mismo grupo
  Scenario: Matching L2 specialist returns an escalated ticket to the original L1 and restores their queue
    Given the ticket is in status "ESCALATED_L2" for group "REDES" claimed by "SPECIALIST_REDES"
    And the audit log of the workspace is empty
    And a subscriber is listening to TicketReturnedToL1 and MessagePosted events
    When the "SPECIALIST_REDES" returns the ticket to L1 with requested info "Solicitar al colaborador la captura del comando ipconfig /all."
    Then the response status is 200
    And the response field "status" is "ASSIGNED_L1"
    And the response field "current_tier" is "TIER_L1"
    And the response field "assigned_analyst_id" matches the user "ANALYST_L1"
    And the response field "assigned_specialist_id" is "null"
    And the response field "specialist_claimed_at" is "null"
    And the response field "escalated_group" is "REDES"
    And the response field "escalated_at" is not null
    And TicketReturnedToL1 was published once
    And MessagePosted was not emitted during escalation
    When the "ANALYST_L1" opens the "mine" queue
    Then the response status is 200
    And the queue includes the ticket
    When the "ANALYST_L1" opens the full detail of the ticket
    Then the detail shows 1 comments
    And the first comment is an internal note containing:
      | fragment                                                      |
      | [DEVOLUCIÓN DE L2 A L1 · REDES]                               |
      | Información adicional solicitada: Solicitar al colaborador la |
      | ipconfig /all                                                 |
    When the "COLLABORATOR" opens the full detail of the ticket
    Then the detail shows 0 comments
    And the response body does not contain "DEVOLUCIÓN DE L2 A L1"
    And the response body does not contain "ipconfig /all"
    And the workspace audit log holds a "TicketReturnedToL1" entry acted by "SPECIALIST_REDES" for group "REDES"

  # ------------------------------------------------------------------ US17: guardas de grupo y caso legado null
  Scenario: Specialist of another group or without group cannot return a ticket assigned to REDES
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When the "SPECIALIST_SEGURIDAD" returns the ticket to L1 with requested info "Confirmar si ocurre en red doméstica o móvil."
    Then the response status is 403
    And the problem type is "ticket-status-change-forbidden"
    And the error detail says "El ticket está escalado al grupo REDES."
    And the ticket status is "ESCALATED_L2"
    When the "SPECIALIST_L2" returns the ticket to L1 with requested info "Confirmar si ocurre en red doméstica o móvil."
    Then the response status is 403
    And the problem type is "ticket-status-change-forbidden"
    And the ticket status is "ESCALATED_L2"

  Scenario: Any L2 specialist can return a legacy escalated ticket with null group
    Given the ticket is in status "ESCALATED_L2" with null escalated group
    When the "SPECIALIST_L2" returns the ticket to L1 with requested info "Confirmar si ocurre en red doméstica o móvil."
    Then the response status is 200
    And the response field "status" is "ASSIGNED_L1"
    And the response field "escalated_group" is "null"
    And the response field "assigned_analyst_id" matches the user "ANALYST_L1"

  Scenario: Legacy escalated ticket without original L1 analyst returns 400 on return-to-l1
    Given the ticket is in status "ESCALATED_L2" for group "REDES" without assigned analyst
    When the "SPECIALIST_REDES" returns the ticket to L1 with requested info "Solicitar datos adicionales al usuario."
    Then the response status is 400
    And the problem type is "invalid-ticket-data"
    And the error detail says "El ticket no tiene un analista L1 original asignado para devolverlo."
    And the ticket status is "ESCALATED_L2"

  # ------------------------------------------------------------------ US17: estado y validaciones en return-to-l1
  Scenario Outline: Returning a ticket outside ESCALATED_L2 is rejected with 422
    Given the ticket is in status "<status>"
    When the "SPECIALIST_REDES" returns the ticket to L1 with requested info "Solicitar datos adicionales al usuario."
    Then the response status is 422
    And the problem type is "invalid-ticket-state-transition"
    And the ticket status is "<status>"

    Examples:
      | status             |
      | PENDING_ASSIGNMENT |
      | ASSIGNED_L1        |
      | REOPENED           |
      | RESOLVED           |

  Scenario Outline: Invalid return-to-l1 payloads are rejected with 422
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When the "SPECIALIST_REDES" sends raw return-to-l1 payload '<payload>'
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "<field>"

    Examples:
      | payload                                                      | field          |
      | {"requested_info": "   "}                                    | requested_info |
      | {"requested_info": "abc"}                                    | requested_info |
      | {"requested_info": "Información válida", "unknown": 1}       | unknown        |

  Scenario: A return-to-l1 request longer than 2000 characters is rejected with 422
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When the "SPECIALIST_REDES" returns the ticket to L1 with requested info of 2001 characters
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "requested_info"

  # ------------------------------------------------------------------ US17, esc. 4: permisos, autenticación y aislamiento 404
  Scenario Outline: Roles without permission cannot escalate a ticket
    Given the ticket is in status "ASSIGNED_L1"
    When the "<role>" escalates the ticket to group "REDES" with reason "Intento sin permiso suficiente"
    Then the response status is 403
    And the problem type is "forbidden"
    And the ticket status is "ASSIGNED_L1"

    Examples:
      | role          |
      | COLLABORATOR  |
      | IT_LEADER     |
      | SPECIALIST_L2 |

  Scenario Outline: Roles without permission cannot return an escalated ticket to L1
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When the "<role>" returns the ticket to L1 with requested info "Intento de devolución sin permiso"
    Then the response status is 403
    And the problem type is "forbidden"
    And the ticket status is "ESCALATED_L2"

    Examples:
      | role         |
      | COLLABORATOR |
      | ANALYST_L1   |
      | IT_LEADER    |

  Scenario: Unauthenticated or invalid-token requests to escalate and return-to-l1 return 401
    Given the ticket is in status "ASSIGNED_L1"
    When an anonymous user escalates the ticket to group "REDES"
    Then the response status is 401
    When a user with an invalid token escalates the ticket to group "REDES"
    Then the response status is 401
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When an anonymous user returns the ticket to L1
    Then the response status is 401
    When a user with an invalid token returns the ticket to L1
    Then the response status is 401

  Scenario: Nonexistent tickets and tickets from another workspace return 404
    Given an analyst of another workspace
    And a specialist L2 of another workspace
    And the ticket is in status "ASSIGNED_L1"
    When the "ANALYST_L1" escalates a nonexistent ticket to group "REDES"
    Then the response status is 404
    And the problem type is "ticket-not-found"
    When the analyst of another workspace escalates the ticket to group "REDES"
    Then the response status is 404
    And the problem type is "ticket-not-found"
    Given the ticket is in status "ESCALATED_L2" for group "REDES"
    When the "SPECIALIST_REDES" returns a nonexistent ticket to L1
    Then the response status is 404
    And the problem type is "ticket-not-found"
    When the specialist L2 of another workspace returns the ticket to L1
    Then the response status is 404
    And the problem type is "ticket-not-found"

  # ------------------------------------------------------------------ US17: privacidad PII en auditoría y contrato OpenAPI
  Scenario: PII in escalation reason and return request is masked in audit entries
    Given the ticket is in status "ASSIGNED_L1"
    And the audit log of the workspace is empty
    When the "ANALYST_L1" escalates the ticket to group "REDES" with reason "Contactar a juan.perez@empresa.pe por fallo VPN"
    Then the response status is 200
    And the workspace audit log entries do not contain "juan.perez@empresa.pe"
    When the "SPECIALIST_REDES" returns the ticket to L1 with requested info "Pedir captura al correo maria.lopez@empresa.pe"
    Then the response status is 200
    And the workspace audit log entries do not contain "maria.lopez@empresa.pe"

  Scenario: OpenAPI contract documents both escalation and return-to-l1 endpoints
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI document declares "POST" "/api/v1/tickets/{ticket_id}/escalate" with the responses "200,403,404,422"
    And the OpenAPI document declares "POST" "/api/v1/tickets/{ticket_id}/return-to-l1" with the responses "200,400,403,404,422"
