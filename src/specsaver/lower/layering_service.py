"""Service wrapper for layered emission — bridges emit_layered to the
contract runner by accepting (context, args) and returning a receipt."""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

from specsaver.lower.emit import emit_layered
from specsaver.lower.introspect import introspect_contract
from specsaver.lower.layering_types import EmitArgs, EmitReceipt


class EmitLayeringService:
    """Wraps emit_layered as a domain service."""

    def execute(self, context, args: EmitArgs) -> EmitReceipt:
        contract_ = getattr(
            importlib.import_module(args.module), args.contract,
        )
        row_type = getattr(
            importlib.import_module(args.types_module), args.row_type,
        )
        info = introspect_contract(
            contract_, row_type, args.map_field, args.key_arg,
        )

        out_dir = str(Path(tempfile.mkdtemp()) / info.name)
        emit_layered(info, f"{args.module}:{args.contract}", out_dir)

        # Count layers
        layer_files = sorted(
            f for f in os.listdir(out_dir)
            if f.endswith(".v") and "_L" in f
        )
        num_layers = len(layer_files)
        all_files = os.listdir(out_dir)

        return EmitReceipt(
            out_dir=out_dir,
            num_layers=num_layers,
            num_files=len(all_files),
        )
