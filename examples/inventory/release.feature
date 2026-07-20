Feature: Reservation release
  As an order fulfilment system
  I want to release reserved stock when orders are cancelled
  So that available stock is returned for other orders

  Rule: Reserved stock never exceeds physical stock at all times

  Scenario Outline: Happy path release
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the reserved stock covers the release quantity
    When stock of <quantity> is released for order "<order>" on "<sku>"
    Then the on-hand quantity is unchanged
    And the reserved quantity decreased by the release quantity
    And a ReservationReleased event is emitted
    And a stock level gauge matching the new state is emitted

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome |
      | S1  | O1    | 100     | 30       | 30       | 20            | success |
      | S2  | O2    | 50      | 10       | 5        | 20            | success |

  Scenario Outline: Release exceeds reserved
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the release quantity exceeds the reserved stock
    When stock of <quantity> is released for order "<order>" on "<sku>"
    Then the release is rejected with code RELEASE_EXCEEDS_RESERVED
    And no stock levels are changed
    And a ReleaseFailed event is emitted

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome                          |
      | S3  | O3    | 10      | 5        | 6        | 2             | error:ReleaseExceedsReservedError |
      | S4  | O4    | 0       | 0        | 1        | 0             | error:ReleaseExceedsReservedError |

  Scenario Outline: Invalid quantity
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And the release quantity is not positive
    When stock of <quantity> is released for order "<order>" on "<sku>"
    Then the release is rejected

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome  |
      | S5  | O5    | 100     | 10       | 0        | 20            | rejected |
      | S6  | O6    | 100     | 10       | -5       | 20            | rejected |

  Scenario Outline: Non-existent product
    Given no product "<sku>" exists
    When stock of <quantity> is released for order "<order>" on "<sku>"
    Then the release is rejected

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome  |
      | S7  | O7    |         |          | 5        |               | rejected |

  Scenario Outline: Runtime fault
    Given a product "<sku>" with on-hand <on_hand> reserved <reserved> and reorder point <reorder_point>
    And a simulated runtime fault is injected
    When stock of <quantity> is released for order "<order>" on "<sku>"
    Then the release fails with a runtime error
    And no stock levels are changed

    Examples:
      | sku | order | on_hand | reserved | quantity | reorder_point | outcome                    | fault           |
      | S8  | O8    | 200     | 100      | 50       | 25            | error:SimulatedFaultError  | simulated_fault |
