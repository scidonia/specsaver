Feature: Stock reservation
  As an order fulfilment system
  I want to reserve inventory stock for orders
  So that available stock is never oversold

  Rule: Reserved stock never exceeds physical stock at all times

  Scenario Outline: Happy path reservation
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the available stock covers the reservation quantity
    When stock of <quantity> is reserved for order "<order>" on "<sku>"
    Then the on-hand quantity is unchanged
    And the reserved quantity increased by the reservation quantity
    And a StockReserved event is emitted
    And a stock level gauge matching the new state is emitted

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome |
      | S1  | O1    | 100     | 10       | 30       | 20            | success |
      | S2  | O2    | 50      | 0        | 50       | 10            | success |
      | S3  | O3    | 15      | 0        | 5        | 20            | success |

  Scenario Outline: Insufficient stock
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the available stock is less than the reservation quantity
    When stock of <quantity> is reserved for order "<order>" on "<sku>"
    Then the reservation is rejected with code INSUFFICIENT_STOCK
    And no stock levels are changed
    And a ReservationFailed event is emitted

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome                        |
      | S4  | O4    | 10      | 5        | 6        | 2             | error:InsufficientStockError   |
      | S5  | O5    | 0       | 0        | 1        | 0             | error:InsufficientStockError   |

  Scenario Outline: Invalid quantity
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the reservation quantity is not positive
    When stock of <quantity> is reserved for order "<order>" on "<sku>"
    Then the reservation is rejected

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome  |
      | S6  | O6    | 100     | 10       | 0        | 20            | rejected |
      | S7  | O7    | 100     | 10       | -5       | 20            | rejected |

  Scenario Outline: Non-existent product
    Given no product "<sku>" exists
    When stock of <quantity> is reserved for order "<order>" on "<sku>"
    Then the reservation is rejected

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome  |
      | S9  | O9    |         |          | 5        |               | rejected |

  Scenario Outline: Runtime fault
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And a simulated runtime fault is injected
    When stock of <quantity> is reserved for order "<order>" on "<sku>"
    Then the reservation fails with a runtime error
    And no stock levels are changed

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome                    | fault           |
      | S8  | O8    | 200     | 100      | 50       | 25            | error:SimulatedFaultError  | simulated_fault |
