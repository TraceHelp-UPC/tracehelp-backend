Feature: Ticket lifecycle state machine
  As a TraceHelp support team member
  I want ticket status changes to follow the defined lifecycle
  So that no incident skips a stage or is closed without the collaborator's confirmation

  Background:
    Given a workspace with users for every role
    And a ticket reported by the collaborator

  Scenario: Analyst takes a ticket from the queue
    Given the ticket is in status "PENDING_ASSIGNMENT"
    When the "ANALYST_L1" changes the ticket status to "ASSIGNED_L1"
    Then the response status is 200
    And the ticket status is "ASSIGNED_L1"
    And the ticket is assigned to the "ANALYST_L1"

  Scenario Outline: Allowed transitions for the authorized role
    Given the ticket is in status "<from>"
    When the "<role>" changes the ticket status to "<to>"
    Then the response status is 200
    And the ticket status is "<to>"

    Examples:
      | from                  | role          | to                 |
      | OPEN                  | ANALYST_L1    | PENDING_ASSIGNMENT |
      | SELF_SERVICE_PROPOSED | COLLABORATOR  | RESOLVED           |
      | SELF_SERVICE_PROPOSED | COLLABORATOR  | PENDING_ASSIGNMENT |
      | ASSIGNED_L1           | ANALYST_L1    | ESCALATED_L2       |
      | ASSIGNED_L1           | ANALYST_L1    | RESOLVED           |
      | ESCALATED_L2          | SPECIALIST_L2 | RESOLVED           |
      | ESCALATED_L2          | SPECIALIST_L2 | ASSIGNED_L1        |
      | RESOLVED              | COLLABORATOR  | CLOSED             |
      | RESOLVED              | COLLABORATOR  | REOPENED           |

  Scenario Outline: Transitions outside the lifecycle are rejected
    Given the ticket is in status "<from>"
    When the "ANALYST_L1" changes the ticket status to "<to>"
    Then the response status is 422
    And the ticket status is "<from>"

    Examples:
      | from               | to           |
      | OPEN               | CLOSED       |
      | PENDING_ASSIGNMENT | RESOLVED     |
      | CLOSED             | REOPENED     |
      | RESOLVED           | ESCALATED_L2 |

  Scenario Outline: Roles without permission cannot change the status
    Given the ticket is in status "<from>"
    When the "<role>" changes the ticket status to "<to>"
    Then the response status is 403
    And the ticket status is "<from>"

    Examples:
      | from               | role          | to           |
      | PENDING_ASSIGNMENT | COLLABORATOR  | ASSIGNED_L1  |
      | ASSIGNED_L1        | SPECIALIST_L2 | ESCALATED_L2 |
      | ESCALATED_L2       | ANALYST_L1    | RESOLVED     |
      | RESOLVED           | ANALYST_L1    | CLOSED       |
