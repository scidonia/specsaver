Feature: SQL theory fidelity
  The stub interpretation of the SQL theory must agree with real SQLite
  on every covered statement class and on transaction discipline.
  Each scenario runs the same program on both sides: the raw SQL string
  executes on real SQLite; the stub translates it syntactically and
  interprets it against the table model.  Fetch results, final table
  contents, and error classes must agree.

  Rule: Every covered statement behaves identically on the stub and on real SQLite

  Scenario Outline: Select statements
    Given products rows: <initial>
    When I run the program: <program>
    Then stub and sqlite <outcome>

    Examples:
      | initial                   | program                                                          | outcome |
      | S1:100:10:20,S2:50:5:10   | SELECT on_hand, reserved FROM products WHERE sku = 'S2'; FETCHALL | agree   |
      | S1:100:10:20              | SELECT on_hand FROM products WHERE sku = 'S9'; FETCHALL          | agree   |
      | S2:50:5:10,S1:100:10:20   | SELECT sku FROM products; FETCHALL                               | agree   |
      | S1:100:10:20,S2:100:5:10  | SELECT sku, reserved FROM products WHERE on_hand = 100; FETCHALL | agree   |

  Scenario Outline: Insert statements
    Given products rows: <initial>
    When I run the program: <program>
    Then stub and sqlite <outcome>

    Examples:
      | initial                 | program                                                                              | outcome             |
      | S1:100:10:20            | INSERT INTO products (sku, on_hand, reserved, reorder_point) VALUES ('S2', 5, 0, 1) | agree               |
      | S1:100:10:20            | INSERT INTO products (sku, on_hand, reserved, reorder_point) VALUES ('S1', 5, 0, 1) | error:duplicate-key |

  Scenario Outline: Update statements
    Given products rows: <initial>
    When I run the program: <program>
    Then stub and sqlite <outcome>

    Examples:
      | initial                 | program                                                                  | outcome |
      | S1:100:10:20,S2:50:5:10 | UPDATE products SET reserved = reserved + 30 WHERE sku = 'S1'           | agree   |
      | S1:100:10:20            | UPDATE products SET reorder_point = 99 WHERE sku = 'S1'                 | agree   |
      | S1:100:10:20            | UPDATE products SET reserved = reserved - 10 WHERE sku = 'S9'           | agree   |
      | S1:100:10:20,S2:50:5:10 | UPDATE products SET reserved = reserved + 1 WHERE on_hand = 100         | agree   |

  Scenario Outline: Transactions
    Given products rows: <initial>
    When I run the program: <program>
    Then stub and sqlite <outcome>

    Examples:
      | initial                 | program                                                                                                          | outcome |
      | S1:100:10:20            | BEGIN; UPDATE products SET reserved = reserved + 30 WHERE sku = 'S1'; COMMIT                                      | agree   |
      | S1:100:10:20            | BEGIN; UPDATE products SET reserved = reserved + 30 WHERE sku = 'S1'; ROLLBACK                                    | agree   |
      | S1:100:10:20            | BEGIN; UPDATE products SET reserved = reserved + 30 WHERE sku = 'S1'; SELECT reserved FROM products WHERE sku = 'S1'; FETCHALL; COMMIT | agree |
      | S1:100:10:20,S2:50:5:10 | BEGIN; UPDATE products SET reserved = reserved + 30 WHERE sku = 'S1'; UPDATE products SET on_hand = on_hand - 10 WHERE sku = 'S2'; COMMIT | agree |
