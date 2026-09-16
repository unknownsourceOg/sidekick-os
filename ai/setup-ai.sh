#!/bin/sh
# Setup is graphical; the ISO already includes the local inference engine.
if [ -x /opt/sidekick/sidekick-mascot ]; then
    exec /opt/sidekick/sidekick-mascot --setup
fi
printf '%s\n' 'Install the updated Sidekick desktop first, then open AI Setup.' >&2
exit 1
