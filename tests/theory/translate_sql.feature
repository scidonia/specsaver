Feature: SQL statement translation
  As a theory developer
  I want SQL strings to be translated into the theory's statement model
  So that the stub handler can interpret them with precise operational
  semantics

  Rule: The covered fragment is SELECT, INSERT, and UPDATE — anything
  else raises UnsupportedStatementError.

  Background:
    Given the theory SQL translator

  Scenario Outline: SELECT
    When <query> with params <params> is translated
    Then the result is a Select on <table> with columns <cols>

    Examples:
      | query                                                            | params     | table    | cols                        | outcome |
      | SELECT on_hand, reserved FROM products WHERE sku = ?             | ("S1",)    | products | on_hand, reserved           | success |
      | SELECT * FROM products WHERE sku = ?                             | ("S1",)    | products | *                           | success |
      | SELECT on_hand FROM orders WHERE sku = ?                         | ("S1",)    | orders   | on_hand                     | success |
      | SELECT on_hand FROM products WHERE sku = ? AND status = ?        | ("S1", "active") | products | on_hand              | success |

  Scenario Outline: INSERT
    When <query> with params <params> is translated
    Then the result is an Insert on <table>

    Examples:
      | query                                                                   | params             | table    | outcome |
      | INSERT INTO products (sku, on_hand, reserved, reorder_point) VALUES (?, ?, ?, ?) | ("S1", 100, 10, 20) | products | success |

  Scenario Outline: UPDATE
    When <query> with params <params> is translated
    Then the result is an Update on <table>

    Examples:
      | query                                                       | params        | table    | outcome |
      | UPDATE products SET reserved = reserved + ? WHERE sku = ?  | (30, "S1")    | products | success |
      | UPDATE products SET reserved = reserved - ? WHERE sku = ?  | (5, "S1")     | products | success |
      | UPDATE products SET status = ? WHERE sku = ?              | ("sold", "S1") | products | success |

  Scenario Outline: Rejected
    When <query> is translated
    Then the translation is rejected

    Examples:
      | query                                                          | outcome                      |
      | DELETE FROM products WHERE sku = ?                             | error:UnsupportedStatement   |
      | DROP TABLE products                                            | error:UnsupportedStatement   |
      | CREATE TABLE products (sku TEXT)                               | error:UnsupportedStatement   |
      | SELECT * FROM products ORDER BY sku DESC                       | error:UnsupportedStatement   |
      | SELECT * FROM products JOIN orders ON products.sku = orders.sku | error:UnsupportedStatement  |
      | SELECT * FROM products LIMIT 10                                | error:UnsupportedStatement   |
      | garbage                                                        | error:UnsupportedStatement   |
