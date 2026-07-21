# Prompt Configuration Guide

askUOS's wording — what the bot says, what it's allowed to answer, how tools are described to it — comes from three different places, each with a different audience. This guide explains which is which, so you edit the right one.

## 1. Internal prompts — not for you to configure

**Where:** `src/chatbot/prompt/internal_prompt_text.py`

These are implementation details of the graph's own control flow: a description field consumed only by an internal grading step's structured output, and a short internal message inserted when the graph corrects the agent's own decision. None of this text is ever shown to end users, and none of it defines the bot's behavior, tone, or scope — it only makes sense in the context of the exact Python code that reads it. That's why it's kept in Python source rather than a config file: there's nothing here a university admin needs, or should want, to customize. Changing it requires a code change and redeploy, same as any other application logic.

## 2. General application prompts — configure these for every installation

**Where:** `prompts_example/` (copy to `prompts/` to activate your changes — see `docs/INSTALLATION_GUIDE.md`)

This is the bot's actual personality and guardrails: the system prompts that define what it is, what it's allowed to talk about, how it should ask clarifying questions, and how it should use retrieved context — plus a couple of short, always-active tool descriptions. These apply to every installation regardless of which optional tools or MCP integrations are turned on, so **every university adopting askUOS should review and adjust these**, not just leave the shipped University of Osnabrück wording in place.

Layout: one `.md` file per long prompt, per language (`prompts/en/system_message.md`, `prompts/de/system_message.md`, etc.), plus a short `strings.yaml` per language for the couple of always-on tool descriptions.

Rules when editing:
- Each file may contain `{placeholder}` markers (e.g. `{current_date}`, `{user_query}`, `{context}`). These are filled in automatically at runtime — keep them, spelled exactly as they are, but feel free to move them to a different part of the text.
- Deleting a placeholder or introducing a typo in its name makes the application **fail to start**, with an error naming the exact file and the missing/wrong placeholder. This is intentional: a wording mistake gets caught immediately, not discovered later as a broken or nonsensical answer.
- Changes require restarting (rebuilding) the app to take effect — there's no live reload.

## 3. Tool / MCP / agent-specific prompts — only needed if that feature is on

**Where:** `backend_config.yaml`

Some prompts belong to one specific optional feature — a standalone tool or an MCP-connected subagent — and are meaningless outside that feature's own configuration block. These live next to the feature they describe in `backend_config.yaml`, not in `prompts/`, and you only need to fill them in if you actually enable that feature:

- **Standalone tools**, e.g. the HISinOne troubleshooting tool:
  ```yaml
  graph:
    troubleshooting:
      activate: True   # only if True is a description required
      description: |
        What this tool is for and when the agent should use it.
  ```
- **MCP subagents**, one block per agent under `mcp_agents:`:
  ```yaml
  mcp_agents:
    - agent_name: "some_agent"
      enabled: True
      description: |     # tells the main agent when to route a task to this subagent
        ...
      prompt: |           # the system prompt for the subagent itself
        ...
  ```

If a tool/agent is disabled (`activate: False` / `enabled: False`), its prompt fields are ignored and don't need to be provided at all.

## Quick reference

| Type | Location | Who edits it | When needed |
|---|---|---|---|
| Internal | `src/chatbot/prompt/internal_prompt_text.py` | Developers only | Never (not user-facing) |
| General application | `prompts/` (from `prompts_example/`) | Every installer | Always |
| Tool/MCP-specific | `backend_config.yaml` | Every installer, per feature | Only if that tool/agent is activated |
