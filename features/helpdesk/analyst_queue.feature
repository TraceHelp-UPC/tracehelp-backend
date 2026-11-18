Feature: Analyst ticket queue
  As a support analyst
  I want my queue ordered by priority and age, with filters
  So that I always attend the most urgent incident first

  Background:
    Given a workspace with users for every role
    And these tickets in the workspace:
      | title                 | priority | status             | assigned_to   | hours_ago |
      | Impresora del piso 3  | LOW      | PENDING_ASSIGNMENT |               | 5         |
      | ERP caído en ventas   | CRITICAL | PENDING_ASSIGNMENT |               | 1         |
      | VPN error 809         | HIGH     | PENDING_ASSIGNMENT |               | 6         |
      | Outlook desconectado  | HIGH     | PENDING_ASSIGNMENT |               | 2         |
      | Carpeta S: sin acceso | MEDIUM   | ASSIGNED_L1        | ANALYST_L1    | 3         |
      | Teams sin audio       | HIGH     | ASSIGNED_L1        | ANALYST_L1    | 4         |
      | Base de datos lenta   | CRITICAL | ESCALATED_L2       | ANALYST_L1    | 8         |
      | Cuenta bloqueada      | HIGH     | ASSIGNED_L1        | OTHER_ANALYST | 1         |
      | Monitor parpadea      | MEDIUM   | RESOLVED           | ANALYST_L1    | 9         |

  Scenario: Pending tickets are ordered by priority and then by age
    When the "ANALYST_L1" opens the "unassigned" queue
    Then the response status is 200
    And the queue shows these tickets in order:
      | title                |
      | ERP caído en ventas  |
      | VPN error 809        |
      | Outlook desconectado |
      | Impresora del piso 3 |
    And each ticket in the queue shows who reported it

  Scenario: My queue only shows the open tickets assigned to me
    When the "ANALYST_L1" opens the "mine" queue
    Then the response status is 200
    And the queue shows these tickets in order:
      | title                 |
      | Base de datos lenta   |
      | Teams sin audio       |
      | Carpeta S: sin acceso |

  Scenario: Attending a pending ticket moves it to my queue
    When the "ANALYST_L1" attends the ticket "VPN error 809"
    And the "ANALYST_L1" opens the "unassigned" queue
    Then the queue does not show the ticket "VPN error 809"
    When the "ANALYST_L1" opens the "mine" queue
    Then the queue shows the ticket "VPN error 809" assigned to the "ANALYST_L1"

  Scenario: The specialist sees the tickets escalated to level 2
    When the "SPECIALIST_L2" opens the "escalated" queue
    Then the response status is 200
    And the queue shows these tickets in order:
      | title               |
      | Base de datos lenta |

  Scenario Outline: Analysts filter the queue
    When the "ANALYST_L1" opens the "all" queue with "<filters>"
    Then the response status is 200
    And the queue shows these tickets in order:
      | title     |
      | <first>   |
      | <second>  |

    Examples:
      | filters                  | first                | second                |
      | priority=CRITICAL        | Base de datos lenta  | ERP caído en ventas   |
      | search=vpn               | VPN error 809        |                       |
      | priority=HIGH&search=out | Outlook desconectado |                       |
      | search=sin               | Teams sin audio      | Carpeta S: sin acceso |

  Scenario: Filters without matches return an empty queue
    When the "ANALYST_L1" opens the "all" queue with "search=impresora&priority=CRITICAL"
    Then the response status is 200
    And the queue is empty

  Scenario: An analyst without tickets assigned has an empty queue
    When the "OTHER_ANALYST" opens the "mine" queue
    Then the response status is 200
    And the queue shows these tickets in order:
      | title            |
      | Cuenta bloqueada |
    When the "SPECIALIST_L2" opens the "mine" queue
    Then the response status is 200
    And the queue is empty

  Scenario: Collaborators cannot open the support queue
    When the "COLLABORATOR" opens the "unassigned" queue
    Then the response status is 403

  Scenario: Analyst changes their availability
    When the "ANALYST_L1" changes their availability to "UNAVAILABLE"
    Then the response status is 200
    And the "ANALYST_L1" appears as "UNAVAILABLE"
    When the "ANALYST_L1" changes their availability to "AVAILABLE"
    Then the "ANALYST_L1" appears as "AVAILABLE"
