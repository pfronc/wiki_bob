# Bob tools

Short instructions to use the `tools` helper scripts.

1. Make wrapper executable:

```bash
chmod +x tools/bob
```

2. Add `tools/` to your PATH for the current shell session:

```bash
export PATH="$PWD/tools:$PATH"
```

You can add that line to your shell rc (e.g., `~/.zshrc`) to persist it.

3. Examples:

```bash
# run ingest
bob ingest --source example.md

# run query
bob query --question "What is transformer architecture?"

# research (agent-driven — prints procedure path, no scaffolding)
bob research
```

4. Runner map:

See `.bob/runner_map.yaml` for a simple mapping from logical modes to CLI templates.
