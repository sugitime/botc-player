"""Application configuration loaded from environment / .env."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
DINOSAUR_DIR = ASSETS_DIR / "dinosaur"
KNOWLEDGE_DIR = PACKAGE_ROOT / "knowledge"


def _running_in_docker() -> bool:
    if os.environ.get("BOTC_IN_DOCKER", "").lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("DOCKER", "").lower() in {"1", "true", "yes"}:
        return True
    return Path("/.dockerenv").exists()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_model: str = Field(default="grok-4.5", alias="XAI_MODEL")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    xai_tts_voice: str = Field(default="rex", alias="XAI_TTS_VOICE")
    tts_pitch_semitones: float = Field(default=3.0, alias="TTS_PITCH_SEMITONES")

    botc_url: str = Field(default="https://botc.app", alias="BOTC_URL")
    agent_player_name: str = Field(default="Dino", alias="AGENT_PLAYER_NAME")

    # In Docker these default to PulseAudio virtual sinks created by entrypoint.
    audio_input_device: str = Field(default="", alias="AUDIO_INPUT_DEVICE")
    audio_output_device: str = Field(default="", alias="AUDIO_OUTPUT_DEVICE")
    sample_rate: int = Field(default=24000, alias="SAMPLE_RATE")

    face_width: int = Field(default=640, alias="FACE_WIDTH")
    face_height: int = Field(default=640, alias="FACE_HEIGHT")
    virtual_cam_fps: int = Field(default=15, alias="VIRTUAL_CAM_FPS")
    v4l2_device: str = Field(default="", alias="BOTC_V4L2_DEVICE")
    fake_video_path: str = Field(default="/tmp/botc_dino.y4m", alias="BOTC_FAKE_VIDEO")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    in_docker: bool = Field(default_factory=_running_in_docker, alias="BOTC_IN_DOCKER")

    @field_validator("in_docker", mode="before")
    @classmethod
    def _parse_docker_flag(cls, v):  # noqa: ANN001
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return _running_in_docker()
        if isinstance(v, str):
            return v.lower() in {"1", "true", "yes"}
        return bool(v)

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        # Apply Docker audio defaults when not explicitly set
        if self.in_docker or _running_in_docker():
            object.__setattr__(self, "in_docker", True)
            if not self.audio_output_device:
                object.__setattr__(self, "audio_output_device", "VirtualMic")
            if not self.audio_input_device:
                object.__setattr__(self, "audio_input_device", "GameOut")

    @property
    def dinosaur_idle(self) -> Path:
        return DINOSAUR_DIR / "idle.jpg"

    @property
    def dinosaur_talk_mid(self) -> Path:
        return DINOSAUR_DIR / "talk_mid.jpg"

    @property
    def dinosaur_talk_open(self) -> Path:
        return DINOSAUR_DIR / "talk_open.jpg"

    def require_api_key(self) -> str:
        if not self.xai_api_key:
            raise RuntimeError(
                "XAI_API_KEY is not set. Copy .env.example to .env and add your key from https://console.x.ai"
            )
        return self.xai_api_key


def get_settings() -> Settings:
    return Settings()
