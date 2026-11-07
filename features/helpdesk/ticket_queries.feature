Feature: Ticket query endpoints
  As a collaborator or a support analyst
  I want to browse tickets page by page and open their detail
  So that I can follow up incidents without seeing tickets that are not mine

  Background:
    Given a workspace with users for every role
    And another collaborator in the same workspace
    And the collaborator has reported 5 tickets

  Scenario: Collaborator browses their ticket history page by page
    When the "COLLABORATOR" requests their ticket history page 1 with 2 tickets per page
    Then the response status is 200
    And the page shows these tickets:
      | title       |
      | Incidente 5 |
      | Incidente 4 |
    And the pagination shows page 1 of 3 with 5 tickets
    When the "COLLABORATOR" requests their ticket history page 3 with 2 tickets per page
    Then the response status is 200
    And the page shows these tickets:
      | title       |
      | Incidente 1 |
    And the pagination shows page 3 of 3 with 5 tickets

  Scenario: The history only includes the tickets the collaborator reported
    Given the other collaborator has reported a ticket titled "Ticket ajeno"
    When the "COLLABORATOR" requests their ticket history page 1 with 20 tickets per page
    Then the response status is 200
    And the pagination shows page 1 of 1 with 5 tickets
    And the page does not show the ticket "Ticket ajeno"

  Scenario: A collaborator without tickets gets an empty first page
    When the other collaborator requests their ticket history
    Then the response status is 200
    And the page is empty

  Scenario: Collaborator opens the detail of their own ticket
    When the "COLLABORATOR" opens the detail of the ticket "Incidente 3"
    Then the response status is 200
    And the detail shows the ticket "Incidente 3" reported by the collaborator

  Scenario: A collaborator cannot open a ticket reported by someone else
    When the other collaborator opens the detail of the ticket "Incidente 3"
    Then the response status is 403
    And the error is reported as problem details
    And the error detail mentions "No tienes acceso a este ticket"

  Scenario Outline: Support staff can open any ticket of the workspace
    When the "<role>" opens the detail of the ticket "Incidente 3"
    Then the response status is 200

    Examples:
      | role          |
      | ANALYST_L1    |
      | SPECIALIST_L2 |

  Scenario: Opening a ticket that does not exist
    When the "ANALYST_L1" opens the detail of a nonexistent ticket
    Then the response status is 404
    And the error is reported as problem details

  Scenario Outline: Pagination out of range is rejected
    When the "COLLABORATOR" requests their ticket history with "<query>"
    Then the response status is 400
    And the error is reported as problem details
    And the error detail mentions "<message>"

    Examples:
      | query           | message                |
      | page=4&size=2   | La página 4 no existe  |
      | page=0          | debe ser 1 o mayor     |
      | size=101        | entre 1 y 100          |

  Scenario: The analyst queue also rejects pages out of range
    When the "ANALYST_L1" opens the "all" queue with "page=99&size=10"
    Then the response status is 400
    And the error detail mentions "La página 99 no existe"
