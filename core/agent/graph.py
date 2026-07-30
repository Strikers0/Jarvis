from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.llm import LLMMessage

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    messages: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    current_node: str = "analyze_intent"
    context: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    done: bool = False


class ToolExecutionNode:
    def __init__(self, dispatcher: Any):
        self.dispatcher = dispatcher

    async def __call__(self, state: AgentState) -> AgentState:
        tool_calls = []
        for msg in state.messages:
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
        if not tool_calls:
            return state
        results = []
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            result = await self.dispatcher.dispatch(tool_name, args)
            results.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result.to_text(),
            })
            logger.info("Tool %s executed: success=%s", tool_name, result.success)
        state.tool_results = results
        for r in results:
            state.messages.append(r)
        return state


class AgentGraph:
    def __init__(self, llm: Any, dispatcher: Any):
        self.llm = llm
        self.dispatcher = dispatcher
        self._nodes: dict[str, Any] = {
            "analyze_intent": self._analyze_intent,
            "select_tools": self._select_tools,
            "execute_tools": ToolExecutionNode(dispatcher),
            "synthesize_response": self._synthesize_response,
        }
        self._edges: dict[str, list[str]] = {
            "analyze_intent": ["select_tools"],
            "select_tools": ["execute_tools", "synthesize_response"],
            "execute_tools": ["synthesize_response"],
            "synthesize_response": [],
        }

    async def run(
        self,
        user_input: str,
        system_prompt: str,
        tools: list[dict],
        max_iterations: int = 5,
    ) -> AgentState:
        state = AgentState(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            context={"tools": tools, "iteration": 0},
        )

        for iteration in range(max_iterations):
            state.context["iteration"] = iteration
            node_name = state.current_node

            if node_name == "synthesize_response":
                state = await self._nodes[node_name](state)
                break

            state = await self._nodes[node_name](state)

            if state.error:
                logger.error("Agent error at node %s: %s", node_name, state.error)
                break

            next_nodes = self._edges.get(node_name, [])
            if node_name == "select_tools":
                has_tool_calls = any(
                    msg.get("tool_calls") for msg in state.messages
                )
                state.current_node = "execute_tools" if has_tool_calls else "synthesize_response"
            elif next_nodes:
                state.current_node = next_nodes[0]

        state.done = True
        return state

    async def _analyze_intent(self, state: AgentState) -> AgentState:
        try:
            messages = [LLMMessage(role=m["role"], content=m.get("content", "")) for m in state.messages]
            response = await self.llm.chat(
                messages,
                system_prompt=state.messages[0]["content"] if state.messages else "",
                tools=state.context.get("tools"),
            )
            msg = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                msg["tool_calls"] = response.tool_calls
            state.messages.append(msg)
            if not response.tool_calls:
                state.current_node = "synthesize_response"
        except Exception as e:
            state.error = str(e)
        return state

    async def _select_tools(self, state: AgentState) -> AgentState:
        return state

    async def _synthesize_response(self, state: AgentState) -> AgentState:
        if state.tool_results:
            import json
            tool_context = "\n".join(
                f"Tool result ({r.get('tool_call_id', '')[:8]}): {r.get('content', '')[:500]}"
                for r in state.tool_results
            )
            synthesis_prompt = {
                "role": "user",
                "content": f"Based on the tool execution results below, provide a clear response to the user.\n\nTool Results:\n{tool_context}",
            }
            state.messages.append(synthesis_prompt)
            try:
                messages = [LLMMessage(role=m["role"], content=m.get("content", "")) for m in state.messages]
                response = await self.llm.chat(
                    messages,
                    system_prompt=state.messages[0]["content"] if state.messages else "",
                )
                state.messages.append({"role": "assistant", "content": response.content or ""})
            except Exception as e:
                state.error = str(e)
        return state


