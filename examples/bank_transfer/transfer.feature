Feature: Funds transfer
  As a bank customer
  I want to transfer funds between accounts
  So that I can move money

  Rule: All account balances are non-negative at all times

  Rule: Successful transfers preserve total funds

  Rule: Cross-currency transfers are rejected

  Rule: Transfer limits are enforced
    The system enforces a per-transfer maximum amount.
    The system enforces daily and monthly aggregate transfer limits, derived
    from ghost state tracking remaining allowances.

  Scenario Outline: Transfer funds
    Given an account "<source>" with balance <source_balance> in currency "<source_currency>"
    And an account "<target>" with balance <target_balance> in currency "<target_currency>"
    And the source balance exceeds the transfer amount
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the total balance across all accounts is unchanged
    And the source balance decreased by the transfer amount
    And the target balance increased by the transfer amount
    And all account balances are non-negative
    And no account balances are changed when the transfer fails

    Examples: Happy paths
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome |
      | A1     | A2     | 100            | 50             | 30     | USD             | USD             | success |
      | B1     | B2     | 1000           | 0              | 500    | USD             | USD             | success |

    Examples: Insufficient funds
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome                   |
      | A1     | A2     | 100            | 50             | 200    | USD             | USD             | error:INSUFFICIENT_FUNDS |
      | B1     | B2     | 0              | 1000           | 1      | USD             | USD             | error:INSUFFICIENT_FUNDS |

    Examples: Zero or negative amount
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome  |
      | A1     | A2     | 100            | 50             | 0      | USD             | USD             | rejected |
      | A1     | A2     | 100            | 50             | -10    | USD             | USD             | rejected |

    Examples: Non-existent account
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome  |
      | A1     | A3     | 100            |                | 30     | USD             | USD             | rejected |

    Examples: Currency mismatch
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome                  |
      | A1     | A2     | 100            | 50             | 30     | USD             | EUR             | error:CURRENCY_MISMATCH |
      | B1     | B2     | 1000           | 0              | 100    | GBP             | USD             | error:CURRENCY_MISMATCH |

    Examples: Runtime fault
      | source | target | source_balance | target_balance | amount | source_currency | target_currency | outcome               | fault            |
      | C1     | C2     | 200            | 100            | 50     | USD             | USD             | error:FAULT_INJECTED | simulated_fault  |
