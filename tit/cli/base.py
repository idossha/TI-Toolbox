"""
Base CLI framework for TI-Toolbox CLI scripts.

Provides consistent support for both interactive and direct execution modes
across all CLI tools. Designed to be modular, reusable, and extensible.

Interactive Mode:
- Prompts users for input in a call-and-response fashion
- Validates input and provides helpful defaults
- Allows for complex multi-step configuration

Direct Mode:
- Accepts command-line arguments directly
- Suitable for scripting, automation, and CI/CD
- Environment variable fallbacks where appropriate

Usage:
    class MyCLI(BaseCLI):
        def get_argument_parser(self):
            # Define direct mode arguments

        def get_interactive_prompts(self):
            # Define interactive mode prompts

        def execute(self, args):
            # Execute the actual functionality

    if __name__ == "__main__":
        MyCLI().run()
"""

from __future__ import annotations

import argparse
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TypeVar

from tit.cli import utils


@dataclass
class ArgumentDefinition:
    """Definition for a command-line argument."""
    name: str
    type: type = str
    help: str = ""
    default: Any = None
    required: bool = False
    choices: Optional[List[Any]] = None
    metavar: Optional[str] = None
    nargs: Any = None  # passed through to argparse (e.g. 3, '+', '*')

    # For interactive mode
    prompt_text: Optional[str] = None
    prompt_default: Any = None
    validator: Optional[Callable[[Any], bool]] = None
    validator_message: str = ""


@dataclass
class InteractivePrompt:
    """Definition for an interactive prompt."""
    name: str
    prompt_text: str
    type: type = str
    default: Any = None
    choices: Optional[List[Any]] = None
    required: bool = True
    validator: Optional[Callable[[Any], bool]] = None
    validator_message: str = "Invalid input. Please try again."
    help_text: Optional[str] = None


