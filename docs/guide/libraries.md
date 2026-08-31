# Libraries

A library is the unit of privacy in Primer. It has one owner, and only that
owner can see it.

## What "private" means here

Someone else's library is not merely unreadable — it is undetectable. Asking
Primer for a library you do not own returns the same "not found" as asking
for one that never existed. That is deliberate: an error that distinguished
"forbidden" from "missing" would let anyone confirm that a particular
library exists, which is itself a disclosure.

The same applies to documents inside a library, and to their contents in
search results.

## Creating and renaming

A library needs a name, which can be up to 120 characters, and can be
renamed at any time. Renaming does not affect its documents.

If two people edit the same library, the second change can be rejected
rather than silently overwriting the first. Reload and reapply the change.

## Deleting

Deleting a library takes it and its documents out of reach immediately. The
underlying passages and files are removed afterwards, in the background.

The order matters: the tombstone is written first, so there is no window in
which a deleted library still answers questions. What follows is cleanup,
not part of the deletion the user asked for.

!!! note "Sharing is not built yet"
    Every library today belongs to exactly one person. The authorization
    layer was written so that adding shared libraries later is a change in
    one place rather than in every route, but that feature does not exist.
