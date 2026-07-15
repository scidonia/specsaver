Feature: Funds transfer
  As a bank customer
  I want to transfer funds between accounts
  So that I can move money

  Rule: Successful transfers preserve total funds

  Scenario Outline: Transfer between two accounts
    Given an account "<source>" with balance <source_balance> in currency "<currency>"
    And an account "<target>" with balance <target_balance> in currency "<currency>"
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the total balance across all accounts is unchanged
    And the "<source>" balance decreased by <amount>
    And the "<target>" balance increased by <amount>
    And all account balances are non-negative

    Examples: Happy paths
      | source | target | source_balance | target_balance | amount | currency |
      | A1     | A2     | 100            | 50             | 30     | USD      |
      | B1     | B2     | 1000           | 0              | 500    | USD      |
      | SRC    | DST    | 1              | 1              | 1      | EUR      |

  Scenario Outline: Transfer is rejected when preconditions fail
    Given an account "<source>" with balance <source_balance> in currency "<currency>"
    And an account "<target>" with balance <target_balance> in currency "<currency>"
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected
    And no account balances are changed

    Examples: Insufficient funds
      | source | target | source_balance | target_balance | amount | currency |
      | A1     | A2     | 100            | 50             | 200    | USD      |
      | B1     | B2     | 0              | 1000           | 1      | USD      |

    Examples: Zero or negative amount
      | source | target | source_balance | target_balance | amount | currency |
      | A1     | A2     | 100            | 50             | 0      | USD      |
      | A1     | A2     | 100            | 50             | -10    | USD      |

  Scenario Outline: Transfer to non-existent account is rejected
    Given an account "<source>" with balance <source_balance> in currency "<currency>"
    And an account "<target>" does not exist
    When funds of <amount> are transferred from "<source>" to "<target>"
    Then the transfer is rejected

    Examples: Non-existent account
      | source | target | source_balance | amount | currency |
      | A1     | A3     | 100            | 30     | USD      |
