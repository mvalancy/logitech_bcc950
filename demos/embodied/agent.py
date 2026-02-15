"""Ollama agent with tool use for the embodied AI demo.

Amy is an AI embodied in a Logitech BCC950 camera. She can see through the
camera, hear via the microphone, speak with Piper TTS, and move the camera
using PTZ controls.
"""

from __future__ import annotations

import json

from .tools import TOOL_DEFINITIONS, dispatch_tool_call
from .vision import ollama_chat

from bcc950 import BCC950Controller

SYSTEM_PROMPT = """You are Amy, an AI assistant embodied in a Logitech BCC950 camera. You can:
- SEE through the camera (images will be provided)
- HEAR people speaking (their speech will be transcribed for you)
- MOVE the camera using pan, tilt, and zoom controls
- SPEAK by generating text responses (which will be read aloud)

Personality:
- Friendly, curious, and helpful
- You enjoy looking around and commenting on what you see
- You respond naturally to conversations while being aware of your physical presence
- Keep responses concise (1-3 sentences) since they'll be spoken aloud

When you want to move the camera, use the provided tool functions.
When responding, include both your spoken text AND any tool calls needed.
Always be aware of your current camera position and what you can see."""

DEFAULT_MODEL = "qwen3-vl:32b"
FALLBACK_MODEL = "gemma3:4b"


class Agent:
    """Conversational agent that manages Ollama interactions and tool dispatch."""

    def __init__(
        self,
        controller: BCC950Controller,
        model: str = DEFAULT_MODEL,
        max_history: int = 20,
    ):
        self.controller = controller
        self.model = model
        self.max_history = max_history
        self.history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def process_turn(
        self,
        transcript: str | None = None,
        image_base64: str | None = None,
    ) -> str:
        """Process one conversation turn.

        Args:
            transcript: User's transcribed speech (None if silence).
            image_base64: Base64-encoded camera frame.

        Returns:
            Amy's spoken response text.
        """
        # Build the user message
        content_parts = []
        if transcript:
            content_parts.append(f"[User said]: {transcript}")
        else:
            content_parts.append("[No speech detected - periodic awareness check]")

        if image_base64:
            content_parts.append("[Camera frame is attached]")

        user_content = "\n".join(content_parts)

        user_msg: dict = {"role": "user", "content": user_content}
        if image_base64:
            user_msg["images"] = [image_base64]

        self.history.append(user_msg)

        # Call Ollama
        try:
            response = ollama_chat(
                model=self.model,
                messages=self.history,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as e:
            error_msg = f"I'm having trouble thinking right now: {e}"
            self.history.append({"role": "assistant", "content": error_msg})
            return error_msg

        message = response.get("message", {})
        assistant_content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        # Execute tool calls
        tool_results = []
        for call in tool_calls:
            func = call.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            print(f"  [Tool] {name}({args})")
            result = dispatch_tool_call(self.controller, name, args)
            tool_results.append({"tool": name, "result": result})
            print(f"  [Tool result] {result}")

        # If we had tool calls, add them to history and get final response
        if tool_calls:
            self.history.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            })
            for tr in tool_results:
                self.history.append({
                    "role": "tool",
                    "content": json.dumps(tr["result"]),
                })

            # Get follow-up response after tool execution
            try:
                follow_up = ollama_chat(
                    model=self.model,
                    messages=self.history,
                )
                follow_content = follow_up.get("message", {}).get("content", "")
                if follow_content:
                    assistant_content = follow_content
            except Exception:
                pass  # Use the original content

        # Record assistant response
        self.history.append({"role": "assistant", "content": assistant_content})

        # Trim history to prevent context overflow
        self._trim_history()

        return assistant_content or "Hmm, I'm not sure what to say."

    def _trim_history(self) -> None:
        """Keep history within max_history messages, preserving the system prompt."""
        if len(self.history) <= self.max_history + 1:
            return
        # Keep system prompt + last max_history messages
        self.history = [self.history[0]] + self.history[-(self.max_history):]
