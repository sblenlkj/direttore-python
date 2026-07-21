# Auth Module

This document describes the `core/modules/auth` module.

The module provides small contracts for authentication and authorization. It does not define application users, roles, permissions, access tags, tokens, or exceptions. Those remain application-level concerns.

```text
core/modules/auth/
  __init__.py
  authenticator.py
  authorizer.py
  authorizer_modular.py
```

## Core Idea

The auth module separates two different concerns:

```text
authentication
  auth input -> auth object

authorization
  auth object + handler policy -> allow or deny
```

Authentication answers:

```text
Who or what is calling?
```

Authorization answers:

```text
Is this caller allowed to execute this handler?
```

The framework does not define the shape of `auth_input` or `auth`.

## `authenticator.py`

`authenticator.py` defines the authentication contract.

Conceptually:

```text
AuthInputT -> Authenticator -> AuthT
```

The input may be anything provided by an adapter or runtime:

```text
HTTP headers
JWT token
API key
Telegram user payload
service token
test fixture object
already resolved request principal
```

The output is the application-specific auth object.

Examples:

```text
AppUserAuth
ServiceAuth
TelegramAuth
AnonymousAuth
TestAuth
```

The framework does not inspect this object. It is passed to handlers through handler context and to the authorizer for access decisions.

Typical contract shape:

```python
class Authenticator[AuthInputT, AuthT](ABC):
    async def authenticate(self, auth_input: AuthInputT) -> AuthT:
        ...
```

Implementations should return a resolved auth object or raise an application-specific authentication exception.

## `authorizer.py`

`authorizer.py` defines the simple-service authorization contract.

Conceptually:

```text
allowed_access_tags + auth -> allow / deny
```

The engine calls the authorizer before executing a handler.

Typical contract shape:

```python
class Authorizer[AuthT](ABC):
    def authorize(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
    ) -> None:
        ...
```

The method should return normally when access is allowed and raise an application-specific exception when access is denied.

## Access Tags

Access tags are plain strings.

The framework does not provide built-in tags such as:

```text
admin
user
system
public
authenticated
```

The application owns tag vocabulary and semantics.

Examples:

```python
frozenset({"admin"})
frozenset({"users.write"})
frozenset({"billing.read"})
frozenset({"internal.service"})
```

The application decides what every case means:

```text
allowed_access_tags is None
allowed_access_tags is empty
auth is None
auth has missing roles/permissions
system/service auth is used
public access is allowed
```

This keeps the framework neutral and prevents hidden authorization behavior.

## `authorizer_modular.py`

`authorizer_modular.py` defines the modular-monolith authorization contract.

The modular authorizer exists because modular execution has one additional authorization signal: whether execution came from an external user-facing boundary or from trusted in-process system code.

```text
USER_REQUEST
  execution entered through an external adapter

SYSTEM_INVOKE
  execution was initiated by trusted in-process runtime code
```

Typical examples of `USER_REQUEST`:

```text
HTTP endpoint
Telegram command
CLI command
user-facing adapter
```

Typical examples of `SYSTEM_INVOKE`:

```text
cross-context invoke inside a modular monolith
trusted in-process call from one module to another
internal invoke performed by framework runtime
```

This signal is intentionally not part of the simple-service authorizer. In simple service mode, there is normally no modular in-process cross-context boundary.

Typical contract shape:

```python
class ModularAuthorizer[AuthT](ABC):
    def authorize(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
        location_kind: ModularAuthorizationLocationKind,
    ) -> None:
        ...
```

The application decides how to interpret `SYSTEM_INVOKE`.

Possible policies:

```text
allow all trusted system invokes
require service auth
require special access tags
deny by default
apply the same rules as user requests
```

The framework does not decide this.

## Why There Is No Authorization Context

The module does not use a generic `AuthorizationContext`.

The application-specific auth object already carries request/user/service information. If an application needs tenant, user id, service id, scopes, roles, or request metadata, it can put those fields inside its own `AuthT`.

The only additional framework signal currently needed is modular execution location. That is why the modular authorizer receives `location_kind` directly instead of a generic context object.

## Simple Service Flow

A simple service engine typically does:

```text
auth_input -> authenticator.authenticate(...) -> auth
authorizer.authorize(allowed_access_tags, auth)
handler context receives auth
handler executes
```

Conceptual code:

```python
auth = None

if authenticator is not None:
    auth = await authenticator.authenticate(auth_input)

if authorizer is not None:
    authorizer.authorize(
        allowed_access_tags=handler_config.allowed_access_tags,
        auth=auth,
    )

context = UseCaseHandlerContext(
    uow=uow,
    queue=queue,
    auth=auth,
    tracer=trace,
)
```

## Modular Monolith Flow

A modular monolith engine or runtime may use the modular authorizer:

```python
auth = await authenticator.authenticate(auth_input)

authorizer.authorize(
    allowed_access_tags=handler_config.allowed_access_tags,
    auth=auth,
    location_kind=ModularAuthorizationLocationKind.SYSTEM_INVOKE,
)
```

For user-facing entrypoints, it can use:

```python
location_kind=ModularAuthorizationLocationKind.USER_REQUEST
```

## Design Boundaries

The auth module should not contain:

```text
application users
roles enum
permissions enum
access tag enum
JWT implementation
HTTP header parsing
framework-owned public/system tags
default access checker with hidden policy
project-specific exceptions
```

Those belong to the application.

## Summary

The auth module provides three contracts:

```text
Authenticator
  converts request-specific input into application auth object

Authorizer
  authorizes simple service handler execution

ModularAuthorizer
  authorizes modular monolith execution with location kind
```

The framework stays neutral. The application owns authentication input, auth object shape, access tag vocabulary, and denial policy.
