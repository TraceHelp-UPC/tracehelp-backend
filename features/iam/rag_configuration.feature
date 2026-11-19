Feature: RAG engine configuration per workspace (US07)
  As an IT leader
  I want to consult and update the RAG engine parameters for my workspace
  So that evidence retrieval, self-service thresholds, and grounding strictness adapt to our manuals without restarting

  Background:
    Given a workspace with users for every role

  # --- Valores por defecto iniciales --------------------------------------------------------------------------

  Scenario: Workspace without saved RAG configuration returns initial defaults
    When the "IT_LEADER" requests the RAG configuration
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | 0.68 |
      | self_service_threshold | 0.80 |
      | retrieval_top_k        | 5    |
      | strict_grounding       | true |
      | is_default             | true |
    And the RAG thresholds are serialized as JSON numbers
    And the RAG configuration has no modification metadata
    And the RAG configuration includes defaults and calibration limits

  # --- Actualización válida, lectura posterior y auditoría -----------------------------------------------------

  Scenario: Leader updates RAG parameters, persists them, and records ConfigurationChanged in audit log
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.72                 | 0.85                   | 7               | true             |
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | 0.72  |
      | self_service_threshold | 0.85  |
      | retrieval_top_k        | 7     |
      | strict_grounding       | true  |
      | is_default             | false |
    And the RAG modification metadata shows the "IT_LEADER"
    When the "IT_LEADER" requests the RAG configuration
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | 0.72  |
      | self_service_threshold | 0.85  |
      | retrieval_top_k        | 7     |
      | strict_grounding       | true  |
      | is_default             | false |
    And the audit log records 1 "ConfigurationChanged" entry for section "rag" acted by "IT_LEADER"
    And the last RAG audit entry records exactly these changes:
      | field                  | old  | new  |
      | similarity_threshold   | 0.68 | 0.72 |
      | self_service_threshold | 0.80 | 0.85 |
      | retrieval_top_k        | 5    | 7    |

  Scenario Outline: Leader updates RAG parameters with valid exact boundary and warning-zone values
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | <similarity>         | <self_service>         | <top_k>         | <strict>         |
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | <similarity>   |
      | self_service_threshold | <self_service> |
      | retrieval_top_k        | <top_k>        |
      | strict_grounding       | <strict>       |
      | is_default             | false          |

    Examples:
      | similarity | self_service | top_k | strict |
      | 0.50       | 0.50         | 1     | false  |
      | 0.95       | 0.99         | 10    | true   |
      | 0.58       | 0.80         | 5     | true   |

  # --- Validación de rangos, decimales y campos (422 Problem Details) ------------------------------------------

  Scenario Outline: Invalid RAG parameter values are rejected with 422 without altering previous configuration
    Given the "IT_LEADER" updated the RAG configuration to 0.70, 0.85, 5, true
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | <similarity>         | <self_service>         | <top_k>         | <strict>         |
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "<error_field>"
    When the "IT_LEADER" requests the RAG configuration
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | 0.70 |
      | self_service_threshold | 0.85 |
      | retrieval_top_k        | 5    |
      | strict_grounding       | true |

    Examples:
      | similarity | self_service | top_k | strict | error_field            |
      | 0.30       | 0.85         | 5     | true   | similarity_threshold   |
      | 0.96       | 0.98         | 5     | true   | similarity_threshold   |
      | 0.75       | 0.70         | 5     | true   | self_service_threshold |
      | 0.75       | 1.00         | 5     | true   | self_service_threshold |
      | 0.725      | 0.85         | 5     | true   | similarity_threshold   |
      | 0.72       | 0.855        | 5     | true   | self_service_threshold |
      | 0.72       | 0.85         | 0     | true   | retrieval_top_k        |
      | 0.72       | 0.85         | 11    | true   | retrieval_top_k        |

  Scenario: Missing required field, unknown property, and invalid boolean type are rejected with 422
    When the "IT_LEADER" sends the raw RAG configuration payload:
      """
      {"similarity_threshold": 0.72, "self_service_threshold": 0.85, "retrieval_top_k": 5}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "strict_grounding"
    When the "IT_LEADER" sends the raw RAG configuration payload:
      """
      {"similarity_threshold": 0.72, "self_service_threshold": 0.85, "retrieval_top_k": 5, "strict_grounding": true, "extra_field": 1}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "extra_field"
    When the "IT_LEADER" sends the raw RAG configuration payload:
      """
      {"similarity_threshold": 0.72, "self_service_threshold": 0.85, "retrieval_top_k": 5, "strict_grounding": "si"}
      """
    Then the response status is 422
    And the problem type is "validation-error"
    And the first error field is "strict_grounding"

  # --- Seguridad y permisos (401 / 403) ------------------------------------------------------------------------

  Scenario Outline: Roles without analytics:read cannot read RAG configuration
    When the "<role>" requests the RAG configuration
    Then the response status is 403
    And the problem type is "forbidden"
    And the error detail says "Tu rol no tiene el permiso requerido: analytics:read."

    Examples:
      | role          |
      | ANALYST_L1    |
      | SPECIALIST_L2 |
      | COLLABORATOR  |

  Scenario Outline: Roles without config:write cannot update RAG configuration
    When the "<role>" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.72                 | 0.85                   | 5               | true             |
    Then the response status is 403
    And the problem type is "forbidden"
    And the error detail says "Tu rol no tiene el permiso requerido: config:write."

    Examples:
      | role          |
      | ANALYST_L1    |
      | SPECIALIST_L2 |
      | COLLABORATOR  |

  Scenario: Unauthenticated or invalid-token requests to RAG configuration receive 401
    When an unauthenticated client requests the RAG configuration
    Then the response status is 401
    And the problem type is "unauthorized"
    When an unauthenticated client updates the RAG configuration
    Then the response status is 401
    And the problem type is "unauthorized"
    When a client with invalid token requests the RAG configuration
    Then the response status is 401
    And the problem type is "unauthorized"

  Scenario: Authorization is checked before body validation on PUT /config/rag
    When the "ANALYST_L1" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.10                 | 0.05                   | 99              | true             |
    Then the response status is 403
    And the problem type is "forbidden"

  # --- Guardado sin cambios (no-op) ----------------------------------------------------------------------------

  Scenario: Saving unchanged RAG parameters does not touch updated_at or emit extra audit entries
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.68                 | 0.80                   | 5               | true             |
    Then the response status is 200
    And the RAG configuration response has:
      | is_default | true |
    And the RAG configuration has no modification metadata
    And the audit log records 0 "ConfigurationChanged" entries for section "rag"
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.72                 | 0.85                   | 6               | true             |
    Then the response status is 200
    And the RAG modification timestamp is remembered
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.72                 | 0.85                   | 6               | true             |
    Then the response status is 200
    And the RAG modification timestamp matches the remembered one
    And the audit log records 1 "ConfigurationChanged" entry for section "rag" acted by "IT_LEADER"

  # --- Efecto inmediato en Smart Triage y strict_grounding -----------------------------------------------------

  Scenario: Updating similarity_threshold and top_k takes immediate effect in evidence search without restart
    Given smart triage reads workspace RAG settings with a simulated retriever returning similarity 0.70
    When the "IT_LEADER" searches the manuals for "error 809 vpn"
    Then the response status is 200
    And the evidence search confidence level is "GROUNDED"
    And the evidence search reports similarity threshold 0.68 and retrieved top_k 5
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.72                 | 0.85                   | 8               | true             |
    Then the response status is 200
    When the "IT_LEADER" searches the manuals for "error 809 vpn"
    Then the response status is 200
    And the evidence search confidence level is "LOW_CONFIDENCE"
    And the evidence search reports similarity threshold 0.72 and retrieved top_k 8

  Scenario: Toggling strict_grounding changes uncited LLM draft handling and avoids self-service without citations
    Given smart triage reads workspace RAG settings with similarity 0.90 and an uncited LLM answer
    When the "IT_LEADER" requests a diagnosis preview for "error 809 vpn"
    Then the response status is 200
    And the preview status is "INVALID_RESPONSE"
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.68                 | 0.80                   | 5               | false            |
    Then the response status is 200
    When the "IT_LEADER" requests a diagnosis preview for "error 809 vpn"
    Then the response status is 200
    And the preview status is "ANSWERED"
    And the preview diagnosis has 0 sources
    When automatic triage processes a ticket for "error 809 vpn" using the workspace RAG settings
    Then the resulting triage diagnosis has review status "PENDING_REVIEW" and 0 sources

  # --- Aislamiento multi-workspace y contrato OpenAPI ----------------------------------------------------------

  Scenario: RAG configuration changes are isolated per workspace
    Given a second workspace with its own IT leader
    When the "IT_LEADER" updates the RAG configuration with:
      | similarity_threshold | self_service_threshold | retrieval_top_k | strict_grounding |
      | 0.80                 | 0.90                   | 9               | false            |
    Then the response status is 200
    When the leader of the second workspace requests the RAG configuration
    Then the response status is 200
    And the RAG configuration response has:
      | similarity_threshold   | 0.68  |
      | self_service_threshold | 0.80  |
      | retrieval_top_k        | 5     |
      | strict_grounding       | true  |
      | is_default             | true  |

  Scenario: OpenAPI documents GET and PUT /api/v1/config/rag with expected responses
    When the client requests the OpenAPI document
    Then the response status is 200
    And the OpenAPI document declares "GET" "/api/v1/config/rag" with the responses "200,401,403"
    And the OpenAPI document declares "PUT" "/api/v1/config/rag" with the responses "200,401,403,422"
