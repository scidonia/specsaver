Feature: SQL statement translation
  As a theory developer
  I want SQL strings to be translated into the theory's statement model
  So that the stub handler can interpret them with precise operational
  semantics

  Rule: The covered fragment is SELECT, INSERT, and UPDATE — anything
  else raises UnsupportedStatementError.

  Background:
    Given the theory SQL translator

  Scenario Outline: SELECT — simple equality where
    When the SQL <query> with params (<params>) is translated
    Then the result is a Select on "<table>" with columns <columns>
    And the where clause is <where>

    Examples:
      | query                                  | params   | table    | columns                     | where                   | outcome |
      | SELECT on_hand, reserved FROM products WHERE sku = ? | ("S1",)  | products | (on_hand, reserved)         | ((sku, "S1"),)         | success |
      | SELECT * FROM products WHERE sku = ?   | ("S1",)  | products | ()                          | ((sku, "S1"),)         | success |
      | SELECT on_hand, reserved, reorder_point FROM products WHERE sku = ? AND active = 1 | ("S1",)  | products | (on_hand, reserved, reorder_point) | ((sku, "S1"),)   | success |
      | SELECT on_hand FROM orders WHERE sku = ? | ("S1",)  | orders   | (on_hand,)                  | ((sku, "S1"),)         | success |
      | SELECT on_hand FROM products WHERE sku = ? AND status = ? | ("S1", "active")  | products | (on_hand,) | ((sku, "S1"), (status, "active")) | success |

  Scenario Outline: INSERT — column/value pairs
    When the SQL <query> with params (<params>) is translated
    Then the result is an Insert on "<table>" with row <row>

    Examples:
      | query                                        | params              | table    | row                                       | outcome |
      | INSERT INTO products (sku, on_hand, reserved, reorder_point) VALUES (?, ?, ?, ?) | ("S1", 100, 10, 20) | products | ((sku, "S1"), (on_hand, 100), (reserved, 10), (reorder_point, 20)) | success |

  Scenario Outline: UPDATE — column deltas and literals
    When the SQL <query> with params (<params>) is translated
    Then the result is an Update on "<table>" with sets <sets>
    And the where clause is <where>

    Examples:
      | query                                        | params    | table    | sets                                                                  | where          | outcome |
      | UPDATE products SET reserved = reserved + ? WHERE sku = ? | (30, "S1") | products | ((reserved, SetAdd(30)),)                                             | ((sku, "S1"),) | success |
      | UPDATE products SET reserved = reserved - ? WHERE sku = ? | (5, "S1")  | products | ((reserved, SetSub(5)),)                                              | ((sku, "S1"),) | success |
      | UPDATE products SET on_hand = on_hand + ?, reorder_point = ? WHERE sku = ? | (50, 30, "S1") | products | ((on_hand, SetAdd(50)), (reorder_point, SetLit(30))) | ((sku, "S1"),) | success |
      | UPDATE products SET status = ? WHERE sku = ? | ("sold", "S1") | products | ((status, SetLit("sold")),)                                           | ((sku, "S1"),) | success |

  Scenario Outline: Rejected — unsupported statement types
    When the SQL <query> is translated
    Then the translation is rejected as unsupported

    Examples:
      | query                             | outcome                    |
      | DELETE FROM products WHERE sku = ?| error:UnsupportedStatement |
      | DROP TABLE products               | error:UnsupportedStatement |
      | CREATE TABLE products (sku TEXT)  | error:UnsupportedStatement |
      | SELECT * FROM products ORDER BY sku DESC | error:UnsupportedStatement |
      | SELECT * FROM products JOIN orders ON products.sku = orders.sku | error:UnsupportedStatement |
      | SELECT * FROM products LIMIT 10 | error:UnsupportedStatement |

  Scenario Outline: Rejected — unparseable SQL
    When the SQL <query> is translated
    Then the translation is rejected as unparseable

    Examples:
      | query             | outcome                        |
      | garbage           | error:UnsupportedStatement     |
      |                   | error:UnsupportedStatement     |
