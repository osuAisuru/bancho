from __future__ import annotations

import importlib
import inspect
from typing import Any

import app


def make_safe_name(name: str) -> str:
    return name.replace(" ", "_").lower()


def get_class_from_module(module_name: str) -> Any:
    module_name_split = module_name.split(".")

    if len(module_name_split) == 1:  # what the fuck is this code LOL
        for _, _obj in inspect.getmembers(app):
            if inspect.ismodule(_obj):
                for name, obj in inspect.getmembers(_obj):
                    if inspect.isclass(obj) and name == module_name_split[0]:
                        return obj

    module = importlib.import_module(".".join(module_name_split[:-1]))
    structure_class = getattr(module, module_name_split[-1])

    return structure_class
