Feature: Parallel Obligation Emission
  As a rocq-piler integration
  I want obligation files split by dependency layer
  So that each layer can be proven independently and in parallel.

  Rule: Every generated lemma is assigned to a dependency layer based
        on which other lemmas it references.  Layers are topological:
        a lemma only references lemmas from lower-numbered layers
        (or external definitions).

  Rule: One `.v` file is emitted per layer.  Each file imports the
        shared language definitions (the Coq prelude).  A
        `_CoqProject` lists all layer files in dependency order for
        sequential fallback compilation.

  Rule: A `schedule.json` records the layer DAG — which files can
        be proven together and which depend on previous phases.

  Scenario Outline: Layer splitting for a contract
    Given a contract for <operation>
    When the obligation generator introspects it
    Then the obligations are partitioned into layers
    And each layer is emitted as a separate ".v" file
    And a "_CoqProject" is emitted listing files in dependency order
    And a "schedule.json" is emitted with the parallel execution DAG

    Examples:
      | operation | obligations | layers | phase-1-count | phase-2-count |
      | reserve   | 6          | 4      | 2             | 2             |
      | release   | 6          | 4      | 2             | 2             |
      | restock   | 4          | 3      | 2             | 1             |
      | transfer  | 7          | 4      | 3             | 2             |

  Scenario: Output directory structure
    Given a contract for "release"
    When obligations are emitted into "coqgen/release/"
    Then the following files exist:
      | coqgen/release/release_L0.v |
      | coqgen/release/release_L1.v |
      | coqgen/release/release_L2.v |
      | coqgen/release/release_L3.v |
      | coqgen/release/release_L4.v |
      | coqgen/release/_CoqProject  |
      | coqgen/release/schedule.json |
