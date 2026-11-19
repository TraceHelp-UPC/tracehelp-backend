Feature: User and role administration (US09)
  As an IT leader
  I want to manage the users of my workspace and their roles
  So that I control who can access each TraceHelp capability

  Background:
    Given a workspace with these active users, all with password "Segura123":
      | email                   | role          | department    | specialist_group | full_name       |
      | lider@empresa.pe        | IT_LEADER     | Gerencia TI   |                  | Roberto Pérez   |
      | analista@empresa.pe     | ANALYST_L1    | Mesa de ayuda |                  | Karim Ramírez   |
      | colaborador@empresa.pe  | COLLABORATOR  | Ventas        |                  | Ana Salazar     |
      | especialista@empresa.pe | SPECIALIST_L2 | Redes         | REDES            | Carlos Reátegui |
    And the application logs are being captured
    And "lider@empresa.pe" is the acting user

  # --- US09 Escenario 1: datos válidos -> cuenta con el rol indicado ---------------------------------------------

  Scenario: The leader registers a user with valid data and the indicated role
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "Lucia.Torres@empresa.pe", "role": "ANALYST_L1", "department": "Mesa de ayuda"}
      """
    Then the response status is 201
    And the response is not cached
    And the response field "user.email" is "lucia.torres@empresa.pe"
    And the response field "user.role" is "ANALYST_L1"
    And the response field "user.is_active" is "true"
    And the response field "user.specialist_group" is "null"
    And the response field "user.last_login_at" is "null"
    And the temporary password follows the generation policy
    And the response does not expose internal fields

  Scenario: The new user can sign in with the temporary password
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "COLLABORATOR", "department": "Ventas"}
      """
    Then the response status is 201
    And the created user can sign in with the temporary password

  Scenario: The leader registers a specialist with a group
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "SPECIALIST_L2", "department": "Redes y Comunicaciones", "specialist_group": "REDES"}
      """
    Then the response status is 201
    And the response field "user.role" is "SPECIALIST_L2"
    And the response field "user.specialist_group" is "REDES"

  Scenario: A specialist can be registered without a group
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "SPECIALIST_L2", "department": "Redes"}
      """
    Then the response status is 201
    And the response field "user.specialist_group" is "null"

  Scenario: The email is stored in lowercase and surrounding spaces are removed
    When the acting user creates a user with the payload
      """
      {"full_name": "   Lucía Torres   ", "email": "LUCIA.TORRES@EMPRESA.PE", "role": "COLLABORATOR", "department": "  Ventas  "}
      """
    Then the response status is 201
    And the response field "user.email" is "lucia.torres@empresa.pe"
    And the response field "user.full_name" is "Lucía Torres"
    And the response field "user.department" is "Ventas"

  Scenario: Two registrations generate different temporary passwords
    When the acting user creates a user with the payload
      """
      {"full_name": "Uno", "email": "uno@empresa.pe", "role": "COLLABORATOR", "department": "Ventas"}
      """
    And the temporary password is remembered
    And the acting user creates a user with the payload
      """
      {"full_name": "Dos", "email": "dos@empresa.pe", "role": "COLLABORATOR", "department": "Ventas"}
      """
    Then the temporary password differs from the remembered one

  # --- Contraseña temporal: una sola vez, nunca en auditoría ni logs ---------------------------------------------

  Scenario: The temporary password is audited nowhere and never listed
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "ANALYST_L1", "department": "Mesa de ayuda"}
      """
    Then the response status is 201
    And the audit log has a "UserRegistered" entry for "lucia.torres@empresa.pe" acted by "lider@empresa.pe"
    And the audit entry detail field "source" is "admin"
    And the audit entry detail field "role" is "ANALYST_L1"
    And the temporary password does not appear in any audit entry
    And the temporary password does not appear in the captured logs
    When the acting user lists users with query "search=lucia"
    Then the response status is 200
    And the response field "total" is "1"
    And the temporary password does not appear in the response body
    And the response does not expose internal fields

  # --- US09 Escenario 2: rol no permitido -> rechazo -------------------------------------------------------------

  Scenario Outline: Registration is rejected when the role is not one of the allowed roles
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "<role>", "department": "Ventas"}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "role"
    And no user "lucia.torres@empresa.pe" exists

    Examples:
      | role       |
      | SUPERADMIN |
      | analyst_l1 |
      | ADMIN      |
      |            |

  Scenario: Registration is rejected when the role is missing
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "department": "Ventas"}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "role"

  Scenario: A specialist group is rejected for a role that is not SPECIALIST_L2
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "ANALYST_L1", "department": "Ventas", "specialist_group": "REDES"}
      """
    Then the response status is 422
    And the problem type is "specialist-group-not-allowed"
    And no user "lucia.torres@empresa.pe" exists

  Scenario: A specialist group outside the catalogue is rejected
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "SPECIALIST_L2", "department": "Redes", "specialist_group": "MARKETING"}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "specialist_group"

  Scenario: The client cannot choose the password
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "ANALYST_L1", "department": "Ventas", "password": "Elegida123"}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And no user "lucia.torres@empresa.pe" exists

  Scenario: Unknown fields in the registration are rejected
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "ANALYST_L1", "department": "Ventas", "is_admin": true}
      """
    Then the response status is 422
    And the problem type is "validation-error"

  Scenario Outline: Registration is rejected when required data is missing or malformed
    When the acting user creates a user with the payload
      """
      <payload>
      """
    Then the response status is <status>
    And the problem type is "<problem>"

    Examples:
      | payload                                                                                       | status | problem           |
      | {"email": "a@empresa.pe", "role": "ANALYST_L1", "department": "TI"}                           | 422    | validation-error  |
      | {"full_name": "Ana", "role": "ANALYST_L1", "department": "TI"}                                | 422    | validation-error  |
      | {"full_name": "Ana", "email": "a@empresa.pe", "role": "ANALYST_L1"}                           | 422    | validation-error  |
      | {"full_name": "Ana", "email": "correo-sin-formato", "role": "ANALYST_L1", "department": "TI"} | 400    | invalid-email     |
      | {"full_name": "   ", "email": "a@empresa.pe", "role": "ANALYST_L1", "department": "TI"}       | 400    | invalid-user-data |
      | {"full_name": "Ana", "email": "a@empresa.pe", "role": "ANALYST_L1", "department": "   "}      | 400    | invalid-user-data |
      | {"full_name": "", "email": "a@empresa.pe", "role": "ANALYST_L1", "department": "TI"}         | 422    | validation-error  |
      | {"full_name": "Ana", "email": "a@empresa.pe", "role": "ANALYST_L1", "department": ""}        | 422    | validation-error  |

  # --- US09 Escenario 3: usuario ya registrado -> rechazo --------------------------------------------------------

  Scenario: Registration is rejected when the email is already registered, ignoring case
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "Lucia.Torres@empresa.pe", "role": "ANALYST_L1", "department": "Ventas"}
      """
    Then the response status is 201
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "COLLABORATOR", "department": "Ventas"}
      """
    Then the response status is 409
    And the problem type is "email-already-registered"
    And the error detail says "Ya existe una cuenta con el correo lucia.torres@empresa.pe."
    And the workspace has 5 users

  Scenario: Registration is rejected when the email belongs to an existing user
    When the acting user creates a user with the payload
      """
      {"full_name": "Otro Líder", "email": "LIDER@empresa.pe", "role": "IT_LEADER", "department": "TI"}
      """
    Then the response status is 409
    And the problem type is "email-already-registered"

  Scenario: Registration is rejected when the email belongs to a deactivated account
    Given the user "analista@empresa.pe" has been deactivated
    When the acting user creates a user with the payload
      """
      {"full_name": "Karim Otra Vez", "email": "analista@empresa.pe", "role": "ANALYST_L1", "department": "TI"}
      """
    Then the response status is 409
    And the problem type is "email-already-registered"

  Scenario: Registration is rejected when the email belongs to another workspace
    Given an active user "externo@otra.pe" with role "COLLABORATOR" in another workspace
    When the acting user creates a user with the payload
      """
      {"full_name": "Externo", "email": "externo@otra.pe", "role": "COLLABORATOR", "department": "TI"}
      """
    Then the response status is 409
    And the problem type is "email-already-registered"
    And the error detail does not mention a workspace

  Scenario: Two simultaneous registrations of the same email end in a conflict, not a server error
    Given the duplicate-email pre-check is bypassed as in a concurrent request
    When the acting user creates a user with the payload
      """
      {"full_name": "Karim Doble", "email": "analista@empresa.pe", "role": "ANALYST_L1", "department": "TI"}
      """
    Then the response status is 409
    And the problem type is "email-already-registered"

  # --- Acceso: autenticación y permiso iam:admin -----------------------------------------------------------------

  Scenario Outline: Users without the iam:admin permission cannot administer users
    Given "<actor>" is the acting user
    When the acting user requests "<operation>" on the users API
    Then the response status is 403
    And the problem type is "forbidden"

    Examples:
      | actor                   | operation |
      | analista@empresa.pe     | GET       |
      | analista@empresa.pe     | POST      |
      | analista@empresa.pe     | PATCH     |
      | colaborador@empresa.pe  | GET       |
      | colaborador@empresa.pe  | POST      |
      | colaborador@empresa.pe  | PATCH     |
      | especialista@empresa.pe | GET       |
      | especialista@empresa.pe | POST      |
      | especialista@empresa.pe | PATCH     |

  Scenario: A forbidden registration creates nothing
    Given "analista@empresa.pe" is the acting user
    When the acting user creates a user with the payload
      """
      {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "IT_LEADER", "department": "TI"}
      """
    Then the response status is 403
    And no user "lucia.torres@empresa.pe" exists

  Scenario: A non-leader cannot promote themselves
    Given "analista@empresa.pe" is the acting user
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"role": "IT_LEADER"}
      """
    Then the response status is 403
    And the user "analista@empresa.pe" has the role "ANALYST_L1"

  Scenario Outline: Requests without a token are rejected
    Given there is no acting user
    When the acting user requests "<operation>" on the users API
    Then the response status is 401
    And the problem type is "unauthorized"

    Examples:
      | operation |
      | GET       |
      | POST      |
      | PATCH     |

  Scenario: A malformed token is rejected
    Given the acting user presents the token "no-es-un-jwt"
    When the acting user lists users without filters
    Then the response status is 401

  # --- Desactivación: el usuario desactivado no puede iniciar sesión ---------------------------------------------

  Scenario: A deactivated user cannot sign in or renew the session
    Given the user "analista@empresa.pe" has signed in with password "Segura123"
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"is_active": false}
      """
    Then the response status is 200
    And the response field "is_active" is "false"
    And the response field "status" is "INACTIVE"
    And the response field "availability_status" is "UNAVAILABLE"
    When the user signs in with email "analista@empresa.pe" and password "Segura123"
    Then the response status is 403
    When the client requests a new access token with the refresh token
    Then the response status is 401
    When the user requests their profile with the access token
    Then the response status is 401

  Scenario: Deactivation is audited with the leader as actor
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"is_active": false}
      """
    Then the response status is 200
    And the audit log has a "UserDeactivated" entry for "analista@empresa.pe" acted by "lider@empresa.pe"

  Scenario: A reactivated user can sign in again but stays unavailable
    Given the user "analista@empresa.pe" has been deactivated
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"is_active": true}
      """
    Then the response status is 200
    And the response field "status" is "ACTIVE"
    And the response field "availability_status" is "UNAVAILABLE"
    And the audit log has a "UserReactivated" entry for "analista@empresa.pe" acted by "lider@empresa.pe"
    When the user signs in with email "analista@empresa.pe" and password "Segura123"
    Then the response status is 200

  Scenario: Deactivating an already inactive user changes nothing
    Given the user "analista@empresa.pe" has been deactivated
    And the audit log is cleared
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"is_active": false}
      """
    Then the response status is 200
    And the response field "status" is "INACTIVE"
    And the audit log has no entries

  # --- Protección de uno mismo (self-lockout) --------------------------------------------------------------------

  Scenario: The leader cannot remove their own role
    When the acting user updates the user "lider@empresa.pe" with the payload
      """
      {"role": "ANALYST_L1"}
      """
    Then the response status is 422
    And the problem type is "self-lockout"
    And the user "lider@empresa.pe" has the role "IT_LEADER"

  Scenario: The leader cannot deactivate their own account
    When the acting user updates the user "lider@empresa.pe" with the payload
      """
      {"is_active": false}
      """
    Then the response status is 422
    And the problem type is "self-lockout"
    And the user "lider@empresa.pe" is active

  Scenario: The leader cannot lock themselves out in a combined update
    When the acting user updates the user "lider@empresa.pe" with the payload
      """
      {"department": "Otra área", "role": "COLLABORATOR"}
      """
    Then the response status is 422
    And the problem type is "self-lockout"
    And the user "lider@empresa.pe" has the department "Gerencia TI"

  Scenario: The leader can still change their own department and keep their role
    When the acting user updates the user "lider@empresa.pe" with the payload
      """
      {"role": "IT_LEADER", "department": "Dirección de TI", "is_active": true}
      """
    Then the response status is 200
    And the response field "role" is "IT_LEADER"
    And the response field "department" is "Dirección de TI"

  # --- Cambio de rol y grupo -------------------------------------------------------------------------------------

  Scenario: Changing a specialist to another role clears the group
    When the acting user updates the user "especialista@empresa.pe" with the payload
      """
      {"role": "ANALYST_L1"}
      """
    Then the response status is 200
    And the response field "role" is "ANALYST_L1"
    And the response field "specialist_group" is "null"
    And the audit log has a "UserRoleChanged" entry for "especialista@empresa.pe" acted by "lider@empresa.pe"
    And the audit entry detail field "previous_role" is "SPECIALIST_L2"
    And the audit entry detail field "new_role" is "ANALYST_L1"
    And the audit log has a "UserProfileUpdated" entry for "especialista@empresa.pe" acted by "lider@empresa.pe"

  Scenario: Promoting an analyst to specialist with a group in the same request
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"role": "SPECIALIST_L2", "specialist_group": "SEGURIDAD"}
      """
    Then the response status is 200
    And the response field "role" is "SPECIALIST_L2"
    And the response field "specialist_group" is "SEGURIDAD"

  Scenario: Assigning a group to a user that is not a specialist is rejected
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"specialist_group": "REDES"}
      """
    Then the response status is 422
    And the problem type is "specialist-group-not-allowed"
    And the user "analista@empresa.pe" has no specialist group

  Scenario: Changing the role and the group together is rejected when the resulting role is not a specialist
    When the acting user updates the user "especialista@empresa.pe" with the payload
      """
      {"role": "COLLABORATOR", "specialist_group": "SEGURIDAD"}
      """
    Then the response status is 422
    And the problem type is "specialist-group-not-allowed"

  Scenario: An explicit null removes the group of a specialist
    When the acting user updates the user "especialista@empresa.pe" with the payload
      """
      {"specialist_group": null}
      """
    Then the response status is 200
    And the response field "role" is "SPECIALIST_L2"
    And the response field "specialist_group" is "null"

  Scenario: Omitting the group keeps it when other fields change
    When the acting user updates the user "especialista@empresa.pe" with the payload
      """
      {"department": "Redes y Telecom"}
      """
    Then the response status is 200
    And the response field "specialist_group" is "REDES"
    And the response field "department" is "Redes y Telecom"
    And the audit log has a "UserProfileUpdated" entry for "especialista@empresa.pe" acted by "lider@empresa.pe"

  Scenario: A specialist can move to another group
    When the acting user updates the user "especialista@empresa.pe" with the payload
      """
      {"specialist_group": "APLICACIONES"}
      """
    Then the response status is 200
    And the response field "specialist_group" is "APLICACIONES"

  Scenario: The database rejects invalid groups even if the service is bypassed
    Then the database refuses the group "REDES" on the user "analista@empresa.pe"
    And the database refuses the group "MARKETING" on the user "especialista@empresa.pe"

  # --- PATCH: validación y casos límite --------------------------------------------------------------------------

  Scenario Outline: The update is rejected when the body is not valid
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      <payload>
      """
    Then the response status is 422
    And the problem type is "validation-error"

    Examples:
      | payload                      |
      | {}                           |
      | {"role": "SUPERADMIN"}       |
      | {"role": null}               |
      | {"is_active": "false"}       |
      | {"is_active": null}          |
      | {"department": ""}           |
      | {"specialist_group": "XYZ"}  |
      | {"email": "otro@empresa.pe"} |
      | {"password": "Nueva12345"}   |

  Scenario: An update without real changes answers 200 and records nothing
    Given the audit log is cleared
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"role": "ANALYST_L1", "department": "Mesa de ayuda", "is_active": true}
      """
    Then the response status is 200
    And the response field "role" is "ANALYST_L1"
    And the audit log has no entries

  Scenario: A blank department in the update is rejected by the domain
    When the acting user updates the user "analista@empresa.pe" with the payload
      """
      {"department": "    "}
      """
    Then the response status is 400
    And the problem type is "invalid-user-data"

  Scenario: Updating a user that does not exist
    When the acting user updates the user with id "00000000-0000-4000-8000-0000000000aa" with the payload
      """
      {"role": "COLLABORATOR"}
      """
    Then the response status is 404
    And the problem type is "user-not-found"

  Scenario: Updating a user of another workspace answers as if it did not exist
    Given an active user "externo@otra.pe" with role "COLLABORATOR" in another workspace
    When the acting user updates the user "externo@otra.pe" with the payload
      """
      {"is_active": false}
      """
    Then the response status is 404
    And the problem type is "user-not-found"
    And the user "externo@otra.pe" is active

  Scenario: A user id that is not a UUID is rejected
    When the acting user updates the user with id "no-es-uuid" with the payload
      """
      {"role": "COLLABORATOR"}
      """
    Then the response status is 422

  # --- Listado: filtros y paginación -----------------------------------------------------------------------------

  Scenario: The listing returns only the users of the workspace, ordered by name
    Given an active user "externo@otra.pe" with role "COLLABORATOR" in another workspace
    When the acting user lists users without filters
    Then the response status is 200
    And the listing has these emails in order
      | email                   |
      | colaborador@empresa.pe  |
      | especialista@empresa.pe |
      | analista@empresa.pe     |
      | lider@empresa.pe        |
    And the response field "total" is "4"
    And the response field "page" is "1"
    And the response field "size" is "20"
    And the response field "total_pages" is "1"
    And the response does not expose internal fields

  Scenario: The listing is filtered by role
    When the acting user lists users with query "role=SPECIALIST_L2"
    Then the response status is 200
    And the listing has these emails in order
      | email                   |
      | especialista@empresa.pe |

  Scenario: The listing is filtered by specialist group
    Given the user "analista@empresa.pe" is promoted to specialist of group "SEGURIDAD"
    When the acting user lists users with query "specialist_group=SEGURIDAD"
    Then the response status is 200
    And the listing has these emails in order
      | email               |
      | analista@empresa.pe |

  Scenario: The listing is filtered by active status
    Given the user "analista@empresa.pe" has been deactivated
    When the acting user lists users with query "is_active=false"
    Then the response status is 200
    And the listing has these emails in order
      | email               |
      | analista@empresa.pe |
    When the acting user lists users with query "is_active=true"
    Then the response field "total" is "3"

  Scenario Outline: The listing is searched by name or email ignoring case and surrounding spaces
    When the acting user lists users with query "search=<search>"
    Then the response status is 200
    And the response field "total" is "1"
    And the listing contains the email "<email>"

    Examples:
      | search          | email                   |
      | KARIM           | analista@empresa.pe     |
      | CARLOS          | especialista@empresa.pe |
      | COLABORADOR@    | colaborador@empresa.pe  |
      | %20%20salazar%20%20 | colaborador@empresa.pe  |

  Scenario: A search without matches returns an empty page
    When the acting user lists users with query "search=zzzzzz"
    Then the response status is 200
    And the response field "total" is "0"
    And the response field "total_pages" is "0"

  Scenario: A blank search does not filter
    When the acting user lists users with query "search=%20%20"
    Then the response status is 200
    And the response field "total" is "4"

  Scenario: Filters are combined
    When the acting user lists users with query "role=ANALYST_L1&is_active=true&search=karim"
    Then the response status is 200
    And the response field "total" is "1"
    When the acting user lists users with query "role=COLLABORATOR&search=karim"
    Then the response field "total" is "0"

  Scenario: The listing is paginated
    When the acting user lists users with query "size=3&page=1"
    Then the response status is 200
    And the response field "total" is "4"
    And the response field "total_pages" is "2"
    And the listing has 3 items
    When the acting user lists users with query "size=3&page=2"
    Then the response status is 200
    And the listing has 1 items
    And the listing contains the email "lider@empresa.pe"

  Scenario Outline: The listing rejects an invalid page request
    When the acting user lists users with query "<query>"
    Then the response status is 400
    And the problem type is "invalid-page-request"

    Examples:
      | query         |
      | size=101      |
      | size=0        |
      | page=0        |
      | size=3&page=3 |

  Scenario Outline: The listing rejects values outside the enums
    When the acting user lists users with query "<query>"
    Then the response status is 422
    And the problem type is "validation-error"

    Examples:
      | query                      |
      | role=SUPERADMIN            |
      | specialist_group=MARKETING |
      | is_active=quizas           |

  # --- Contrato publicado en Swagger -----------------------------------------------------------------------------

  Scenario: The OpenAPI document describes the user administration routes
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI document declares "GET" "/api/v1/users" with the responses "200,400,401,403"
    And the OpenAPI document declares "POST" "/api/v1/users" with the responses "201,400,401,403,409,422"
    And the OpenAPI document declares "PATCH" "/api/v1/users/{user_id}" with the responses "200,401,403,404,422"
    And the OpenAPI document has no route "/api/v1/users/{user_id}/role"
