Feature: Safe integer division

  As a mathematician
  I want to divide two integers safely
  So that divisibility and remainder laws hold.

  Scenario Outline: Happy path division
    When <dividend> is divided by <divisor>
    Then the quotient times divisor plus remainder equals the dividend
    And the remainder is non-negative

    Examples:
      | dividend | divisor | outcome |
      | 10       | 3       | success |
      | 20       | 5       | success |
      | 7        | 2       | success |
      | 0        | 5       | success |
      | 100      | 1       | success |

  Scenario Outline: Division by zero
    When <dividend> is divided by <divisor>
    Then the division is rejected

    Examples:
      | dividend | divisor | outcome             |
      | 10       | 0       | error:DIVISION_ERROR |
      | 0        | 0       | error:DIVISION_ERROR |
