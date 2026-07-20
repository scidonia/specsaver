Feature: Stock restock
  As a warehouse operator
  I want to receive stock shipments into inventory
  So that on-hand stock reflects what physically arrived

  Rule: Reserved stock never exceeds physical stock at all times

  Scenario Outline: Happy path restock
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    When stock of <quantity> is received on "<sku>"
    Then the on-hand quantity increased by the received quantity
    And the reserved quantity is unchanged
    And a StockReceived event is emitted
    And a stock level gauge matching the new state is emitted

    Examples:
      | sku | on_hand | reserved | quantity | reorder_point | outcome |
      | S1  | 10      | 5        | 40       | 20            | success |
      | S2  | 0       | 0        | 100      | 10            | success |

  Scenario Outline: Invalid quantity
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the received quantity is not positive
    When stock of <quantity> is received on "<sku>"
    Then the restock is rejected

    Examples:
      | sku | on_hand | reserved | quantity | reorder_point | outcome  |
      | S3  | 100     | 10       | 0        | 20            | rejected |
      | S4  | 100     | 10       | -5       | 20            | rejected |

  Scenario Outline: Non-existent product
    Given no product "<sku>" exists
    When stock of <quantity> is received on "<sku>"
    Then the restock is rejected

    Examples:
      | sku | on_hand | reserved | quantity | reorder_point | outcome  |
      | S5  |         |          | 5        |               | rejected |
