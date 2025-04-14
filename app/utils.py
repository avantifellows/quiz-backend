from pydantic import BaseModel


def remove_optional_unset_args(model: BaseModel):
    """Removes fields marked as Optional that haven't been set while creating the model

    For example, if you have a model with multiple optional fields without any default
    value, you probably intended that it was okay if that field is not passed while creating
    the model. However, even if you don't pass any value for the field, pydantic will, by
    default, still keep that field in the model instance and set its value to null.

    Refer to this for more details: https://stackoverflow.com/questions/65362524/in-json-created-from-a-pydantic-basemodel-exclude-optional-if-not-set

    :param model: the model which needs to be updated
    :type model: BaseModel

    """

    def union(source, destination):
        for key, value in source.items():
            if isinstance(value, dict):
                node = destination.setdefault(key, {})
                union(value, node)
            else:
                destination[key] = value

        return destination

    return union(model.dict(exclude_unset=True), model.dict(exclude_none=True))
