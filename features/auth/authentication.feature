Feature: Corporate Authentication with JWT
  As a TraceHelp user
  I want to sign in with my corporate credentials
  So that I can access the features allowed for my role

  Background:
    Given an active user "karim.ramirez@empresa.pe" with password "Segura123" and role "ANALYST_L1"

  Scenario: Successful login with valid credentials
    When the user signs in with email "karim.ramirez@empresa.pe" and password "Segura123"
    Then the response status is 200
    And the response contains an access token and a refresh token
    And the authenticated user has the role "ANALYST_L1"
    And the access token includes the permission "triage:validate_hitl"

  Scenario Outline: Login rejected with invalid credentials
    When the user signs in with email "<email>" and password "<password>"
    Then the response status is 401

    Examples:
      | email                    | password    |
      | karim.ramirez@empresa.pe | Incorrecta1 |
      | nadie@empresa.pe         | Segura123   |
      | correo-sin-formato       | Segura123   |

  Scenario: Login rejected for an inactive account
    Given the user "karim.ramirez@empresa.pe" has been deactivated
    When the user signs in with email "karim.ramirez@empresa.pe" and password "Segura123"
    Then the response status is 403

  Scenario: Access token renewed with a valid refresh token
    Given the user "karim.ramirez@empresa.pe" has signed in with password "Segura123"
    When the client requests a new access token with the refresh token
    Then the response status is 200
    And the response contains a new access token

  Scenario: Renewal rejected with an invalid refresh token
    When the client requests a new access token with the refresh token "token-invalido"
    Then the response status is 401

  Scenario: Renewal rejected when an access token is sent instead of a refresh token
    Given the user "karim.ramirez@empresa.pe" has signed in with password "Segura123"
    When the client requests a new access token using the access token
    Then the response status is 401