class BaseCLI(ABC):
    """
    Base class for TI-Toolbox CLI scripts.

    Provides consistent interactive and direct mode support.
    """

    def __init__(self, description: str = ""):
        self.description = description
        self._argument_definitions: Dict[str, ArgumentDefinition] = {}
        self._interactive_prompts: List[InteractivePrompt] = []

    def add_argument(self, arg_def: ArgumentDefinition) -> None:
        """Add an argument definition for direct mode."""
        self._argument_definitions[arg_def.name] = arg_def

    def add_interactive_prompt(self, prompt: InteractivePrompt) -> None:
        """Add an interactive prompt definition."""
        self._interactive_prompts.append(prompt)

    def is_interactive_mode(self) -> bool:
        """Check if we should run in interactive mode."""
        # Interactive mode if stdin is a TTY and no args were provided.
        return len(sys.argv) == 1 and sys.stdin.isatty()

    def run(self) -> int:
        """Main entry point - determines mode and executes."""
        try:
            if self.is_interactive_mode():
                return self.run_interactive()
            else:
                return self.run_direct()
        except KeyboardInterrupt:
            utils.echo_warning("\nCancelled.")
            return 1
        except Exception as e:
            utils.echo_error(str(e))
            return 1

    def run_direct(self) -> int:
        """Run in direct mode using command-line arguments."""
        parser = argparse.ArgumentParser(
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )

        # Add script-specific arguments
        for arg_def in self._argument_definitions.values():
            kwargs = {
                "help": arg_def.help,
                "default": arg_def.default,
                "metavar": arg_def.metavar,
            }

            if arg_def.choices:
                kwargs["choices"] = arg_def.choices
            if arg_def.nargs is not None:
                kwargs["nargs"] = arg_def.nargs

            if arg_def.type == bool:
                kwargs["action"] = "store_true"
                kwargs.pop("metavar", None)
                kwargs.pop("default", None)
            else:
                kwargs["type"] = arg_def.type
                kwargs["required"] = arg_def.required

            parser.add_argument(f"--{arg_def.name.replace('_', '-')}", **kwargs)

        args = parser.parse_args()

        return self.execute(vars(args))

    def run_interactive(self) -> int:
        """Run in interactive mode with prompts."""
        utils.echo_header(f"{self.__class__.__name__.replace('CLI', '')} (interactive)")

        args = {}

        for prompt in self._interactive_prompts:
            value = self._prompt_for_value(prompt)
            args[prompt.name] = value

        return self.execute(args)

    @staticmethod
    def select_one(
        *,
        prompt_text: str,
        options: List[str],
        help_text: Optional[str] = None,
    ) -> str:
        """Select a single item from a non-empty list (1-based index)."""
        if not options:
            raise RuntimeError("No options available to select from.")
        if help_text:
            utils.echo_info(help_text)
        print(f"{utils.prompt_text(prompt_text)} [1-{len(options)}]:")
        utils.print_options(options)
        while True:
            raw = input(f"{utils.prompt_text('Selection')}: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(options):
                    return options[idx - 1]
            utils.echo_error("Invalid selection.")

    @staticmethod
    def select_many(
        *,
        prompt_text: str,
        options: List[str],
        help_text: Optional[str] = None,
    ) -> List[str]:
        """Select multiple items from a non-empty list (comma-separated indices)."""
        if not options:
            raise RuntimeError("No options available to select from.")
        if help_text:
            utils.echo_info(help_text)
        print(f"{utils.prompt_text(prompt_text)} (comma-separated indices):")
        utils.print_options(options)
        while True:
            raw = input(f"{utils.prompt_text('Selection')}: ").strip()
            if not raw:
                utils.echo_error("Selection required.")
                continue
            out: List[str] = []
            ok = True
            for tok in raw.split(","):
                t = tok.strip()
                if not t.isdigit():
                    ok = False
                    break
                idx = int(t)
                if not (1 <= idx <= len(options)):
                    ok = False
                    break
                out.append(options[idx - 1])
            if ok and out:
                # stable-unique
                return list(dict.fromkeys(out))
            utils.echo_error("Invalid selection.")

    def _prompt_for_value(self, prompt: InteractivePrompt) -> Any:
        """Prompt user for a value with validation."""
        while True:
            if prompt.help_text:
                utils.echo_info(prompt.help_text)

            raw_default = "" if prompt.default is None else str(prompt.default)

            if prompt.choices:
                utils.echo_section(prompt.prompt_text)
                utils.print_options([str(c) for c in prompt.choices])
                raw = utils.ask(f"Select [1-{len(prompt.choices)}]", default=(raw_default if raw_default else None))
                if not raw and prompt.default is not None:
                    value = prompt.default
                else:
                    # allow either numeric index or exact value
                    if raw.isdigit():
                        idx = int(raw)
                        if idx < 1 or idx > len(prompt.choices):
                            utils.echo_error(prompt.validator_message)
                            continue
                        value = prompt.choices[idx - 1]
                    else:
                        if raw not in [str(x) for x in prompt.choices]:
                            utils.echo_error(prompt.validator_message)
                            continue
                        value = raw
            else:
                raw = utils.ask(prompt.prompt_text, default=(raw_default if raw_default else None))
                if not raw and prompt.default is not None:
                    value = prompt.default
                else:
                    value = self._cast(prompt.type, raw)

            if prompt.required and (value is None or (isinstance(value, str) and not value.strip())):
                utils.echo_error("Value required.")
                continue

            if prompt.validator and not prompt.validator(value):
                utils.echo_error(prompt.validator_message)
                continue

            return value

    @staticmethod
    def _cast(t: type, raw: str) -> Any:
        if t is bool:
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        if t is int:
            return int(raw)
        if t is float:
            return float(raw)
        return raw

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> int:
        """
        Execute the CLI functionality.

        Args:
            args: Dictionary of argument names to values

        Returns:
            Exit code (0 for success)
        """
        pass
