# -*- coding: utf-8 -*-
"""
***************************************************************************
    p_decorators.py
    ---------------------
    Date                 : June 2026
    Copyright            : (C) 2026 Planet Inc, https://planet.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = "Kartoza"
__date__ = "June 2026"
__copyright__ = "(C) 2026 Planet Inc, https://planet.com"

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = "$Format:%H$"

from functools import wraps


def verify_mosaics_client(func):
    """Guard methods requiring an active Planet Mosaics API client connection.

    Ensures the decorated instance method has a fully initialized
    ``mosaics_client`` attribute before allowing execution.

    Args:
        func (callable): The instance method being decorated.

    Returns:
        callable: The wrapped function.

    Raises: # noqa
        TypeError: If applied to a global function or static method.
        AttributeError: If the host object lacks a ``mosaics_client`` attribute.
        RuntimeError: If ``mosaics_client`` is None, indicating the user
            has not logged in.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not args:
            raise TypeError(
                f"'{func.__name__}' decorator can only be used on class instance methods."
            )

        self_instance = args[0]

        if not hasattr(self_instance, "mosaics_client"):
            raise AttributeError(
                f"The object '{type(self_instance).__name__}' has no attribute 'mosaics_client'."
            )

        if self_instance.mosaics_client is None:
            raise RuntimeError(
                f"Mosaics client is not available. Log in before calling {func.__name__}()."
            )
        return func(*args, **kwargs)

    return wrapper


def verify_async_runner(func):  # noqa: DAR402
    """Guard methods requiring an active async runner environment.

    Ensures the decorated instance method has a fully initialized
    ``runner`` attribute before allowing execution.

    Args:
        func (callable): The instance method being decorated.

    Returns:
        callable: The wrapped function.

    Raises: # noqa
        TypeError: If applied to a global function or static method.
        AttributeError: If the host object lacks a ``runner`` attribute.
        RuntimeError: If ``runner`` is None, indicating the async runtime
            is not available.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not args:
            raise TypeError(
                f"'{func.__name__}' decorator can only be used on class instance methods."
            )

        self_instance = args[0]

        if not hasattr(self_instance, "runner"):
            raise AttributeError(
                f"The object '{type(self_instance).__name__}' has no attribute 'runner'."
            )

        if self_instance.runner is None:
            raise RuntimeError(
                "Async runtime is not available. "
                "Log in or rebuild the client before making requests."
            )

        return func(*args, **kwargs)

    return wrapper


def verify_session(func):  # noqa: DAR402
    """Guard methods requiring an active HTTP/API session.

    Ensures the decorated instance method has a fully initialized
    ``session`` attribute before allowing execution.

    Args:
        func (callable): The instance method being decorated.

    Returns:
        callable: The wrapped function.

    Raises: # noqa
        TypeError: If applied to a global function or static method.
        AttributeError: If the host object lacks a ``session`` attribute.
        RuntimeError: If ``session`` is None, indicating the network layer
            is not initialized.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not args:
            raise TypeError(
                f"'{func.__name__}' decorator can only be used on class instance methods."
            )

        self_instance = args[0]

        if not hasattr(self_instance, "session"):
            raise AttributeError(
                f"The object '{type(self_instance).__name__}' has no attribute 'session'."
            )

        if self_instance.session is None:
            raise RuntimeError(
                f"Session is not available. Log in before calling {func.__name__}()."
            )

        return func(*args, **kwargs)

    return wrapper
