"""
ThemisLoop — the conversational tool-call loop for the chat interface.

WHY a separate class from LangGraph's StateGraph:
  - StateGraph = the matter pipeline (intake → research → draft → cite → review).
    Called once per matter. Has checkpointing. Not involved in chat conversation routing.
  - ThemisLoop = the conversational shell in chat.py. Handles "which tool should I
    call now?" decisions in real-time chat. Lives outside the StateGraph.

This is the same pattern Hermes uses: the agent loop (while True) is separate from
the internal tools that do the heavy lifting when called.

Key improvements over the old _stream_turn():
  1. IterationBudget replaces the fragile "depth > 6" recursion guard
  2. Multiple tool calls from a single LLM response fire in parallel via asyncio.gather()
  3. The loop is a class — easy to test and extend for R3 (LLM Council)
"""

import asyncio
import json
import sys
from typing import Callable, Optional

import litellm
from rich.console import Console

from themis.agent.budget import IterationBudget
from themis.config import LexConfig

console = Console()

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


async def _spin_until(stop: asyncio.Event) -> None:
    i = 0
    sys.stdout.write(_SPINNER_FRAMES[0])
    sys.stdout.flush()
    while not stop.is_set():
        await asyncio.sleep(0.08)
        i += 1
        sys.stdout.write(f"\b{_SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]}")
        sys.stdout.flush()
    sys.stdout.write("\b \b")
    sys.stdout.flush()


class ThemisLoop:
    """
    Run one user turn through the LLM + tool-execution cycle.

    Usage:
        loop = ThemisLoop(
            model=chat_model,
            tools=_TOOLS,
            execute_tool=_execute_tool,
            cfg=cfg,
            system=system_prompt,
        )
        new_messages = await loop.run(messages)
    """

    def __init__(
        self,
        model: str,
        tools: list[dict],
        execute_tool: Callable,
        cfg: LexConfig,
        system: str = "",
        budget: Optional[IterationBudget] = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._execute_tool = execute_tool
        self._cfg = cfg
        self._system = system
        self._budget = budget or IterationBudget()

    async def run(self, messages: list[dict]) -> list[dict]:
        """
        Run the full turn: LLM call → tool execution (parallel) → follow-up LLM call.
        Returns the list of NEW messages to append to conversation history.
        """
        accumulated_new: list[dict] = []
        current_messages = messages

        while not self._budget.exhausted:
            new_from_turn = await self._one_llm_turn(current_messages + accumulated_new)
            if not new_from_turn:
                break

            accumulated_new.extend(new_from_turn)

            # Check if there were tool calls — if not, we're done
            last_assistant = next(
                (m for m in reversed(new_from_turn) if m.get("role") == "assistant"),
                None,
            )
            if not last_assistant or not last_assistant.get("tool_calls"):
                break

            self._budget.tick()

        if self._budget.exhausted and self._budget.reason:
            console.print(f"\n[dim yellow]Loop stopped: {self._budget.reason}[/dim yellow]")

        return accumulated_new

    async def _one_llm_turn(self, messages: list[dict]) -> list[dict]:
        """
        Fire one LLM call, stream the response, execute any tool calls in parallel.
        Returns new messages from this turn (assistant msg + tool results).
        """
        console.print()
        console.print("[bold green]Themis[/bold green]  ", end="")
        sys.stdout.flush()

        text_buffer = ""
        tool_calls_acc: dict[int, dict] = {}
        finish_reason = None
        first_content = True

        spinner_stop = asyncio.Event()
        spinner_task = asyncio.create_task(_spin_until(spinner_stop))

        try:
            stream = await litellm.acompletion(
                model=self._model,
                messages=[{"role": "system", "content": self._system}] + messages
                if self._system
                else messages,
                tools=self._tools or None,
                stream=True,
                request_timeout=120,
            )

            async for chunk in stream:
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                has_content = bool(delta.content)
                has_tool = bool(delta.tool_calls)

                if first_content and (has_content or has_tool):
                    spinner_stop.set()
                    await spinner_task
                    first_content = False

                if has_content:
                    console.print(delta.content, end="", highlight=False)
                    text_buffer += delta.content

                if has_tool:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        finally:
            if not spinner_stop.is_set():
                spinner_stop.set()
                await spinner_task

        console.print()

        new_messages: list[dict] = []

        # Build the assistant message (with optional tool_calls field)
        tool_calls_list = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in (tool_calls_acc[i] for i in sorted(tool_calls_acc))
        ]

        assistant_msg: dict = {"role": "assistant", "content": text_buffer or None}
        if tool_calls_list:
            assistant_msg["tool_calls"] = tool_calls_list
        new_messages.append(assistant_msg)

        # Execute tool calls — IN PARALLEL if multiple tools were requested
        # WHY parallel: if the LLM asks for "draft a notice AND search limitation",
        # both fire simultaneously instead of waiting for one before starting the other.
        if finish_reason == "tool_calls" and tool_calls_list:
            async def _run_one_tool(tc: dict) -> dict:
                name = tc["function"]["name"]
                try:
                    inputs = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    inputs = {}
                console.print(f"\n[dim cyan]→ {name}[/dim cyan]")
                result = await self._execute_tool(
                    name, inputs, self._cfg, messages=messages + new_messages
                )
                return {"role": "tool", "tool_call_id": tc["id"], "content": result}

            # WHY gather: multiple tool calls from one LLM response can run concurrently.
            tool_results = await asyncio.gather(*[_run_one_tool(tc) for tc in tool_calls_list])
            new_messages.extend(tool_results)

        return new_messages
