Feature: Ticket status and message notifications
  As a non-technical collaborator or support team member
  I want to receive in-app and email alerts about ticket status changes and new messages
  So that I stay informed while respecting my channel preferences and keeping message text out of notifications

  Background:
    Given a workspace with users for every role
    And a fake email sender is capturing outgoing emails
    And a ticket reported by the collaborator
    And the ticket is in status "ASSIGNED_L1"

  # ------------------------------------------------------------------ US19, criterio 1: cambio de estado
  Scenario: Analyst resolving a ticket notifies the collaborator in-app and by email without leaking reason text
    When the "ANALYST_L1" changes the ticket status to "RESOLVED" with reason "Clave temporal VPN-99881 reiniciada"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "TICKET_STATUS_CHANGED", read "false" and the ticket code
    And the first notification data has previous_status "ASSIGNED_L1" and new_status "RESOLVED"
    And the first notification does not contain "VPN-99881"
    And 1 fake email was sent to the "COLLABORATOR"
    And the last fake email subject starts with "[TraceHelp] TK-" and contains "Resuelto"
    And the last fake email body includes the no-reply footer and omits "VPN-99881"

  Scenario: Analyst taking an unassigned ticket notifies the collaborator with the Spanish status label
    Given the ticket is in status "PENDING_ASSIGNMENT"
    When the "ANALYST_L1" changes the ticket status to "ASSIGNED_L1"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "TICKET_STATUS_CHANGED", read "false" and the ticket code
    And the first notification title contains "En atención"
    And 1 fake email was sent to the "COLLABORATOR"

  Scenario: Releasing a ticket back to PENDING_ASSIGNMENT does not notify the collaborator
    When the "ANALYST_L1" changes the ticket status to "PENDING_ASSIGNMENT"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 0, total_pages 0 and unread_count 0
    And 0 fake emails were sent

  Scenario Outline: Collaborator's own status changes never notify them
    Given the ticket is in status "<from_status>"
    When the "COLLABORATOR" changes the ticket status to "<to_status>"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 0, total_pages 0 and unread_count 0
    And 0 fake emails were sent

    Examples:
      | from_status           | to_status          |
      | SELF_SERVICE_PROPOSED | RESOLVED           |
      | SELF_SERVICE_PROPOSED | PENDING_ASSIGNMENT |
      | RESOLVED              | CLOSED             |
      | RESOLVED              | REOPENED           |

  Scenario: Resolving an escalated L2 ticket produces a single ESCALATED_TICKET_RESOLVED notification
    Given the ticket is in status "ESCALATED_L2"
    When the specialist resolves the escalated ticket in group "INFRAESTRUCTURA"
    And the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "ESCALATED_TICKET_RESOLVED", read "false" and the ticket code
    And the first notification data has escalated_group "INFRAESTRUCTURA"
    And 1 fake email was sent to the "COLLABORATOR"
    And the last fake email subject starts with "[TraceHelp] TK-" and contains "Resuelto"

  # ------------------------------------------------------------------ US19, criterio 2: mensajes y notas internas
  Scenario: Analyst posting a message notifies the collaborator without leaking the message content
    When the "ANALYST_L1" posts the message "Secreto-XYZ-77441 reiniciar adaptador de red"
    Then the response status is 201
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "MESSAGE_POSTED", read "false" and the ticket code
    And the first notification title starts with "Tienes una nueva respuesta en TK-"
    And the first notification does not contain "Secreto-XYZ-77441"
    When the "ANALYST_L1" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 1 fake email was sent to the "COLLABORATOR"
    And the last fake email body includes the no-reply footer and omits "Secreto-XYZ-77441"

  Scenario: Posting an internal note creates no notification and no email
    When the "ANALYST_L1" posts the internal note "Nota interna solo para TI: revisar firewall"
    Then the response status is 201
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    When the "ANALYST_L1" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 0 fake emails were sent

  Scenario: Collaborator posting a message notifies only the assigned analyst
    When the "COLLABORATOR" posts the message "Adjunto el error que aparece en pantalla"
    Then the response status is 201
    When the "ANALYST_L1" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "MESSAGE_POSTED", read "false" and the ticket code
    And the first notification does not contain "Adjunto el error"
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 1 fake email was sent to the "ANALYST_L1"

  Scenario: Collaborator message on an unassigned or unclaimed escalated ticket notifies nobody
    Given the ticket is in status "PENDING_ASSIGNMENT"
    And the ticket has no assigned analyst
    When the "COLLABORATOR" posts the message "Sigo esperando asignación"
    Then the response status is 201
    Given the ticket is in status "ESCALATED_L2"
    When the "COLLABORATOR" posts the message "Información extra para L2"
    Then the response status is 201
    When the "ANALYST_L1" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    When the "SPECIALIST_L2" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 0 fake emails were sent

  Scenario: Collaborator message on an escalated ticket with an assigned specialist notifies only the specialist
    Given the ticket is in status "ESCALATED_L2"
    When a collaborator MessagePosted event arrives with assigned_specialist_id set to the specialist
    And the "SPECIALIST_L2" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the first notification has type "MESSAGE_POSTED", read "false" and the ticket code
    When the "ANALYST_L1" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 1 fake email was sent to the "SPECIALIST_L2"

  # ------------------------------------------------------------------ US19, criterio 3: canales y preferencias
  Scenario: Disabling email sends 0 emails while keeping in-app notifications
    When the "COLLABORATOR" updates their notification preferences with '{"notify_email": false}'
    Then the response status is 200
    And the response field "notify_inapp" is "true"
    And the response field "notify_email" is "false"
    When the "ANALYST_L1" changes the ticket status to "RESOLVED"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 1, total_pages 1 and unread_count 1
    And 0 fake emails were sent

  Scenario: Disabling in-app skips storing rows while still sending email
    When the "COLLABORATOR" updates their notification preferences with '{"notify_inapp": false, "notify_email": true}'
    Then the response status is 200
    And the response field "notify_inapp" is "false"
    And the response field "notify_email" is "true"
    When the "ANALYST_L1" posts the message "Respuesta solo por correo"
    Then the response status is 201
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 1 fake email was sent to the "COLLABORATOR"

  Scenario: Disabling both channels creates no in-app notification and sends no email
    When the "COLLABORATOR" updates their notification preferences with '{"notify_inapp": false, "notify_email": false}'
    Then the response status is 200
    When the "ANALYST_L1" changes the ticket status to "RESOLVED"
    Then the response status is 200
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 0, total_pages 0 and unread_count 0
    And 0 fake emails were sent

  Scenario: An inactive recipient receives neither in-app notifications nor emails
    Given the "COLLABORATOR" account is marked inactive
    When the "ANALYST_L1" changes the ticket status to "RESOLVED"
    Then the response status is 200
    And the database has 0 notifications for the "COLLABORATOR"
    And 0 fake emails were sent

  Scenario: Forbidden ticket actions generate no notifications and no emails
    When the "COLLABORATOR" posts the internal note "Intento prohibido"
    Then the response status is 403
    And the problem type is "internal-note-not-allowed"
    When the "COLLABORATOR" changes the ticket status to "RESOLVED"
    Then the response status is 403
    And the database has 0 notifications for the "COLLABORATOR"
    And the database has 0 notifications for the "ANALYST_L1"
    And 0 fake emails were sent

  # ------------------------------------------------------------------ Listado, unread_only, paginación y lectura idempotente
  Scenario: Notifications are ordered newest first, support unread_only and mark-as-read is idempotent
    Given the "COLLABORATOR" has 3 seeded notifications where the newest is already read
    When the "COLLABORATOR" requests their notifications with query "size=2&page=1"
    Then the response status is 200
    And the notification listing reports total 3, total_pages 2 and unread_count 2
    And the listed notification titles in order are "Notif 3, Notif 2"
    When the "COLLABORATOR" requests their notifications with query "unread_only=true"
    Then the response status is 200
    And the notification listing reports total 2, total_pages 1 and unread_count 2
    And the listed notification titles in order are "Notif 2, Notif 1"
    When the "COLLABORATOR" marks seeded notification "Notif 2" as read
    Then the response status is 200
    And the response field "read" is "true"
    And the read_at timestamp is remembered
    When the "COLLABORATOR" marks seeded notification "Notif 2" as read
    Then the response status is 200
    And the read_at timestamp matches the remembered value
    When the "COLLABORATOR" requests their notifications
    Then the notification listing reports total 3, total_pages 1 and unread_count 1

  Scenario Outline: Out-of-range pagination on notifications returns 400 invalid-page-request
    Given the "COLLABORATOR" has 3 seeded notifications where the newest is already read
    When the "COLLABORATOR" requests their notifications with query "<query>"
    Then the response status is 400
    And the problem type is "invalid-page-request"

    Examples:
      | query         |
      | page=0        |
      | page=-1       |
      | size=0        |
      | size=101      |
      | page=5&size=2 |

  # ------------------------------------------------------------------ Aislamiento, 404, 422 y 401
  Scenario: Users cannot read or list notifications belonging to another user or another workspace
    Given another collaborator in the same workspace
    And an analyst of another workspace
    And the "COLLABORATOR" has 1 seeded notification named "Propia"
    And the other collaborator has 1 seeded notification named "Ajena mismo workspace"
    And the foreign analyst has 1 seeded notification named "Ajena otro workspace"
    When the "COLLABORATOR" requests their notifications
    Then the response status is 200
    And the notification listing reports total 1, total_pages 1 and unread_count 1
    And the listed notification titles in order are "Propia"
    When the "COLLABORATOR" marks seeded notification "Ajena mismo workspace" as read
    Then the response status is 404
    And the problem type is "notification-not-found"
    When the "COLLABORATOR" marks seeded notification "Ajena otro workspace" as read
    Then the response status is 404
    And the problem type is "notification-not-found"
    When the "COLLABORATOR" marks a nonexistent notification as read
    Then the response status is 404
    And the problem type is "notification-not-found"
    When the "COLLABORATOR" marks notification id "no-es-uuid" as read
    Then the response status is 422
    And the problem type is "validation-error"

  # ------------------------------------------------------------------ Preferencias: roles, auditoría, validación, 401, inactivo
  Scenario Outline: Every authenticated role can read and update their own notification preferences without 403
    When the "<role>" requests their notification preferences
    Then the response status is 200
    And the response field "notify_inapp" is "true"
    And the response field "notify_email" is "true"
    When the "<role>" updates their notification preferences with '{"notify_email": false}'
    Then the response status is 200
    And the response field "notify_inapp" is "true"
    And the response field "notify_email" is "false"

    Examples:
      | role          |
      | COLLABORATOR  |
      | ANALYST_L1    |
      | SPECIALIST_L2 |
      | IT_LEADER     |

  Scenario: Updating notification preferences audits UserProfileUpdated only when values actually change
    Given the audit log of the workspace is empty
    When the "COLLABORATOR" updates their notification preferences with '{"notify_email": false}'
    Then the response status is 200
    And the audit log has 1 "UserProfileUpdated" entry for the "COLLABORATOR" with changes '{"notify_email": {"from": "true", "to": "false"}}'
    When the "COLLABORATOR" updates their notification preferences with '{"notify_email": false}'
    Then the response status is 200
    And the audit log still has 1 "UserProfileUpdated" entry for the "COLLABORATOR"

  Scenario Outline: Invalid notification preference payloads return 422 validation-error
    When the "COLLABORATOR" updates their notification preferences with '<payload>'
    Then the response status is 422
    And the problem type is "validation-error"

    Examples:
      | payload                   |
      | {}                        |
      | {"notify_email": null}    |
      | {"notify_inapp": null}    |
      | {"notify_email": "false"} |
      | {"notify_email": 1}       |
      | {"unknown_channel": true} |

  Scenario: Unauthenticated or invalid-token requests to notifications and preferences are rejected with 401
    Given the "COLLABORATOR" has 1 seeded notification named "Privada"
    When an unauthenticated client calls "GET" "/api/v1/notifications"
    Then the response status is 401
    When an unauthenticated client marks seeded notification "Privada" as read
    Then the response status is 401
    When an unauthenticated client calls "GET" "/api/v1/users/me/notification-preferences"
    Then the response status is 401
    When an unauthenticated client calls "PATCH" "/api/v1/users/me/notification-preferences" with '{"notify_email": false}'
    Then the response status is 401
    When a client with an invalid token calls "GET" "/api/v1/notifications"
    Then the response status is 401
    When a client with an invalid token calls "GET" "/api/v1/users/me/notification-preferences"
    Then the response status is 401

  Scenario: An inactive user with a previously issued token gets 401 on notification preferences
    Given a valid token is cached for the "COLLABORATOR"
    And the "COLLABORATOR" account is marked inactive
    When the cached token requests GET notification preferences
    Then the response status is 401
    When the cached token requests PATCH notification preferences with '{"notify_email": false}'
    Then the response status is 401

  # ------------------------------------------------------------------ Privacidad, auditoría y LogEmailSender
  Scenario: Creating notifications does not write extra audit rows and LogEmailSender masks the recipient email
    Given the audit log of the workspace is empty
    And the default log email sender is active
    And the application logs are being captured
    When the "ANALYST_L1" posts the message "Mensaje-privado-log-55443"
    Then the response status is 201
    And the captured logs mask the "COLLABORATOR" email address
    And the captured logs do not contain "Mensaje-privado-log-55443"
    And the audit log contains no notification event entries

  # ------------------------------------------------------------------ Contrato OpenAPI
  Scenario: OpenAPI documents all notifications and preferences endpoints without duplicate tags
    When the client requests the OpenAPI document
    Then the OpenAPI document declares "GET" "/api/v1/notifications" with the responses "200,400,401"
    And the OpenAPI document declares "PATCH" "/api/v1/notifications/{notification_id}/read" with the responses "200,401,404,422"
    And the OpenAPI document declares preferences endpoints with summary, description, examples and unique tags
