Feature: Funds transfer
  As a bank customer
  I want to transfer funds between accounts
  So that I can move money

  Rule: All account balances are non-negative at all times

  Scenario Outline: Happy path transfer
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And a target account "<target>" with balance <target_balance> in currency "<target_currency>"
    And the source balance exceeds the transfer amount
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the total balance across all accounts is unchanged
    And the source balance decreased by the transfer amount
    And the target balance increased by the transfer amount
    And all account balances are non-negative

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome |
      | A1     | A2     | 100            | 50             | 30     | USD             | USD             | success |
      | B1     | B2     | 1000           | 0              | 500    | USD             | USD             | success |

  Scenario Outline: Insufficient funds
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And a target account "<target>" with balance <target_balance> in currency "<target_currency>"
    And the source balance is less than the transfer amount
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected with code INSUFFICIENT_FUNDS
    And no account balances are changed

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome                   |
      | A1     | A2     | 100            | 50             | 200    | USD             | USD             | error:INSUFFICIENT_FUNDS |
      | B1     | B2     | 0              | 1000           | 1      | USD             | USD             | error:INSUFFICIENT_FUNDS |

  Scenario Outline: Invalid amount
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And a target account "<target>" with balance <target_balance> in currency "<target_currency>"
    And the transfer amount is not positive
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome  |
      | A1     | A2     | 100            | 50             | 0      | USD             | USD             | rejected |
      | A1     | A2     | 100            | 50             | -10    | USD             | USD             | rejected |

  Scenario Outline: Non-existent account
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And the target account does not exist
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome  |
      | A1     | A3     | 100            |                | 30     | USD             | USD             | rejected |

  Scenario Outline: Currency mismatch
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And a target account "<target>" with balance <target_balance> in currency "<target_currency>"
    And the source and target currencies differ
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected with code CURRENCY_MISMATCH
    And no account balances are changed

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome                  |
      | A1     | A2     | 100            | 50             | 30     | USD             | EUR             | error:CURRENCY_MISMATCH |
      | B1     | B2     | 1000           | 0              | 100    | GBP             | USD             | error:CURRENCY_MISMATCH |

  Scenario Outline: Runtime fault
    Given a source account "<source>" with balance <source_balance> in currency "<source_currency>"
    And a target account "<target>" with balance <target_balance> in currency "<target_currency>"
    And a simulated runtime fault is injected
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer fails with a runtime error
    And no account balances are changed

    Examples:
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome               | fault            |
      | C1     | C2     | 200            | 100            | 50     | USD             | USD             | error:FAULT_INJECTED | simulated_fault  |
