# Defensive coding and boundaries

Check what comes from outside: external input, file reads and writes, network calls, API
responses. Null and undefined, missing directories, malformed JSON. Handle the failure
where it happens rather than letting it surface three layers up as something unrecognisable.

Stay inside the current project. Reading or writing outside it — system config, another
project, anything in the home directory — needs to be asked for first. That is where SSH
keys, credentials, and browser data live.

API keys, tokens, and private keys never appear in code, in a command line, or in the
conversation. All three persist somewhere you didn't choose. Read them from the environment
or a secrets file that is already ignored by git.
