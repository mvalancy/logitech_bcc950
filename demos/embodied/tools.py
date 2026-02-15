"""Tool dispatch for LLM-driven camera control.

Maps tool names to BCC950Controller methods, returning structured results.
Tool definitions follow the OpenAI function-calling schema used by Ollama.
"""

from __future__ import annotations

from bcc950 import BCC950Controller

# Tool definitions for Ollama chat API
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "pan_camera",
            "description": "Pan the camera left or right for a specified duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["left", "right"],
                        "description": "Direction to pan.",
                    },
                    "duration": {
                        "type": "number",
                        "description": "How long to pan in seconds (0.1 to 5.0).",
                        "default": 0.3,
                    },
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tilt_camera",
            "description": "Tilt the camera up or down for a specified duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Direction to tilt.",
                    },
                    "duration": {
                        "type": "number",
                        "description": "How long to tilt in seconds (0.1 to 5.0).",
                        "default": 0.3,
                    },
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_zoom",
            "description": "Set the camera zoom to an absolute value. Range: 100 (widest) to 500 (most zoomed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "integer",
                        "minimum": 100,
                        "maximum": 500,
                        "description": "Absolute zoom value.",
                    }
                },
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_camera",
            "description": "Combined pan and tilt movement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pan_dir": {
                        "type": "integer",
                        "enum": [-1, 0, 1],
                        "description": "-1 for left, 0 for none, 1 for right.",
                    },
                    "tilt_dir": {
                        "type": "integer",
                        "enum": [-1, 0, 1],
                        "description": "-1 for down, 0 for none, 1 for up.",
                    },
                    "duration": {
                        "type": "number",
                        "description": "Movement duration in seconds.",
                        "default": 0.3,
                    },
                },
                "required": ["pan_dir", "tilt_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_camera_status",
            "description": "Get the camera's current estimated position and list of saved presets.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_camera",
            "description": "Reset the camera to its default center position with minimum zoom.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def dispatch_tool_call(controller: BCC950Controller, name: str, args: dict) -> dict:
    """Execute a tool call and return the result.

    Pan/tilt results include movement feedback: ``moved`` indicates whether the
    camera actually shifted, and ``can_*`` flags report the current limit state.
    """
    pos = controller.position

    if name == "pan_camera":
        duration = float(args.get("duration", 0.3))
        if args["direction"] == "left":
            moved = controller.pan_left(duration)
        else:
            moved = controller.pan_right(duration)
        return {
            "status": "ok",
            "action": f"panned {args['direction']} for {duration}s",
            "moved": moved,
            "at_limit": not moved,
            "can_pan_left": pos.can_pan_left,
            "can_pan_right": pos.can_pan_right,
        }

    elif name == "tilt_camera":
        duration = float(args.get("duration", 0.3))
        if args["direction"] == "up":
            moved = controller.tilt_up(duration)
        else:
            moved = controller.tilt_down(duration)
        return {
            "status": "ok",
            "action": f"tilted {args['direction']} for {duration}s",
            "moved": moved,
            "at_limit": not moved,
            "can_tilt_up": pos.can_tilt_up,
            "can_tilt_down": pos.can_tilt_down,
        }

    elif name == "set_zoom":
        controller.zoom_to(int(args["value"]))
        return {"status": "ok", "zoom": args["value"]}

    elif name == "move_camera":
        pan_moved, tilt_moved = controller.move(
            int(args["pan_dir"]),
            int(args["tilt_dir"]),
            float(args.get("duration", 0.3)),
        )
        return {
            "status": "ok",
            "pan_moved": pan_moved,
            "tilt_moved": tilt_moved,
            "can_pan_left": pos.can_pan_left,
            "can_pan_right": pos.can_pan_right,
            "can_tilt_up": pos.can_tilt_up,
            "can_tilt_down": pos.can_tilt_down,
        }

    elif name == "get_camera_status":
        return {
            "pan": pos.pan,
            "tilt": pos.tilt,
            "zoom": pos.zoom,
            "can_pan_left": pos.can_pan_left,
            "can_pan_right": pos.can_pan_right,
            "can_tilt_up": pos.can_tilt_up,
            "can_tilt_down": pos.can_tilt_down,
            "limits": {
                "pan_min": pos.pan_min,
                "pan_max": pos.pan_max,
                "tilt_min": pos.tilt_min,
                "tilt_max": pos.tilt_max,
            },
            "presets": controller.list_presets(),
        }

    elif name == "reset_camera":
        controller.reset_position()
        return {"status": "ok"}

    return {"status": "error", "message": f"Unknown tool: {name}"}
