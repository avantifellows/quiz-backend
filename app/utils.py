from pydantic import BaseModel


def union(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            union(value, node)
        else:
            destination[key] = value

    return destination


def remove_optional_unset_args(model: BaseModel):
    return union(model.dict(exclude_unset=True), model.dict(exclude_none=True))
