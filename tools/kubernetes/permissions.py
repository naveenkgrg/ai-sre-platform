READ_OPERATIONS = {"get", "describe", "logs"}
WRITE_OPERATIONS = {"delete", "apply", "scale"}


def validate_operation(operation, resource):
    if operation in WRITE_OPERATIONS:
        raise PermissionError(
            f"Human approval required for: {operation}"
        )

    if operation not in READ_OPERATIONS:
        raise PermissionError(
            f"Operation not allowed: {operation}"
        )

    return True