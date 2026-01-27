"""Tests for the PromptLoader module."""

from __future__ import annotations

from pathlib import Path

import pytest

from kagan.agents.prompt_loader import PromptLoader, dump_default_prompts
from kagan.config import HatConfig, KaganConfig, PromptsConfig


class TestPromptsConfig:
    """Test PromptsConfig model."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = PromptsConfig()
        assert config.worker_system_prompt == ""
        assert config.reviewer_system_prompt == ""
        assert config.planner_system_prompt == ""

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = PromptsConfig(
            worker_system_prompt="worker prompt",
            reviewer_system_prompt="reviewer prompt",
            planner_system_prompt="planner prompt",
        )
        assert config.worker_system_prompt == "worker prompt"
        assert config.reviewer_system_prompt == "reviewer prompt"
        assert config.planner_system_prompt == "planner prompt"


class TestHatConfigPromptFile:
    """Test HatConfig prompt_file field."""

    def test_default_empty(self) -> None:
        """Test default prompt_file is empty."""
        config = HatConfig()
        assert config.prompt_file == ""

    def test_custom_prompt_file(self) -> None:
        """Test custom prompt_file."""
        config = HatConfig(prompt_file="backend.md")
        assert config.prompt_file == "backend.md"


class TestPromptLoaderBuiltinDefaults:
    """Test PromptLoader with built-in defaults."""

    def test_get_worker_prompt_default(self, tmp_path: Path) -> None:
        """Test loading default worker prompt."""
        config = KaganConfig()
        # Use tmp_path to ensure no user overrides exist
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_worker_prompt()
        assert "{iteration}" in prompt
        assert "{max_iterations}" in prompt
        assert "{title}" in prompt

    def test_get_reviewer_prompt_default(self, tmp_path: Path) -> None:
        """Test loading default reviewer prompt."""
        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_reviewer_prompt()
        assert "{title}" in prompt
        assert "{ticket_id}" in prompt
        assert "{commits}" in prompt

    def test_get_planner_prompt_default(self, tmp_path: Path) -> None:
        """Test loading default planner prompt (preamble only)."""
        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_planner_prompt()
        # Planner prompt now returns preamble only, not the XML format
        assert "project planning assistant" in prompt
        assert "Guidelines" in prompt


class TestPromptLoaderTomlOverride:
    """Test PromptLoader with TOML inline config overrides."""

    def test_worker_prompt_from_toml(self, tmp_path: Path) -> None:
        """Test worker prompt from TOML config."""
        config = KaganConfig(
            prompts=PromptsConfig(worker_system_prompt="Custom worker prompt")
        )
        # Use tmp_path to ensure no file overrides exist
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_worker_prompt()
        assert prompt == "Custom worker prompt"

    def test_reviewer_prompt_from_toml(self, tmp_path: Path) -> None:
        """Test reviewer prompt from TOML config."""
        config = KaganConfig(
            prompts=PromptsConfig(reviewer_system_prompt="Custom reviewer prompt")
        )
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_reviewer_prompt()
        assert prompt == "Custom reviewer prompt"

    def test_planner_prompt_from_toml(self, tmp_path: Path) -> None:
        """Test planner prompt from TOML config."""
        config = KaganConfig(
            prompts=PromptsConfig(planner_system_prompt="Custom planner prompt")
        )
        loader = PromptLoader(config, prompts_dir=tmp_path / "prompts")
        prompt = loader.get_planner_prompt()
        assert prompt == "Custom planner prompt"


class TestPromptLoaderFileOverride:
    """Test PromptLoader with file overrides."""

    def test_worker_prompt_from_file(self, tmp_path: Path) -> None:
        """Test worker prompt from file override."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "worker.md").write_text("File worker prompt")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        prompt = loader.get_worker_prompt()
        assert prompt == "File worker prompt"

    def test_reviewer_prompt_from_file(self, tmp_path: Path) -> None:
        """Test reviewer prompt from file override."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "reviewer.md").write_text("File reviewer prompt")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        prompt = loader.get_reviewer_prompt()
        assert prompt == "File reviewer prompt"

    def test_planner_prompt_from_file(self, tmp_path: Path) -> None:
        """Test planner prompt from file override."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "planner.md").write_text("File planner prompt")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        prompt = loader.get_planner_prompt()
        assert prompt == "File planner prompt"

    def test_file_takes_priority_over_toml(self, tmp_path: Path) -> None:
        """Test file overrides take priority over TOML config."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "worker.md").write_text("File prompt")

        config = KaganConfig(
            prompts=PromptsConfig(worker_system_prompt="TOML prompt")
        )
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        prompt = loader.get_worker_prompt()
        # File should take priority
        assert prompt == "File prompt"


class TestPromptLoaderHatInstructions:
    """Test PromptLoader hat instructions."""

    def test_no_hat_returns_empty(self) -> None:
        """Test None hat returns empty string."""
        config = KaganConfig()
        loader = PromptLoader(config)
        instructions = loader.get_hat_instructions(None)
        assert instructions == ""

    def test_hat_with_system_prompt(self) -> None:
        """Test hat with system_prompt."""
        config = KaganConfig()
        loader = PromptLoader(config)
        hat = HatConfig(system_prompt="Focus on tests")
        instructions = loader.get_hat_instructions(hat)
        assert instructions == "Focus on tests"

    def test_hat_with_prompt_file(self, tmp_path: Path) -> None:
        """Test hat with prompt_file."""
        prompts_dir = tmp_path / "prompts"
        roles_dir = prompts_dir / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "backend.md").write_text("Backend role instructions")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        hat = HatConfig(prompt_file="backend.md")
        instructions = loader.get_hat_instructions(hat)
        assert instructions == "Backend role instructions"

    def test_hat_prompt_file_without_extension(self, tmp_path: Path) -> None:
        """Test hat with prompt_file without .md extension."""
        prompts_dir = tmp_path / "prompts"
        roles_dir = prompts_dir / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "frontend.md").write_text("Frontend role instructions")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        hat = HatConfig(prompt_file="frontend")  # No .md extension
        instructions = loader.get_hat_instructions(hat)
        assert instructions == "Frontend role instructions"

    def test_hat_prompt_file_takes_priority(self, tmp_path: Path) -> None:
        """Test prompt_file takes priority over system_prompt."""
        prompts_dir = tmp_path / "prompts"
        roles_dir = prompts_dir / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "test.md").write_text("File instructions")

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        hat = HatConfig(
            system_prompt="Inline instructions",
            prompt_file="test.md",
        )
        instructions = loader.get_hat_instructions(hat)
        # File should take priority
        assert instructions == "File instructions"

    def test_hat_falls_back_to_system_prompt(self, tmp_path: Path) -> None:
        """Test falls back to system_prompt when file not found."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        config = KaganConfig()
        loader = PromptLoader(config, prompts_dir=prompts_dir)
        hat = HatConfig(
            system_prompt="Fallback instructions",
            prompt_file="nonexistent.md",
        )
        instructions = loader.get_hat_instructions(hat)
        assert instructions == "Fallback instructions"


