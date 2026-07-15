# specsaver

Specification-driven verification.  Write contracts (preconditions, postconditions, invariants, frame conditions, effects) as Python functions decorated with `@precondition`, `@postcondition`, etc., organised by entry point.  The contract language is the single source of semantic truth from which all testing and verification artefacts are derived.

## Installation

```bash
pip install specsaver
```

## Quick start

```python
from specsaver import precondition, postcondition, invariant, Args, Result

@precondition(entry_point="transfer")
def transfer_pre_valid_amount(state, args):
    return args.amount > 0

@postcondition(entry_point="transfer")
def transfer_post_total_preserved(old_state, args, result, new_state):
    return old(sum_balances(old_state)) == sum_balances(new_state)
```

Run the CLI to see contracts linked to their Gherkin origins:

```bash
specsaver trace examples.bank_transfer
specsaver trace examples.bank_transfer --verify   # run the tests too
```

## Development

```bash
git clone https://github.com/scidonia/specsaver.git
cd specsaver
uv sync
uv run pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