class TestKaganConfigWithPrompts:
    """Test KaganConfig with prompts section."""

    def test_config_includes_prompts(self) -> None:
        """Test KaganConfig includes prompts field."""
        config = KaganConfig()
        assert hasattr(config, "prompts")
        assert isinstance(config.prompts, PromptsConfig)

    def test_config_prompts_defaults(self) -> None:
        """Test prompts have defaults."""
        config = KaganConfig()
        assert config.prompts.worker_system_prompt == ""
        assert config.prompts.reviewer_system_prompt == ""
        assert config.prompts.planner_system_prompt == ""


class TestDumpDefaultPrompts:
    """Test dump_default_prompts function."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """Test creates prompts and roles directories."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)

        assert prompts_dir.exists()
        assert (prompts_dir / "roles").exists()

    def test_creates_worker_template(self, tmp_path: Path) -> None:
        """Test creates worker.md with template variables."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)

        worker_file = prompts_dir / "worker.md"
        assert worker_file.exists()
        content = worker_file.read_text()
        assert "{iteration}" in content
        assert "{title}" in content

    def test_creates_reviewer_template(self, tmp_path: Path) -> None:
        """Test creates reviewer.md with template variables."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)

        reviewer_file = prompts_dir / "reviewer.md"
        assert reviewer_file.exists()
        content = reviewer_file.read_text()
        assert "{ticket_id}" in content
        assert "{commits}" in content

    def test_creates_planner_template(self, tmp_path: Path) -> None:
        """Test creates planner.md with preamble (not output format)."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)

        planner_file = prompts_dir / "planner.md"
        assert planner_file.exists()
        content = planner_file.read_text()
        # Planner.md contains preamble only, not the XML format
        assert "project planning assistant" in content
        assert "Guidelines" in content
        # Should NOT contain HTML comments (they confuse the AI)
        assert "<!--" not in content

    def test_creates_example_role(self, tmp_path: Path) -> None:
        """Test creates example.md in roles directory."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)

        example_file = prompts_dir / "roles" / "example.md"
        assert example_file.exists()
        content = example_file.read_text()
        assert "Example Hat Role" in content

    def test_idempotent(self, tmp_path: Path) -> None:
        """Test can be called multiple times without error."""
        prompts_dir = tmp_path / "prompts"
        dump_default_prompts(prompts_dir)
        dump_default_prompts(prompts_dir)  # Second call should not raise

        assert (prompts_dir / "worker.md").exists()
